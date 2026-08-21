# views/team_view.py
import streamlit as st
from databases.connection import DatabaseManager
from controllers.team_controller import TeamController

def render_team_view(db_manager: DatabaseManager, league_id: int, season: int):
    """Renderiza la vista de equipos aplicando arquitectura MVC estricta."""
    
    # 1. Obtener datos a través del Controlador
    teams, last_updated = TeamController.get_team_view_data(db_manager, league_id, season)

    # 2. Layout superior con metadatos y botón de sincronización
    col_info, col_btn = st.columns([3, 1])
    
    with col_info:
        st.caption(f"🕒 Última actualización de equipos: **{last_updated}**")
        
    with col_btn:
        if st.button("🔄 Sincronizar Equipos", key=f"sync_teams_{league_id}"):
            with st.status("🔄 Sincronizando equipos...", expanded=True) as status:
                st.write("Conectando con la API de fútbol...")
                TeamController.sync_teams_data(db_manager, league_id, season)
                st.write("Guardando registros...")
                status.update(label="¡Sincronización de equipos completada!", state="complete", expanded=False)
            st.rerun()

    st.divider()

    st.markdown(f"### 🛡️ Equipos Registrados (Temporada {season})")

    if not teams:
        st.warning("⚠️ No hay equipos registrados en la base de datos local para esta liga. Haz clic en 'Sincronizar Equipos'.")
        return

    # 3. Renderizar tabla o tarjetas de equipos
    table_data = []
    for t in teams:
        table_data.append({
            "ID": t["team_id"],
            "Nombre": t["name"],
            "Código": t["code"],
            "País": t["country"],
            "Fundación": t["founded"]
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)