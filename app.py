import streamlit as st

st.set_page_config(page_title="Radar de Faltas por Liga y Jugador", layout="wide")

from core.api_client import APIFootballClient
from database.data_loader import load_data
from components.sidebar import render_sidebar
from components.match_cards import render_upcoming_matches
from components.tabs import render_analysis_tabs
from core.auto_bettor import process_daily_auto_bets
from core.reconciliation import reconcile_daily_bets
from config.constants import TARGET_LEAGUES
from main import run_pipeline

# --- CLIENTE DE API CACHEADO (PERSISTENTE) ---
@st.cache_resource
def get_api_client():
    return APIFootballClient()

client = get_api_client()

# --- CARGA Y CACHÉ DE DATOS DESDE TURSO / SQLITE ---
@st.cache_data(ttl=600)  # Guarda en RAM los datos durante 10 minutos
def get_cached_raw_data():
    return load_data()

# --- CACHÉ PARA PRÓXIMOS PARTIDOS Y AUTO-BETS ---
@st.cache_data(ttl=1800)  # Guarda en RAM por 30 minutos por liga
def get_cached_upcoming_and_bets(league_id: int, season: int, _df_hash):
    """Consulta próximos partidos y procesa apuestas en segundo plano de forma limpia."""
    upcoming_fixtures = client.get_next_fixtures(league_id=league_id, next_n=5)
    if upcoming_fixtures:
        process_daily_auto_bets(league_id, season, upcoming_fixtures, _df_hash)
    return upcoming_fixtures

# Estilos CSS
st.markdown("""
    <style>
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.75rem 0.75rem 0.5rem 0.75rem !important;
        }
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

# 1. Reconciliación de apuestas (Solo se ejecuta UNA VEZ por sesión de Streamlit)
if "reconciled" not in st.session_state:
    with st.spinner("Sincronizando estado de apuestas..."):
        try:
            reconcile_daily_bets(client)
        except Exception as e:
            st.warning(f"No se pudo conciliar apuestas automáticamente: {e}")
    st.session_state["reconciled"] = True

# 2. Cargar Datos Globales (Desde Caché en RAM)
raw_df = get_cached_raw_data()

# 3. Renderizar Sidebar y Obtener Datos Filtrados
filtered_df, selected_season, selected_league, min_edge = render_sidebar(raw_df)

# 4. Encabezado y KPIs Principales
league_title = f" - {selected_league}" if selected_league != "Todas" else ""
st.title(f"⚽ Probabilidad de Faltas por Jugador{league_title}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Jugadores Analizados", len(filtered_df))
col2.metric("Total Faltas Cometidas", int(filtered_df["fouls_committed"].sum()) if not filtered_df.empty else 0)
col3.metric("Promedio Faltas/90m", f"{filtered_df['fouls_per_90'].mean():.2f}" if not filtered_df.empty else "0.00")
col4.metric("Máx. Faltas/90m", f"{filtered_df['fouls_per_90'].max():.2f}" if not filtered_df.empty else "0.00")

# 5. Generar y guardar las apuestas del día con Caché activa
if selected_league != "Todas" and not filtered_df.empty:
    league_id = next((l_id for l_id, info in TARGET_LEAGUES.items() if info["name"] == selected_league), None)
    if league_id:
        # Se ejecuta en memoria amortiguada evitando bloqueos de red
        get_cached_upcoming_and_bets(league_id, selected_season, filtered_df)

# 6. Renderizar Sección de Próximos Partidos
render_upcoming_matches(selected_league, selected_season, filtered_df, client, min_edge)

# 7. Renderizar Pestañas de Análisis y Panel de Apuestas
render_analysis_tabs(filtered_df, selected_league, min_edge, client=client)

# --- BOTÓN DE ACTUALIZACIÓN / SINCRONIZACIÓN EN EL SIDEBAR ---
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Gestión de Datos")

if st.sidebar.button("🔄 Sincronizar Datos con API", use_container_width=True):
    with st.spinner("Ejecutando pipeline incremental de datos..."):
        try:
            # Corre la temporada actual en modo incremental
            current_season = selected_season if 'selected_season' in locals() else 2026
            run_pipeline(seasons=[current_season], max_workers=3, export_csv=False)
            
            # IMPRESCINDIBLE: Limpiar la caché de Streamlit para leer los nuevos registros de Turso
            st.cache_data.clear()
            
            st.sidebar.success("¡Base de datos y árbitros actualizados!")
            st.rerun()  # Recarga la app inmediatamente con la data fresca
        except Exception as e:
            st.sidebar.error(f"Error durante la sincronización: {e}")