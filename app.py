# app.py
import streamlit as st
from databases.connection import DatabaseManager
from views.backtesting import render_backtesting_dashboard
from views.team_view import render_team_view
from views.fixtures_view import render_fixtures_view
from views.betting_simulation_view import render_betting_simulation_view
from views.referees_view import render_referees_view
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
    st.title("⚽ Análisis de faltas y tarjetas")
    
    # Barra lateral para navegación jerárquica
    st.sidebar.title("Navegación")
    
    # 1. Selección de Liga
    league_options = {info["name"]: lid for lid, info in TARGET_LEAGUES.items()}
    selected_league_name = st.sidebar.selectbox("Selecciona una Liga", list(league_options.keys()))
    selected_league_id = league_options[selected_league_name]
    
    season = st.sidebar.selectbox("Temporada", [CURRENT_SEASON, CURRENT_SEASON - 1], index=0)

    st.sidebar.divider()
    st.sidebar.markdown("### Menú de Vistas")
    
    # Lista de opciones estandarizada
    options_list = [
        "Ligas y Equipos", 
        "Jugadores", 
        "Partidos", 
        "Árbitros", 
        "Simulador de Apuestas", 
        "📈 Backtesting & Performance"
    ]

    # --- MANEJO SEGURO DE ESTADO DE NAVEGACIÓN ---
    # 1. Inicializar la clave 'current_view' si no existe
    if "current_view" not in st.session_state:
        st.session_state["current_view"] = "Ligas y Equipos"

    # 2. Si venimos de un botón (ej: "Ver Jugadores" usando st.session_state["navigate_to"])
    if "navigate_to" in st.session_state:
        st.session_state["current_view"] = st.session_state.pop("navigate_to")

    # 3. Widget de radio enlazado a 'current_view'
    view_mode = st.sidebar.radio(
        "Ir a:", 
        options_list, 
        key="current_view"
    )

    # --- CONTROL DE VISTAS ---
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

    elif view_mode == "Árbitros":
        with st.spinner("🔄 Cargando perfil y estadísticas arbitrales..."):
            render_referees_view(db_manager, selected_league_id, season, selected_league_name)

    elif view_mode == "Simulador de Apuestas":
        st.header(f"🤖 Simulador Inteligente - {selected_league_name}")
        with st.spinner("🔄 Calculando probabilidades y estadísticas de alta confianza..."):
            render_betting_simulation_view(db_manager, selected_league_id, season)
            
    elif view_mode == "📈 Backtesting & Performance":
        with st.spinner("🔄 Calculando métricas de rendimiento y bankroll..."):
            render_backtesting_dashboard(db_manager, selected_league_id, season)


if __name__ == "__main__":
    main()