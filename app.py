import math
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime
import libsql
from main import DatabaseManager

st.set_page_config(page_title="Radar de Faltas por Liga y Jugador", layout="wide")

# 1. Importaciones del núcleo del sistema
from core.api_client import APIFootballClient
from config.constants import TARGET_LEAGUES
from main import export_to_csv, sync_league_data


@st.cache_resource
def get_api_client():
    return APIFootballClient()

client = get_api_client()


# --- CARGA DE DATOS DESDE TURSO ---
@st.cache_data
def load_data():
    turso_url = st.secrets["TURSO_DATABASE_URL"]
    turso_token = st.secrets["TURSO_AUTH_TOKEN"]

    conn = libsql.connect(database=turso_url, auth_token=turso_token)
    df = pd.read_sql("SELECT * FROM player_foul_stats", conn)
    conn.close()
    
    df["minutes_played"] = df["minutes_played"].fillna(0)
    df["fouls_per_90"] = df.apply(
        lambda r: (r["fouls_committed"] / r["minutes_played"] * 90) if r["minutes_played"] > 0 else 0.0, 
        axis=1
    )
    df["fouls_drawn_per_90"] = df.apply(
        lambda r: (r["fouls_drawn"] / r["minutes_played"] * 90) if r["minutes_played"] > 0 else 0.0, 
        axis=1
    )
    return df

@st.cache_data(ttl=300)
def get_team_top_foulers(league_id: int, season: int) -> dict:
    """Obtiene el jugador con más faltas por 90 min de cada equipo de la liga."""
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT team_name, player_name, fouls_per_90
            FROM (
                SELECT team_name, player_name, fouls_per_90,
                       ROW_NUMBER() OVER (PARTITION BY team_name ORDER BY fouls_per_90 DESC) as rn
                FROM player_foul_stats
                WHERE league_id = ? AND season = ? AND minutes_played >= 180
            ) WHERE rn = 1
        """
        cursor.execute(query, (league_id, season))
        rows = cursor.fetchall()
        conn.close()
        
        return {
            row[0]: {"player": row[1], "fouls_per_90": row[2]} 
            for row in rows
        }
    except Exception as e:
        print(f"Error consultando top infractores por equipo: {e}")
        return {}

# --- HELPER CACHEADO PARA CONSULTA DE PARTIDOS ---
@st.cache_data(ttl=3600)
def fetch_next_fixture(team_id: int):
    try:
        return client.get_next_fixture_by_team(team_id=team_id)
    except Exception:
        return {}
    
db = DatabaseManager()
@st.cache_data(ttl=60)  # Expira automáticamente cada 60 segundos si no se fuerza la limpieza
def get_available_seasons() -> list:
    # Ejemplo desde DB
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT season FROM player_foul_stats ORDER BY season DESC")
    rows = cursor.fetchall()
    conn.close()
    
    seasons = [r[0] for r in rows] if rows else [2026, 2025, 2024, 2022]
    return seasons

# --- HELPER PARA CONVERTIR DATAFRAME A CSV EN MEMORIA ---
@st.cache_data
def convert_df_to_csv(df_to_export: pd.DataFrame) -> bytes:
    return df_to_export.to_csv(index=False).encode('utf-8')


# Cargar datos desde Turso
df = load_data()

# --- FILTROS DE BÚSQUEDA EN SIDEBAR ---
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

# 3. Filtro por Minutos Jugados
max_mins = int(df_filtered_season["minutes_played"].max()) if not df_filtered_season.empty and pd.notna(df_filtered_season["minutes_played"].max()) else 3000
min_minutes = st.sidebar.slider(
    "Mínimo de minutos jugados en temporada:",
    min_value=0,
    max_value=max_mins,
    value=180,
    step=90
)

# Aplicar Filtros en Cascada
filtered_df = df_filtered_season[df_filtered_season["minutes_played"] >= min_minutes].copy()

if selected_league != "Todas" and "league_name" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["league_name"] == selected_league]

# --- SECCIÓN DE EXPORTACIÓN A CSV ---
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

# --- SECCIÓN DE SINCRONIZACIÓN EN EL SIDEBAR ---
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


# --- FUNCIONES MATEMÁTICAS DE POISSON ---
def poisson_prob(k: int, lambd: float) -> float:
    return (math.exp(-lambd) * (lambd ** k)) / math.factorial(k)

def prob_at_least(k: int, lambd: float) -> float:
    prob_less = sum(poisson_prob(i, lambd) for i in range(k))
    return max(0.0, 1.0 - prob_less)


# --- DASHBOARD PRINCIPAL ---
league_title = f" - {selected_league}" if selected_league != "Todas" else ""
st.title(f"⚽ Probabilidad de Faltas por Jugador{league_title}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Jugadores Analizados", len(filtered_df))
col2.metric("Total Faltas Cometidas", int(filtered_df["fouls_committed"].sum()) if not filtered_df.empty else 0)
col3.metric("Promedio Faltas/90m", f"{filtered_df['fouls_per_90'].mean():.2f}" if not filtered_df.empty else "0.00")
col4.metric("Máx. Faltas/90m", f"{filtered_df['fouls_per_90'].max():.2f}" if not filtered_df.empty else "0.00")



# --- SECCIÓN: PRÓXIMOS PARTIDOS POR DÍA ---
# --- SECCIÓN: PRÓXIMOS PARTIDOS Y TOP INFRACTORES POR EQUIPO ---
if selected_league != "Todas":
    st.markdown("### 📅 Próximos Partidos")

    # 1. Mapear el nombre de la liga seleccionada a su ID numérico
    league_id = None
    for l_id, info in TARGET_LEAGUES.items():
        if info["name"] == selected_league:
            league_id = l_id
            break

    if league_id:
        # 2. Obtener el jugador con más faltas por equipo desde la base de datos
        top_foulers = get_team_top_foulers(league_id, selected_season)

        # 3. Obtener los próximos partidos desde la API
        client = APIFootballClient()
        fixtures = client.get_next_fixtures(league_id=league_id, next_n=10)

        if fixtures:
            # Agrupar los partidos por fecha (YYYY-MM-DD)
            fixtures_by_date = {}
            for f in fixtures:
                match_date = f["fixture"]["date"].split("T")[0]
                if match_date not in fixtures_by_date:
                    fixtures_by_date[match_date] = []
                fixtures_by_date[match_date].append(f)

            # 4. Renderizar tarjetas en filas de 3 columnas
            for match_date, matches in fixtures_by_date.items():
                st.markdown(f"#### 🗓️ {match_date}")

                for i in range(0, len(matches), 3):
                    chunk = matches[i:i + 3]
                    cols = st.columns(3)

                    for idx, m in enumerate(chunk):
                        with cols[idx]:
                            home_team = m["teams"]["home"]["name"]
                            away_team = m["teams"]["away"]["name"]
                            match_time = m["fixture"]["date"].split("T")[1][:5]

                            home_fouler = top_foulers.get(home_team)
                            away_fouler = top_foulers.get(away_team)

                            with st.container(border=True):
                                st.caption(f"⏰ {match_time}")

                                # Equipo Local y su Top Infractor
                                col_h1, col_h2 = st.columns([1.1, 1])
                                with col_h1:
                                    st.markdown(f"**{home_team}**")
                                with col_h2:
                                    if home_fouler:
                                        st.caption(f"🔥 {home_fouler['player']} ({home_fouler['fouls_per_90']:.2f}/90m)")
                                    else:
                                        st.caption("—")

                                st.markdown("<small style='color:gray;'>vs</small>", unsafe_allow_html=True)

                                # Equipo Visitante y su Top Infractor
                                col_a1, col_a2 = st.columns([1.1, 1])
                                with col_a1:
                                    st.markdown(f"**{away_team}**")
                                with col_a2:
                                    if away_fouler:
                                        st.caption(f"🔥 {away_fouler['player']} ({away_fouler['fouls_per_90']:.2f}/90m)")
                                    else:
                                        st.caption("—")

                st.divider()
        else:
            st.info(f"No hay partidos programados próximamente para {selected_league}.")


# --- PESTAÑAS DE ANÁLISIS ---
tab1, tab2, tab3 = st.tabs([
    "🔥 Top Probabilidades por Liga", 
    "🎲 Calculadora Individual", 
    "📋 Tabla Predictiva Completa"
])

with tab1:
    st.subheader(f"🔥 Jugadores con Mayor Tasa de Faltas ({selected_league})")
    if not filtered_df.empty:
        top_foulers = filtered_df.sort_values(by="fouls_per_90", ascending=False).head(15)
        fig = px.bar(
            top_foulers,
            x="fouls_per_90",
            y="player_name",
            color="team_name",
            orientation="h",
            labels={"fouls_per_90": "Faltas Cometidas / 90 min", "player_name": "Jugador", "team_name": "Equipo"},
            title=f"Top 15 Mayor Promedio de Faltas/90m ({selected_league})",
            text_auto=".2f"
        )
        fig.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No hay datos disponibles para la liga o filtros seleccionados.")

with tab2:
    st.subheader("🎯 Estimación para un Jugador Específico")
    if not filtered_df.empty:
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            selected_player = st.selectbox("Selecciona un Jugador:", sorted(filtered_df["player_name"].unique()))
        with col_sel2:
            expected_minutes = st.slider("Minutos a jugar en el partido:", 15, 90, 90, step=5)
            
        player_data = filtered_df[filtered_df["player_name"] == selected_player].iloc[0]
        rate_per_90 = player_data["fouls_per_90"]
        lambd = rate_per_90 * (expected_minutes / 90.0)
        
        team_str = f" - {player_data['team_name']}" if 'team_name' in player_data else ""
        st.info(f"**{player_data['player_name']}**{team_str} | Promedio: **{rate_per_90:.2f}** faltas/90m. Para {expected_minutes} min: **λ = {lambd:.2f}** faltas esperadas.")
        
        st.markdown("#### Probabilidades Estimadas de Superar Líneas:")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Más de 0.5 Faltas (1+)", f"{prob_at_least(1, lambd)*100:.1f}%")
        m2.metric("Más de 1.5 Faltas (2+)", f"{prob_at_least(2, lambd)*100:.1f}%")
        m3.metric("Más de 2.5 Faltas (3+)", f"{prob_at_least(3, lambd)*100:.1f}%")
        m4.metric("Más de 3.5 Faltas (4+)", f"{prob_at_least(4, lambd)*100:.1f}%")
    else:
        st.warning("No hay jugadores disponibles con los filtros actuales.")

with tab3:
    st.subheader(f"📋 Ranking Predictivo - {selected_league}")
    if not filtered_df.empty:
        display_df = filtered_df.copy()
        display_df["P(1+ Falta)"] = display_df["fouls_per_90"].apply(lambda l: f"{prob_at_least(1, l)*100:.1f}%")
        display_df["P(2+ Faltas)"] = display_df["fouls_per_90"].apply(lambda l: f"{prob_at_least(2, l)*100:.1f}%")
        display_df["P(3+ Faltas)"] = display_df["fouls_per_90"].apply(lambda l: f"{prob_at_least(3, l)*100:.1f}%")

        columns_to_show = ["player_name", "team_name", "minutes_played", "fouls_committed", "fouls_per_90", "P(1+ Falta)", "P(2+ Faltas)", "P(3+ Faltas)"]
        if "league_name" in display_df.columns:
            columns_to_show.insert(2, "league_name")

        st.dataframe(
            display_df.sort_values(by="fouls_per_90", ascending=False),
            column_config={
                "player_name": "Jugador",
                "team_name": "Equipo",
                "league_name": "Liga",
                "minutes_played": "Min. Jugados",
                "fouls_committed": "Faltas Totales",
                "fouls_per_90": st.column_config.NumberColumn("Faltas/90m", format="%.2f"),
                "P(1+ Falta)": "Prob. 1+ Falta",
                "P(2+ Faltas)": "Prob. 2+ Faltas",
                "P(3+ Faltas)": "Prob. 3+ Faltas"
            },
            column_order=columns_to_show,
            use_container_width=True,
            hide_index=True
        )