# views/team_view.py
import streamlit as st
from databases.connection import DatabaseManager
from controllers.team_controller import TeamController

def render_team_view(db_manager: DatabaseManager, league_id: int, season: int):
    """Renderiza la vista de equipos con UI moderna tipo tarjetas y tabla interactiva."""
    
    # 1. Obtención de datos mediante el Controlador
    teams, last_updated = TeamController.get_team_view_data(db_manager, league_id, season)

    # 2. Encabezado superior y acción de sincronización
    col_info, col_btn = st.columns([3, 1], vertical_alignment="center")
    
    with col_info:
        st.caption(f"🕒 Última actualización local: **{last_updated}**")
        
    with col_btn:
        if st.button("🔄 Sincronizar Equipos", key=f"sync_teams_{league_id}", use_container_width=True):
            with st.status("🔄 Sincronizando equipos...", expanded=True) as status:
                st.write("Conectando con la API de fútbol...")
                TeamController.sync_teams_data(db_manager, league_id, season)
                st.write("Guardando registros en BD...")
                status.update(label="¡Sincronización completada!", state="complete", expanded=False)
            st.rerun()

    st.divider()

    if not teams:
        st.warning("⚠️ No hay equipos registrados localmente para esta liga. Haz clic en 'Sincronizar Equipos'.")
        return

    # 3. Barra de herramientas (Buscador y Cambio de Vista)
    col_search, col_mode = st.columns([3, 1])
    
    with col_search:
        search_query = st.text_input(
            "🔍 Buscar equipo", 
            placeholder="Escribe el nombre del equipo...", 
            label_visibility="collapsed"
        )
        
    with col_mode:
        view_mode = st.radio(
            "Vista:", 
            ["🎴 Tarjetas", "📋 Tabla"], 
            horizontal=True, 
            label_visibility="collapsed"
        )

    # Filtrar lista de equipos según el texto buscado
    filtered_teams = [
        t for t in teams 
        if search_query.lower() in t["name"].lower() or search_query.lower() in (t.get("code") or "").lower()
    ]

    st.markdown(f"**{len(filtered_teams)}** equipos encontrados")
    st.markdown("---")

    # 4. Renderizado según la opción seleccionada
    if view_mode == "🎴 Tarjetas":
        # Disposición en grid de 4 columnas
        cols_per_row = 4
        for i in range(0, len(filtered_teams), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, team in enumerate(filtered_teams[i:i + cols_per_row]):
                with cols[j]:
                    with st.container(border=True):
                        # Escudo del equipo (usando logo si existe la URL)
                        logo_url = team.get("logo") or "https://via.placeholder.com/80?text=FC"
                        st.image(logo_url, width=80)
                        
                        st.markdown(f"##### {team['name']}")
                        st.caption(f"📍 {team.get('country', 'N/A')} | 🗓️ {team.get('founded') or 'N/A'}")
                        
                        # Acciones rápidas por equipo (Navegación segura con 'navigate_to')
                        if st.button("🏃‍♂️ Ver Jugadores", key=f"btn_team_{team['team_id']}", use_container_width=True):
                            st.session_state["selected_team_id"] = team["team_id"]
                            st.session_state["navigate_to"] = "Jugadores"
                            st.rerun()

    else:
        # Renderizado en Formato Tabla
        table_data = []
        for t in filtered_teams:
            table_data.append({
                "Logo": t.get("logo"),
                "Nombre": t["name"],
                "Código": t.get("code") or "N/A",
                "País": t.get("country", "N/A"),
                "Fundación": t.get("founded") or "N/A"
            })

        st.dataframe(
            table_data, 
            column_config={
                "Logo": st.column_config.ImageColumn("Escudo", help="Escudo oficial"),
                "Nombre": st.column_config.TextColumn("Equipo", help="Nombre del club"),
            },
            use_container_width=True, 
            hide_index=True
        )