# views/player_view.py
import streamlit as st
from databases.connection import DatabaseManager
from controllers.player_controller import PlayerController

def render_player_view(db_manager: DatabaseManager, league_id: int, season: int):
    """Renderiza la vista de jugadores aplicando estrictamente arquitectura MVC."""
    
    selected_team_id = st.session_state.get("selected_team_id")
    
    # 1. Obtener todos los datos necesarios a través del Controlador
    teams_dict, players, last_updated = PlayerController.get_player_view_data(
        db_manager, league_id, season, selected_team_id
    )

    # 2. Layout superior con metadatos de sincronización y botón de actualización
    col_info, col_btn = st.columns([3, 1])
    
    with col_info:
        st.caption(f"🕒 Última actualización de jugadores: **{last_updated}**")
        
    with col_btn:
        if st.button("🔄 Sincronizar Jugadores", key=f"sync_players_{league_id}"):
            print(">>> DIAGNÓSTICO: Se hizo clic en el botón de sincronizar jugadores")
            with st.status("🔄 Sincronizando plantillas y estadísticas...", expanded=True) as status:
                st.write("Conectando con la API de fútbol...")
                PlayerController.sync_players_data(db_manager, league_id, season)
                st.write("Guardando registros en la base de datos...")
                print(">>> DIAGNÓSTICO: Sincronización terminada correctamente")
                status.update(label="¡Sincronización de jugadores completada!", state="complete", expanded=False)
            st.rerun()

    st.divider()

    # 3. Preparar filtros por equipo
    team_options = ["Todos los equipos"] + list(teams_dict.keys())
    
    default_team_name = "Todos los equipos"
    if selected_team_id:
        for name, tid in teams_dict.items():
            if tid == selected_team_id:
                default_team_name = name
                break

    default_team_index = team_options.index(default_team_name) if default_team_name in team_options else 0

    st.markdown("### 🔍 Filtrar Plantillas")
    col1, col2 = st.columns([2, 2])
    
    with col1:
        chosen_team_name = st.selectbox(
            "Filtrar por Equipo:", 
            team_options, 
            index=default_team_index, 
            key="player_team_filter"
        )
    
    if chosen_team_name == "Todos los equipos":
        if "selected_team_id" in st.session_state:
            del st.session_state["selected_team_id"]
        if "selected_team_name" in st.session_state:
            del st.session_state["selected_team_name"]
        _, players, _ = PlayerController.get_player_view_data(db_manager, league_id, season, None)
        view_title = f"Todos los Jugadores de la Liga (Temporada {season})"
    else:
        chosen_team_id = teams_dict[chosen_team_name]
        st.session_state["selected_team_id"] = chosen_team_id
        st.session_state["selected_team_name"] = chosen_team_name
        _, players, _ = PlayerController.get_player_view_data(db_manager, league_id, season, chosen_team_id)
        view_title = f"Jugadores de: {chosen_team_name}"

        if st.button("⬅️ Ver toda la liga"):
            del st.session_state["selected_team_id"]
            del st.session_state["selected_team_name"]
            st.rerun()

    st.markdown(f"### 🏃‍♂️ {view_title}")

    if not players:
        st.warning("⚠️ No hay jugadores registrados para este filtro en la base de datos local.")
        return

    with col2:
        search_query = st.text_input("Buscar jugador por nombre:", "", key="player_search_input")

    filtered_players = [
        p for p in players 
        if search_query.lower() in p["player_name"].lower()
    ] if search_query else players

    table_data = []
    for p in filtered_players:
        table_data.append({
            "Jugador": p["player_name"],
            "Minutos": p["minutes_played"],
            "Faltas Cometidas": p["fouls_committed"],
            "Faltas Recibidas": p["fouls_drawn"],
            "Amarillas": p["yellow_cards"],
            "Rojas": p["red_cards"],
            "F/90": p["fouls_per_90"]
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)