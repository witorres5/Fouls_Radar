import streamlit as st
from datetime import datetime
from controllers.fixture_controller import FixtureController
from utils.betting_engine import BettingEngine

def render_fixtures_view(db_manager, league_id, season):
    st.markdown("### ⚖️ Análisis de Partidos y Estadísticas Arbitrales")

    # Delegación correcta al Controlador sin invocar Repositorios directamente
    entity_name = f"fixtures_league_{league_id}_{season}"
    last_updated = FixtureController.get_last_sync(db_manager, entity_name)

    # Sección de sincronización
    col_sync1, col_sync2 = st.columns([3, 1])
    with col_sync1:
        st.info(f"Última sincronización: **{last_updated}**")
    with col_sync2:
        if st.button("🔄 Sincronizar", use_container_width=True):
            FixtureController.sync_fixtures_and_stats(db_manager, league_id, season)
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

            referee_factor = 1.05 if referee != "Árbitro no asignado" else 1.00

            top_home = top_foulers_map.get(
                home.get("id"), {"name": "N/D", "avg": 0.0, "fouls_per_90": 0.0}
            )
            top_away = top_foulers_map.get(
                away.get("id"), {"name": "N/D", "avg": 0.0, "fouls_per_90": 0.0}
            )

            # Cálculo de Poisson reubicado en BettingEngine
            prob_home = BettingEngine.calculate_player_over_fouls(
                top_home.get("fouls_per_90", 0.0), referee_factor=referee_factor, threshold=0.5
            )
            prob_away = BettingEngine.calculate_player_over_fouls(
                top_away.get("fouls_per_90", 0.0), referee_factor=referee_factor, threshold=0.5
            )

            top_home["prob"] = prob_home
            top_away["prob"] = prob_away

            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1.2, 2])
                with c1:
                    st.markdown(f"**🏠 {home.get('name', 'Local')}**")
                    st.caption(f"Top Faltas: **{top_home['name']}** ({int(top_home['avg'])} total)")
                    if prob_home > 0:
                        high_badge = "🔥 " if prob_home >= 91.0 else ""
                        st.caption(f"🎯 Prob. +0.5 faltas: {high_badge}**{prob_home}%**")
                    else:
                        st.caption("🎯 Prob. +0.5 faltas: **Sin datos**")

                with c2:
                    st.markdown("**vs**")
                    st.caption(f"🕒 {formatted_date}")
                    st.caption(f"👤 {referee}")

                with c3:
                    st.markdown(f"**✈️ {away.get('name', 'Visitante')}**")
                    st.caption(f"Top Faltas: **{top_away['name']}** ({int(top_away['avg'])} total)")
                    if prob_away > 0:
                        high_badge = "🔥 " if prob_away >= 91.0 else ""
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