# views/fixtures_view.py
import streamlit as st
from datetime import datetime
from controllers.fixture_controller import FixtureController
from databases.fixture_repository import FixtureRepository

def render_fixtures_view(db_manager, league_id, season):
    st.markdown("### ⚖️ Análisis de Partidos y Estadísticas Arbitrales")
    
    fixture_repo = FixtureRepository(db_manager)
    entity_name = f"fixtures_league_{league_id}_{season}"
    last_updated = fixture_repo.get_last_sync(entity_name)
    
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
        # 1. Recolectar todos los IDs de equipos únicos para la consulta por lote (Batch)
        team_ids = set()
        for fix in upcoming_fixtures:
            teams = fix.get("teams", {})
            if home_id := teams.get("home", {}).get("id"):
                team_ids.add(home_id)
            if away_id := teams.get("away", {}).get("id"):
                team_ids.add(away_id)
        
        # 2. Una sola llamada masiva al controlador para obtener los tops de faltas
        top_foulers_map = FixtureController.get_teams_top_foulers(db_manager, list(team_ids), season)

        # 3. Renderizar cada tarjeta consultando el mapa en memoria de forma instantánea O(1)
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

            top_home = top_foulers_map.get(home.get("id"), {"name": "N/D", "avg": 0.0})
            top_away = top_foulers_map.get(away.get("id"), {"name": "N/D", "avg": 0.0})

            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1.2, 2])
                with c1:
                    st.markdown(f"**🏠 {home.get('name', 'Local')}**")
                    st.caption(f"Top Faltas: {top_home['name']} ({int(top_home['avg'])} total)")
                with c2:
                    st.markdown("**vs**")
                    st.caption(f"🕒 {formatted_date}")
                    st.caption(f"👤 {referee}")
                with c3:
                    st.markdown(f"**✈️ {away.get('name', 'Visitante')}**")
                    st.caption(f"Top Faltas: {top_away['name']} ({int(top_away['avg'])} total)")
    else:
        st.info("Sin partidos en los próximos 3 días.")

    st.markdown("---")
    st.markdown("### 📋 Resumen de Comportamiento")
    
    # Llamada limpia al controlador para el resumen global
    df_summary = FixtureController.get_competition_summary(db_manager, league_id, season)
    
    if not df_summary.empty:
        st.dataframe(df_summary, use_container_width=True)
    else:
        st.warning("Aún no hay estadísticas registradas.")