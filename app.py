import streamlit as st

st.set_page_config(page_title="Radar de Faltas por Liga y Jugador", layout="wide")

from core.api_client import APIFootballClient
from database.data_loader import load_data
from components.sidebar import render_sidebar
from components.match_cards import render_upcoming_matches
from components.tabs import render_analysis_tabs

@st.cache_resource
def get_api_client():
    return APIFootballClient()

#Estilos

st.markdown("""
    <style>
        /* Ajustar padding inferior en las tarjetas con contenedor de Streamlit */
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.75rem 0.75rem 0.5rem 0.75rem !important;
        }
        /* Reducir el margen inferior de las métricas para dar espacio */
        [data-testid="stMetric"] {
            margin-bottom: 0px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.1rem !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# Initialize API Client
client = get_api_client()

# 1. Cargar Datos Globales
raw_df = load_data()

# 2. Renderizar Sidebar y Obtener Datos Filtrados
filtered_df, selected_season, selected_league, min_edge = render_sidebar(raw_df)

# 3. Encabezado y KPIs Principales
league_title = f" - {selected_league}" if selected_league != "Todas" else ""
st.title(f"⚽ Probabilidad de Faltas por Jugador{league_title}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Jugadores Analizados", len(filtered_df))
col2.metric("Total Faltas Cometidas", int(filtered_df["fouls_committed"].sum()) if not filtered_df.empty else 0)
col3.metric("Promedio Faltas/90m", f"{filtered_df['fouls_per_90'].mean():.2f}" if not filtered_df.empty else "0.00")
col4.metric("Máx. Faltas/90m", f"{filtered_df['fouls_per_90'].max():.2f}" if not filtered_df.empty else "0.00")

# 4. Sección de Próximos Partidos
render_upcoming_matches(selected_league, selected_season, filtered_df, client, min_edge)

# 5. Pestañas de Análisis Predictivo y Métricas
render_analysis_tabs(filtered_df, selected_league, min_edge)