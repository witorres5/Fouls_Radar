# views/referees_view.py
import streamlit as st
import pandas as pd
from controllers.referee_controller import RefereeController

def render_referees_view(db_manager, selected_league_id, selected_season, league_name):
    st.header(f"🟨 Análisis de Árbitros: {league_name} ({selected_season})")
    
    # Invocación pasando el ID explícito de la liga elegida
    referees_data = RefereeController.get_referees_stats(db_manager, selected_league_id, selected_season)
    
    if not referees_data:
        st.warning(f"No hay registros de partidos con árbitro asignado para {league_name} en {selected_season}.")
        return

    df = pd.DataFrame(referees_data)

    # Tarjetas de Resumen
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Árbitros Registrados", len(df))
    with col2:
        st.metric("Total Partidos Asignados", df['matches'].sum())
    with col3:
        avg_league_fouls = round(df["avg_fouls"].mean(), 2) if not df.empty else 0.0
        st.metric("Promedio Faltas / Partido", f"{avg_league_fouls}")

    st.markdown("---")
    st.subheader("📋 Métricas Detalladas por Árbitro")
    
    df_display = df.rename(columns={
        "referee": "Árbitro",
        "matches": "Partidos Totales",
        "finished_matches": "Partidos Finalizados (FT)",
        "total_fouls": "Faltas Totales",
        "avg_fouls": "Prom. Faltas / Partido"
    })
    
    # Se agrega la 'key' dinámica para que Streamlit refresque la tabla al cambiar de liga
    table_key = f"referee_table_{selected_league_id}_{selected_season}"
    st.dataframe(
        df_display, 
        use_container_width=True,
        hide_index=True,
        key=table_key
    )