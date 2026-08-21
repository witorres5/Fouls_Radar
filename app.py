# app.py
import streamlit as st
from databases.connection import DatabaseManager
from views.team_view import render_team_view
from views.fixtures_view import render_fixtures_view
from views.betting_simulation_view import render_betting_simulation_view  # <-- Importamos la nueva vista
from config.constants import TARGET_LEAGUES, CURRENT_SEASON

# Configuración inicial de la página
st.set_page_config(
    page_title="Fouls Tracker Pro",
    page_icon="⚽",
    layout="wide"
)

@st.cache_resource
def get_db():
    db_url = st.secrets.get("TURSO_DATABASE_URL", "local.db")
    auth_token = st.secrets.get("TURSO_AUTH_TOKEN", "")
    return DatabaseManager(db_url=db_url, auth_token=auth_token)

db_manager = get_db()

def main():
    st.title("⚽ Fouls Tracker & Analytics Architecture")
    
    # Barra lateral para navegación jerárquica
    st.sidebar.title("Navegación")
    
    # 1. Selección de Liga
    league_options = {info["name"]: lid for lid, info in TARGET_LEAGUES.items()}
    selected_league_name = st.sidebar.selectbox("Selecciona una Liga", list(league_options.keys()))
    selected_league_id = league_options[selected_league_name]
    
    season = st.sidebar.selectbox("Temporada", [CURRENT_SEASON, CURRENT_SEASON - 1], index=0)

    st.sidebar.divider()
    st.sidebar.markdown("### Menú de Vistas")
    
    # Añadimos "Simulador de Apuestas" al menú de opciones
    options_list = ["Ligas y Equipos", "Jugadores", "Partidos", "Simulador de Apuestas"]

    # Si venimos de hacer clic en "Ver Jugadores" desde un equipo, forzamos la vista
    if "selected_team_id" in st.session_state:
        st.session_state["current_view"] = "Jugadores"

    # Inicializamos la vista actual si no existe en session_state
    if "current_view" not in st.session_state:
        st.session_state["current_view"] = "Ligas y Equipos"

    # Menú de radio enlazado directamente a st.session_state usando 'key'
    view_mode = st.sidebar.radio(
        "Ir a:", 
        options_list, 
        key="current_view"
    )

    # Control de navegación jerárquica con spinners de carga integrados
    if view_mode == "Ligas y Equipos":
        st.header(f"📊 Resumen: {selected_league_name} ({season})")
        with st.spinner("🔄 Cargando equipos y escudos de la liga..."):
            render_team_view(db_manager, selected_league_id, season)
        
    elif view_mode == "Jugadores":
        st.header(f"🏃‍♂️ Estadísticas de Jugadores - {selected_league_name}")
        from views.player_view import render_player_view
        with st.spinner("🔄 Cargando estadísticas de jugadores y plantillas..."):
            render_player_view(db_manager, selected_league_id, season)

    elif view_mode == "Partidos":
        st.header(f"⚖️ Análisis de Partidos {selected_league_name}")
        with st.spinner("🔄 Analizando partidos y comportamiento arbitral..."):
            render_fixtures_view(db_manager, selected_league_id, season)

    elif view_mode == "Simulador de Apuestas":
        st.header(f"🤖 Simulador Inteligente - {selected_league_name}")
        with st.spinner("🔄 Calculando probabilidades y estadísticas de alta confianza..."):
            render_betting_simulation_view(db_manager, selected_league_id, season)


if __name__ == "__main__":
    main()