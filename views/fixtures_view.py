# views/fixtures_view.py
import streamlit as st
from datetime import datetime
from controllers.fixture_controller import FixtureController
from databases.fixture_repository import FixtureRepository
from utils.betting_engine import BettingEngine

def render_fixtures_view(db_manager, league_id, season):
    st.markdown("### ⚖️ Análisis de Partidos y Estadísticas Arbitrales")

    entity_name = f"fixtures_league_{league_id}_{season}"
    last_updated = FixtureController.get_last_sync(db_manager, entity_name)
    fixture_repo = FixtureRepository(db_manager)
    league_avg_fouls, _ = fixture_repo.get_league_averages(league_id, season)

    # Sección de sincronización
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
                        high_badge = "🔥 " if prob_home >= 90.0 else ""
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
                        high_badge = "🔥 " if prob_away >= 90.0 else ""
                        st.caption(f"🎯 Prob. +0.5 faltas: {high_badge}**{prob_away}%**")
                    else:
                        st.caption("🎯 Prob. +0.5 faltas: **Sin datos**")
    else:
        st.info("Sin partidos en los próximos 3 días.")

    st.markdown("---")
    st.markdown("### 📋 Resumen de Comportamiento")

    df_summary = FixtureController.get_competition_summary(db_manager, league_id, season)

    if not df_summary.empty:
        st.dataframe(df_summary, use_container_width=True)
    else:
        st.warning("Aún no hay estadísticas registradas.")