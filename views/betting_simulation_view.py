# views/betting_simulation_view.py
import streamlit as st
from controllers.betting_controller import BettingController

def render_betting_simulation_view(db_manager, league_id, season):
    st.markdown("### 🤖 Módulo de Apuestas Simuladas (Alta Probabilidad >80%)")
    st.info("Este módulo analiza el comportamiento arbitral y el volumen de faltas para sugerir pronósticos automatizados de alta confianza.")

    tab1, tab2 = st.tabs(["💡 Picks Sugeridos (>80%)", "📊 Historial de Simulaciones"])

    with tab1:
        st.markdown("#### Oportencias Detectadas para las Próximas Jornadas")
        picks = BettingController.get_high_probability_bets(db_manager, league_id, season)

        if picks:
            for idx, pick in enumerate(picks):
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        st.markdown(f"**⚽ {pick['match_name']}**")
                        st.caption(f"👤 Árbitro: {pick['referee']}")
                    with col2:
                        st.markdown(f"🎯 **Mercado:** {pick['market']}")
                        st.markdown(f"🔥 **Probabilidad:** :green[**{pick['probability']}%**]")
                    with col3:
                        st.markdown(f"📈 **Cuota:** {pick['odds']}")
                        if st.button("Simular Apuesta", key=f"sim_btn_{idx}Y"):
                            BettingController.save_simulation(db_manager, pick)
                            st.success("¡Apuesta guardada en el historial!")
        else:
            st.warning("No hay suficientes partidos próximos que cumplan el filtro de >80% de probabilidad en este momento.")

    with tab2:
        st.markdown("#### Historial de Apuestas Simuladas")
        df_history = BettingController.get_history_df(db_manager, league_id, season)

        if not df_history.empty:
            st.dataframe(df_history, use_container_width=True)
            
            # Botón de exportación a CSV (Punto 3)
            csv_data = df_history.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Historial en CSV",
                data=csv_data,
                file_name="historial_apuestas_simuladas.csv",
                mime="text/csv"
            )
        else:
            st.info("Aún no tienes apuestas simuladas registradas.")