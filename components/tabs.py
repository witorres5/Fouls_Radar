import plotly.express as px
import streamlit as st
from core.math_utils import prob_at_least
from components.bets_dashboard import render_bets_tracker_tab

def render_analysis_tabs(filtered_df, selected_league: str, min_edge: float = 1.5, client=None):
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔥 Top Probabilidades por Liga", 
        "🎲 Calculadora Individual", 
        "📋 Tabla Predictiva Completa",
        "🤖 Auto-Apuestas y Balance"
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
            league_mean = display_df["fouls_per_90"].mean()
            
            # Lógica de ventaja según el margen seleccionado en el slider
            display_df["Ventaja vs Liga"] = display_df["fouls_per_90"] - league_mean
            display_df["Sugerencia Auto"] = display_df["Ventaja vs Liga"].apply(
                lambda edge: "🔥 Alta Ventaja" if edge >= min_edge else ("⚡ Destacado" if edge >= (min_edge / 2) else "Normal")
            )

            display_df["P(1+ Falta)"] = display_df["fouls_per_90"].apply(lambda l: f"{prob_at_least(1, l)*100:.1f}%")
            display_df["P(2+ Faltas)"] = display_df["fouls_per_90"].apply(lambda l: f"{prob_at_least(2, l)*100:.1f}%")
            display_df["P(3+ Faltas)"] = display_df["fouls_per_90"].apply(lambda l: f"{prob_at_least(3, l)*100:.1f}%")

            columns_to_show = ["player_name", "team_name", "fouls_per_90", "Sugerencia Auto", "P(1+ Falta)", "P(2+ Faltas)", "P(3+ Faltas)"]

            st.dataframe(
                display_df.sort_values(by="fouls_per_90", ascending=False),
                column_config={
                    "player_name": "Jugador",
                    "team_name": "Equipo",
                    "fouls_per_90": st.column_config.NumberColumn("Faltas/90m", format="%.2f"),
                    "Sugerencia Auto": "Auto-Simulador",
                    "P(1+ Falta)": "Prob. 1+",
                    "P(2+ Faltas)": "Prob. 2+",
                    "P(3+ Faltas)": "Prob. 3+"
                },
                column_order=columns_to_show,
                use_container_width=True,
                hide_index=True
            )
            
    with tab4:
        # Renderiza el panel de apuestas guardadas y balance
        render_bets_tracker_tab(client=client)