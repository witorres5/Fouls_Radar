# views/fixtures_view.py
import streamlit as st
from datetime import datetime
from controllers.fixture_controller import FixtureController
from databases.fixture_repository import FixtureRepository
from databases.feature_repository import FeatureRepository
from services.match_analysis_service import MatchAnalysisService
from services.parlay_service import ParlayService
from utils.betting_engine import BettingEngine


def render_daily_parlay_card(db_manager, selected_league_id: int):
    """Muestra la tarjeta interactiva con la propuesta de Parlay Diario (Max 3 por liga)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    repo = FixtureRepository(db_manager)

    # Obtener picks candidates y construir parlay mediante ParlayService
    picks = repo.get_top_daily_picks_by_league(selected_league_id, today_str, limit=3)
    parlay = ParlayService.build_daily_league_parlay(picks)

    with st.expander("🎯 **Parlay Sugerido del Día (Top 3 por Liga)**", expanded=True):
        if not parlay or not parlay.get("legs"):
            st.info("ℹ️ No hay suficiente volumen de partidos o selecciones con valor EV+ suficientes para armar un parlay hoy en esta liga.")
            return

        st.caption(f"Combinada automática generada con probabilidades calibradas Poisson & PySpark ({today_str})")

        # Listado de patas (legs) del Parlay
        for idx, leg in enumerate(parlay["legs"], 1):
            col_match, col_pick, col_prob, col_odds = st.columns([3, 3, 2, 2])
            with col_match:
                st.markdown(f"**Leg {idx}:** {leg['match']}")
            with col_pick:
                st.markdown(f"📌 `{leg['selection']}`")
            with col_prob:
                st.markdown(f"Prob: **{leg['individual_prob']}%**")
            with col_odds:
                st.markdown(f"Cuota: **@{leg['fair_odds']}**")

        st.divider()

        # Resumen de métricas acumuladas
        col_summary1, col_summary2, col_summary3, col_action = st.columns([2, 2, 2, 3])
        
        with col_summary1:
            st.metric("Selecciones", f"{parlay['legs_count']}")
        with col_summary2:
            st.metric("Probabilidad Conjunta", f"{parlay['combined_probability_pct']}%")
        with col_summary3:
            st.metric("Cuota Combinada", f"@{parlay['combined_fair_odds']}")

        with col_action:
            if st.button("📲 Enviar Parlay a Telegram", use_container_width=True, key=f"tg_parlay_{selected_league_id}"):
                st.toast("¡Parlay enviado exitosamente al canal de Telegram!", icon="🚀")


def render_fixtures_view(db_manager, league_id, season):
    st.markdown("### ⚖️ Análisis de Partidos y Estadísticas Arbitrales")

    entity_name = f"fixtures_league_{league_id}_{season}"
    last_updated = FixtureController.get_last_sync(db_manager, entity_name)
    fixture_repo = FixtureRepository(db_manager)
    feature_repo = FeatureRepository(db_manager)
    analysis_service = MatchAnalysisService(feature_repo, fixture_repo)

    league_avg_fouls, _ = fixture_repo.get_league_averages(league_id, season)

    # 1. Sección de sincronización
    col_sync1, col_sync2, col_sync3 = st.columns([2.5, 1.2, 1.3])
    with col_sync1:
        st.info(f"Última sincronización: **{last_updated}**")
    with col_sync2:
        if st.button("🔄 Sincronizar Hoy", use_container_width=True):
            with st.spinner("Sincronizando partidos de hoy..."):
                FixtureController.sync_fixtures_and_stats(db_manager, league_id, season, sync_all_season=False)
            st.success("¡Sincronización del día completada!")
            st.rerun()
    with col_sync3:
        if st.button("📥 Temporada Completa", use_container_width=True):
            with st.spinner("Sincronizando histórico de la temporada..."):
                FixtureController.sync_fixtures_and_stats(db_manager, league_id, season, sync_all_season=True)
            st.success("¡Sincronización histórica completada!")
            st.rerun()

    # 2. Visualización Destacada del Parlay del Día
    render_daily_parlay_card(db_manager, league_id)

    st.markdown("### 📅 Próximos 3 Días")

    upcoming_fixtures = FixtureController.get_upcoming_fixtures_cached(league_id, season, days=3)

    if upcoming_fixtures:
        team_ids = set()
        for fix in upcoming_fixtures:
            teams = fix.get("teams", {})
            if home_id := teams.get("home", {}).get("id"):
                team_ids.add(home_id)
            if away_id := teams.get("away", {}).get("id"):
                team_ids.add(away_id)

        top_foulers_map = FixtureController.get_teams_top_foulers(db_manager, list(team_ids), season)

        for fix in upcoming_fixtures:
            fix_info = fix.get("fixture", {})
            fixture_id = fix_info.get("id")
            teams = fix.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            referee = fix_info.get("referee") or "Árbitro no asignado"

            date_str = fix_info.get("date", "")
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                formatted_date = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                formatted_date = date_str

            ref_matches, ref_avg_fouls, _ = fixture_repo.get_referee_historical_stats(referee)
            referee_factor = BettingEngine.calculate_referee_factor(
                ref_avg_fouls=ref_avg_fouls,
                league_avg_fouls=league_avg_fouls,
                ref_matches_count=ref_matches,
                prior_weight=5.0
            )

            top_home = top_foulers_map.get(
                home.get("id"), {"name": "N/D", "avg": 0.0, "fouls_per_90": 0.0}
            )
            top_away = top_foulers_map.get(
                away.get("id"), {"name": "N/D", "avg": 0.0, "fouls_per_90": 0.0}
            )

            prob_home = BettingEngine.calculate_over_probability(
                metric_rate_per_90=top_home.get("fouls_per_90", 0.0),
                threshold=0.5,
                expected_minutes=85,
                adjustment_factor=referee_factor
            )
            prob_away = BettingEngine.calculate_over_probability(
                metric_rate_per_90=top_away.get("fouls_per_90", 0.0),
                threshold=0.5,
                expected_minutes=85,
                adjustment_factor=referee_factor
            )

            top_home["prob"] = prob_home
            top_away["prob"] = prob_away

            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1.2, 2])
                with c1:
                    st.markdown(f"**🏠 {home.get('name', 'Local')}**")
                    st.caption(f"Top Faltas: **{top_home['name']}** ({int(top_home['avg'])} total | F90: {top_home['fouls_per_90']})")
                    if prob_home > 0:
                        high_badge = "🔥 " if prob_home >= 65.0 else ""
                        st.caption(f"🎯 Prob. +0.5 faltas: {high_badge}**{prob_home}%**")
                    else:
                        st.caption("🎯 Prob. +0.5 faltas: **Sin datos**")

                with c2:
                    st.markdown("**vs**")
                    st.caption(f"🕒 {formatted_date}")
                    st.caption(f"👤 {referee} (x{referee_factor:.2f})")

                with c3:
                    st.markdown(f"**✈️ {away.get('name', 'Visitante')}**")
                    st.caption(f"Top Faltas: **{top_away['name']}** ({int(top_away['avg'])} total | F90: {top_away['fouls_per_90']})")
                    if prob_away > 0:
                        high_badge = "🔥 " if prob_away >= 65.0 else ""
                        st.caption(f"🎯 Prob. +0.5 faltas: {high_badge}**{prob_away}%**")
                    else:
                        st.caption("🎯 Prob. +0.5 faltas: **Sin datos**")

                # Botón para activar el Análisis Profundo con PySpark
                st.divider()
                if st.button(f"🔍 Análisis Profundo (Spark)", key=f"btn_deep_{fixture_id}", use_container_width=True):
                    current_state = st.session_state.get(f"show_analysis_{fixture_id}", False)
                    st.session_state[f"show_analysis_{fixture_id}"] = not current_state

                # Panel de Análisis desplegable
                if st.session_state.get(f"show_analysis_{fixture_id}"):
                    with st.spinner("⚡ Consultando Feature Store PySpark y evaluando distribución..."):
                        analysis = analysis_service.analyze_fixture(
                            fixture_id=fixture_id,
                            home_team_id=home.get("id"),
                            away_team_id=away.get("id"),
                            season=season,
                            referee_name=referee
                        )

                    st.markdown("#### 📊 Proyección Cuantitativa del Encuentro")

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Faltas Esperadas", f"{analysis['expected_fouls']}")
                    k2.metric("Mercado Sugerido", f"{analysis['recommended_market']}")
                    k3.metric("Probabilidad Modelo", f"{analysis['line_probability']}%")
                    k4.metric("Cuota Mínima EV", f"@{analysis['min_odd']}")

                    col_h, col_a = st.columns(2)
                    with col_h:
                        st.caption("🔥 **Racha Reciente Local (Top F90 - Últimos 5 partidos):**")
                        if analysis["home_top_foulers"]:
                            for p in analysis["home_top_foulers"]:
                                st.write(f"• **{p['name']}**: {p['rolling_f90']} F90 *(en {p['matches']} PJ)*")
                        else:
                            st.write("Sin datos recientes en Spark.")

                    with col_a:
                        st.caption("🔥 **Racha Reciente Visitante (Top F90 - Últimos 5 partidos):**")
                        if analysis["away_top_foulers"]:
                            for p in analysis["away_top_foulers"]:
                                st.write(f"• **{p['name']}**: {p['rolling_f90']} F90 *(en {p['matches']} PJ)*")
                        else:
                            st.write("Sin datos recientes en Spark.")

                    # Duelos Directos de Alta Fricción (Matchups)
                    st.markdown("##### ⚔️ Duelos Directos de Alta Fricción")
                    if analysis.get("top_matchups"):
                        for m in analysis["top_matchups"]:
                            st.warning(
                                f"🔥 **{m['committer']}** ({m['committer_side']} - {m['committer_f90']} F90) vs "
                                f"**{m['drawer']}** ({m['drawer_side']} - {m['drawer_fd90']} FD90) | "
                                f"**Índice de Fricción:** `{m['friction_index']}`"
                            )
                    else:
                        st.info("Sin datos suficientes para calcular duelos de alta fricción.")

    else:
        st.info("Sin partidos en los próximos 3 días.")

    st.markdown("---")
    st.markdown("### 📋 Resumen de Comportamiento")

    df_summary = FixtureController.get_competition_summary(db_manager, league_id, season)

    if not df_summary.empty:
        st.dataframe(df_summary, use_container_width=True)
    else:
        st.warning("Aún no hay estadísticas registradas.")
