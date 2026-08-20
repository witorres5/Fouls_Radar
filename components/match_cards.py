import streamlit as st
from core.api_client import APIFootballClient
from core.predictor import calculate_match_fouls_projection
from config.constants import TARGET_LEAGUES
from database.data_loader import db, get_team_top_foulers

def render_referee_and_projection_card(db_manager, fixture_data, home_avg, away_avg, league_avg):
    referee_name = fixture_data.get("referee")
    st.markdown("### ⚖️ Análisis del Árbitro y Proyección")
    
    referee_stats = db_manager.get_referee(referee_name) if referee_name else None
    referee_fouls_avg = None
    
    if referee_stats:
        matches_count, referee_fouls_avg = referee_stats
        st.info(f"👤 **Árbitro:** {referee_name} ({matches_count} partidos dirigidos | Promedio: **{referee_fouls_avg:.1f}** faltas/partido)")
    elif referee_name:
        st.warning(f"👤 **Árbitro:** {referee_name} *(Sin historial acumulado en base de datos)*")
    else:
        st.caption("👤 **Árbitro:** No designado aún")

    projection = calculate_match_fouls_projection(
        home_fouls_avg=home_avg,
        away_fouls_avg=away_avg,
        league_fouls_avg=league_avg,
        referee_fouls_avg=referee_fouls_avg
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Proyección Base (Equipos)", f"{projection['base_projection']} faltas")
    
    ratio = projection['referee_ratio']
    delta_pct = round((ratio - 1.0) * 100, 1)
    col2.metric("Impacto Árbitro", f"{ratio:.2f}x", delta=f"{delta_pct}%" if ratio != 1.0 else "Neutro")
    col3.metric("Proyección Final Ajustada", f"{projection['adjusted_projection']} faltas")

    impact = projection['referee_impact']
    if impact == "HIGH_FOULS":
        st.error("🔥 **Tendencia:** Árbitro riguroso. Incrementa la probabilidad de OVER en faltas y tarjetas.")
    elif impact == "LOW_FOULS":
        st.success("🟢 **Tendencia:** Árbitro permisivo. Favorece líneas UNDER en faltas.")
    else:
        st.caption("⚖️ **Tendencia:** Criterio dentro de la media de la liga.")

def render_upcoming_matches(selected_league: str, selected_season: int, filtered_df, api_client: APIFootballClient):
    if selected_league == "Todas":
        return

    st.markdown("### 📅 Próximos Partidos")
    league_id = next((l_id for l_id, info in TARGET_LEAGUES.items() if info["name"] == selected_league), None)

    if not league_id:
        return

    top_foulers = get_team_top_foulers(league_id, selected_season)
    fixtures = api_client.get_next_fixtures(league_id=league_id, next_n=10)
    league_avg = filtered_df["fouls_per_90"].mean() if not filtered_df.empty else 12.0

    if not fixtures:
        st.info(f"No hay partidos programados próximamente para {selected_league}.")
        return

    fixtures_by_date = {}
    for f in fixtures:
        match_date = f["fixture"]["date"].split("T")[0]
        fixtures_by_date.setdefault(match_date, []).append(f)

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

                    home_df = filtered_df[filtered_df["team_name"] == home_team]
                    away_df = filtered_df[filtered_df["team_name"] == away_team]

                    home_avg = home_df["fouls_per_90"].sum() if not home_df.empty else 10.0
                    away_avg = away_df["fouls_per_90"].sum() if not away_df.empty else 10.0

                    with st.container(border=True):
                        st.caption(f"⏰ {match_time}")
                        col_h1, col_h2 = st.columns([1.1, 1])
                        col_h1.markdown(f"**{home_team}**")
                        col_h2.caption(f"🔥 {home_fouler['player']} ({home_fouler['fouls_per_90']:.2f}/90m)" if home_fouler else "—")

                        st.markdown("<small style='color:gray;'>vs</small>", unsafe_allow_html=True)

                        col_a1, col_a2 = st.columns([1.1, 1])
                        col_a1.markdown(f"**{away_team}**")
                        col_a2.caption(f"🔥 {away_fouler['player']} ({away_fouler['fouls_per_90']:.2f}/90m)" if away_fouler else "—")

                        st.divider()

                        render_referee_and_projection_card(
                            db_manager=db,
                            fixture_data={"referee": m["fixture"].get("referee")},
                            home_avg=home_avg,
                            away_avg=away_avg,
                            league_avg=league_avg
                        )
        st.divider()