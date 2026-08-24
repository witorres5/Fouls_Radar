# views/player_view.py
import streamlit as st
from databases.connection import DatabaseManager
from controllers.player_controller import PlayerController

def render_player_view(db_manager: DatabaseManager, league_id: int, season: int):
    """Renderiza la vista de jugadores aplicando estrictamente arquitectura MVC."""
    
    # 1. Obtener estado inicial de selección
    selected_team_id = st.session_state.get("selected_team_id")
    
    # 2. Cargar metadatos y lista de equipos desde el controlador
    teams_dict, players, last_updated = PlayerController.get_player_view_data(
        db_manager, league_id, season, selected_team_id
    )

    # 3. Layout superior: Sincronización de datos
    col_info, col_btn = st.columns([3, 1])
    
    with col_info:
        st.caption(f"🕒 Última actualización de jugadores: **{last_updated}**")
        
    with col_btn:
        if st.button("🔄 Sincronizar Jugadores", key=f"sync_players_{league_id}"):
            with st.status("🔄 Sincronizando plantillas y estadísticas...", expanded=True) as status:
                st.write("Conectando con la API de fútbol...")
                PlayerController.sync_players_data(db_manager, league_id, season)
                st.write("Guardando registros en la base de datos...")
                status.update(label="¡Sincronización de jugadores completada!", state="complete", expanded=False)
            st.rerun()

    st.divider()

    # 4. Construcción de Filtros (Garantiza layout col1 y col2 juntos)
    st.markdown("### 🔍 Filtrar Plantillas")
    col1, col2 = st.columns([2, 2])
    
    team_options = ["Todos los equipos"] + list(teams_dict.keys())
    default_team_name = "Todos los equipos"
    
    if selected_team_id:
        for name, tid in teams_dict.items():
            if tid == selected_team_id:
                default_team_name = name
                break

    default_team_index = team_options.index(default_team_name) if default_team_name in team_options else 0

    with col1:
        chosen_team_name = st.selectbox(
            "Filtrar por Equipo:", 
            team_options, 
            index=default_team_index, 
            key="player_team_filter"
        )
    
    with col2:
        search_query = st.text_input("Buscar jugador por nombre:", "", key="player_search_input")

    # 5. Lógica de selección de equipos y actualización de sesión
    if chosen_team_name == "Todos los equipos":
        if "selected_team_id" in st.session_state:
            del st.session_state["selected_team_id"]
        if "selected_team_name" in st.session_state:
            del st.session_state["selected_team_name"]
        
        # Volver a cargar la lista global si cambió la selección a "Todos"
        if selected_team_id is not None:
            _, players, _ = PlayerController.get_player_view_data(db_manager, league_id, season, None)
            
        view_title = f"Todos los Jugadores de la Liga (Temporada {season})"
    else:
        chosen_team_id = teams_dict[chosen_team_name]
        
        # Si el usuario cambió el Selectbox a otro equipo, actualizamos session_state y recargamos datos
        if st.session_state.get("selected_team_id") != chosen_team_id:
            st.session_state["selected_team_id"] = chosen_team_id
            st.session_state["selected_team_name"] = chosen_team_name
            _, players, _ = PlayerController.get_player_view_data(db_manager, league_id, season, chosen_team_id)
            
        view_title = f"Jugadores de: {chosen_team_name}"

        if st.button("⬅️ Ver toda la liga"):
            if "selected_team_id" in st.session_state:
                del st.session_state["selected_team_id"]
            if "selected_team_name" in st.session_state:
                del st.session_state["selected_team_name"]
            st.rerun()

    st.markdown(f"### 🏃‍♂️ {view_title}")

    # 6. Manejo de estado vacío
    if not players:
        st.warning("⚠️ No hay jugadores registrados para este filtro en la base de datos local.")
        return

    # 7. Filtrado en memoria por nombre (usando acceso por dict seguro con fallback .get)
    filtered_players = [
        p for p in players 
        if search_query.lower() in str(p.get("player_name", "")).lower()
    ] if search_query else players

    # 8. Mapeo final a DataFrame de Streamlit
    table_data = [
        {
            "Jugador": p.get("player_name", "Desconocido"),
            "Minutos": p.get("minutes_played", 0),
            "Faltas Cometidas": p.get("fouls_committed", 0),
            "Faltas Recibidas": p.get("fouls_drawn", 0),
            "Amarillas": p.get("yellow_cards", 0),
            "Rojas": p.get("red_cards", 0),
            "F/90": p.get("fouls_per_90", 0.0)
        }
        for p in filtered_players
    ]

    st.dataframe(table_data, use_container_width=True, hide_index=True)