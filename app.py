# app.py
import streamlit as st
from databases.connection import DatabaseManager
from views.backtesting import render_backtesting_dashboard
from views.team_view import render_team_view
from views.fixtures_view import render_fixtures_view
from views.betting_simulation_view import render_betting_simulation_view
from views.referees_view import render_referees_view
from config.constants import TARGET_LEAGUES, CURRENT_SEASON
from components.futuristic_ui import inject_cyber_styles, render_hud_banner

# Configuración inicial de la página
st.set_page_config(
    page_title="FOULS RADAR // QUANT INTELLIGENCE",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyección de estilos Cyber-Quant Globales
inject_cyber_styles()

@st.cache_resource
def get_db():
    db_url = st.secrets.get("TURSO_DATABASE_URL", "local.db")
    auth_token = st.secrets.get("TURSO_AUTH_TOKEN", "")
    return DatabaseManager(db_url=db_url, auth_token=auth_token)

db_manager = get_db()

def main():
    # Header Principal Futurista
    st.markdown("""
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
        <h1 style="margin: 0; background: linear-gradient(90deg, #00F5FF 0%, #00FFA3 50%, #A855F7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            ⚡ FOULS RADAR <span style="font-size: 1.1rem; color: #8B949E; -webkit-text-fill-color: #8B949E; font-family: 'JetBrains Mono', monospace;">// QUANT PRO v2.5</span>
        </h1>
    </div>
    """, unsafe_allow_html=True)

    
    # Barra lateral para navegación jerárquica
    st.sidebar.title("Navegación")
    
    # 1. Selección de Liga
    league_options = {info["name"]: lid for lid, info in TARGET_LEAGUES.items()}
    selected_league_name = st.sidebar.selectbox("Selecciona una Liga", list(league_options.keys()))
    selected_league_id = league_options[selected_league_name]
    
    from config.constants import get_current_season_for_league
    def_season = get_current_season_for_league(selected_league_id)
    season_options = [def_season, def_season - 1] if def_season != CURRENT_SEASON else [CURRENT_SEASON, CURRENT_SEASON - 1]
    season = st.sidebar.selectbox("Temporada", season_options, index=0)

    # Telemetría HUD Superior
    render_hud_banner(db_manager, selected_league_name, season)

    st.sidebar.divider()
    st.sidebar.markdown("### 🎛️ Menú de Módulos")
    
    # Lista de opciones estandarizada
    options_list = [
        "⚽ Ligas y Equipos", 
        "🏃‍♂️ Jugadores & F90", 
        "⚖️ Radar de Partidos", 
        "👨‍⚖️ Perfil Arbitral", 
        "🤖 Simulador Cuántico", 
        "📈 Backtesting & Bankroll"
    ]


    # --- MANEJO SEGURO DE ESTADO DE NAVEGACIÓN ---
    if "current_view" not in st.session_state or st.session_state["current_view"] not in options_list:
        st.session_state["current_view"] = "⚽ Ligas y Equipos"

    if "navigate_to" in st.session_state:
        nav = st.session_state.pop("navigate_to")
        # Mapear nombres anteriores si venían de botones
        name_map = {
            "Ligas y Equipos": "⚽ Ligas y Equipos",
            "Jugadores": "🏃‍♂️ Jugadores & F90",
            "Partidos": "⚖️ Radar de Partidos",
            "Árbitros": "👨‍⚖️ Perfil Arbitral",
            "Simulador de Apuestas": "🤖 Simulador Cuántico",
            "📈 Backtesting & Performance": "📈 Backtesting & Bankroll"
        }
        st.session_state["current_view"] = name_map.get(nav, nav)

    view_mode = st.sidebar.radio(
        "Módulo:", 
        options_list, 
        key="current_view"
    )

    # --- CONTROL DE VISTAS ---
    if view_mode == "⚽ Ligas y Equipos":
        with st.spinner("🔄 Cargando equipos y escudos de la liga..."):
            render_team_view(db_manager, selected_league_id, season)
        
    elif view_mode == "🏃‍♂️ Jugadores & F90":
        from views.player_view import render_player_view
        with st.spinner("🔄 Cargando estadísticas de jugadores y plantillas..."):
            render_player_view(db_manager, selected_league_id, season)

    elif view_mode == "⚖️ Radar de Partidos":
        with st.spinner("🔄 Analizando partidos y comportamiento arbitral..."):
            render_fixtures_view(db_manager, selected_league_id, season)

    elif view_mode == "👨‍⚖️ Perfil Arbitral":
        with st.spinner("🔄 Cargando perfil y estadísticas arbitrales..."):
            render_referees_view(db_manager, selected_league_id, season, selected_league_name)

    elif view_mode == "🤖 Simulador Cuántico":
        with st.spinner("🔄 Calculando probabilidades y estadísticas de alta confianza..."):
            render_betting_simulation_view(db_manager, selected_league_id, season)
            
    elif view_mode == "📈 Backtesting & Bankroll":
        with st.spinner("🔄 Calculando métricas de rendimiento y bankroll..."):
            render_backtesting_dashboard(db_manager, selected_league_id, season)



if __name__ == "__main__":
    main()