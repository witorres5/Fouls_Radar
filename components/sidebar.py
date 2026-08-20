import pandas as pd
import streamlit as st
from config.constants import TARGET_LEAGUES
from main import sync_league_data

@st.cache_data
def convert_df_to_csv(df_to_export: pd.DataFrame) -> bytes:
    return df_to_export.to_csv(index=False).encode('utf-8')

def render_sidebar(df: pd.DataFrame):
    """Renderiza la barra lateral con filtros, exportación y sincronización."""
    st.sidebar.title("🔍 Filtros de Búsqueda")

    # 1. Filtro por Temporada
    selected_season = 2024
    if "season" in df.columns and not df["season"].empty:
        available_seasons = sorted(df["season"].dropna().astype(int).unique(), reverse=True)
        selected_season = st.sidebar.selectbox("Selecciona una Temporada:", available_seasons)
        df_filtered_season = df[df["season"] == selected_season].copy()
    else:
        df_filtered_season = df.copy()

    # 2. Filtro por Liga
    available_leagues = ["Todas"]
    if "league_name" in df_filtered_season.columns and not df_filtered_season["league_name"].empty:
        available_leagues += sorted(df_filtered_season["league_name"].dropna().unique().tolist())

    selected_league = st.sidebar.selectbox("Selecciona una Liga:", available_leagues)

    # 3. Filtro por Minutos
    max_mins = int(df_filtered_season["minutes_played"].max()) if not df_filtered_season.empty and pd.notna(df_filtered_season["minutes_played"].max()) else 3000
    min_minutes = st.sidebar.slider(
        "Mínimo de minutos jugados en temporada:",
        min_value=0,
        max_value=max_mins,
        value=180,
        step=90
    )

    auto_bet_enabled = st.sidebar.toggle(
        "Auto-Simulador Activo", 
        value=True, 
        key="sb_auto_bet_toggle"
    )

    min_edge_threshold = st.sidebar.slider(
        "Margen Mínimo (Faltas de Ventaja):", 
        min_value=0.5, 
        max_value=4.0, 
        value=1.5, 
        step=0.5,
        key="sb_min_edge_slider"
    )

    # Aplicación de Filtros
    filtered_df = df_filtered_season[df_filtered_season["minutes_played"] >= min_minutes].copy()
    if selected_league != "Todas" and "league_name" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["league_name"] == selected_league]

    # Exportación
    st.sidebar.markdown("---")
    st.sidebar.title("📥 Exportar Datos")
    if not filtered_df.empty:
        csv_bytes = convert_df_to_csv(filtered_df)
        st.sidebar.download_button(
            label="📄 Descargar CSV Filtrado",
            data=csv_bytes,
            file_name=f"faltas_{selected_league}_{selected_season}.csv".replace(" ", "_").lower(),
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.sidebar.caption("No hay datos para exportar con los filtros actuales.")

    # Sincronización
    st.sidebar.markdown("---")
    st.sidebar.title("🔄 Sincronizar API")
    sync_season_input = st.sidebar.number_input(
        "Temporada a extraer:", 
        min_value=2020, 
        max_value=2026, 
        value=int(selected_season)
    )

    league_options = {info["name"]: league_id for league_id, info in TARGET_LEAGUES.items()}
    sync_league_name = st.sidebar.selectbox("Liga a actualizar:", list(league_options.keys()))

    if st.sidebar.button("🚀 Sincronizar Ahora", use_container_width=True):
        target_league_id = league_options[sync_league_name]
        with st.sidebar.spinner(f"Descargando {sync_league_name} ({sync_season_input})..."):
            try:
                records_count = sync_league_data(
                    league_id=target_league_id, 
                    league_name=sync_league_name, 
                    season=int(sync_season_input)
                )
                if records_count > 0:
                    st.sidebar.success(f"¡Sincronizados {records_count} jugadores!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.sidebar.warning("No se obtuvieron registros de la API.")
            except PermissionError:
                st.sidebar.error("Límite diario de API alcanzado.")
            except Exception as e:
                st.sidebar.error(f"Error en sincronización: {e}")

    return filtered_df, selected_season, selected_league