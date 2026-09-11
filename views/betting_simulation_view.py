# views/betting_simulation_view.py
import streamlit as st
from controllers.betting_controller import BettingController
from components.futuristic_ui import render_hologram_pick_card

def render_betting_simulation_view(db_manager, league_id, season):
    st.markdown("""
    <div style="margin-bottom: 16px;">
        <h3 style="margin: 0; color: #00F5FF; font-family: 'Space Grotesk', sans-serif;">
            🤖 SIMULADOR CUÁNTICO // PICKS DE ALTA CONFIANZA (&gt;80%)
        </h3>
        <p style="color: #8B949E; margin-top: 4px; font-size: 0.9rem;">
            Motor probabilístico multidimensional que analiza rigurosidad arbitral, perfiles F90 y fricción de equipo.
        </p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["💡 PICKS DETECTADOS (&gt;80%)", "📊 HISTORIAL & LIQUIDACIONES"])

    with tab1:
        st.markdown("##### ⚡ Oportunidades Identificadas para las Próximas Jornadas")
        picks = BettingController.get_high_probability_bets(db_manager, league_id, season)

        if picks:
            from databases.betting_repository import BettingRepository
            betting_repo = BettingRepository(db_manager)

            for idx, pick in enumerate(picks):
                col_card, col_action = st.columns([4, 1.2])
                with col_card:
                    render_hologram_pick_card(
                        match_name=pick['match_name'],
                        referee=pick['referee'],
                        market=pick['market'],
                        probability=pick['probability'],
                        odds=pick['odds'],
                        model_used=pick.get('model_used', '🤖 ML (PoissonRegressor)')
                    )
                with col_action:
                    st.write("")
                    st.write("")
                    is_already_saved = betting_repo.exists_bet(league_id, season, pick['match_name'], pick['market'])
                    if is_already_saved:
                        st.button("✅ En Historial", key=f"sim_btn_{idx}Y", disabled=True, use_container_width=True)
                    else:
                        if st.button("💾 Simular", key=f"sim_btn_{idx}Y", use_container_width=True):
                            with st.spinner("Registrando pronóstico en el historial..."):
                                BettingController.save_simulation(db_manager, pick)
                            st.toast(f"✅ ¡Pronóstico registrado para {pick['match_name']}!", icon="🎯")
                            st.rerun()
        else:
            st.warning("📡 No hay partidos próximos en los siguientes 3 días que superen el umbral de >80% de probabilidad.")



    with tab2:
        col_head, col_eval = st.columns([3, 1.5])
        with col_head:
            st.markdown("#### Historial de Apuestas Simuladas")
        with col_eval:
            if st.button("⚡ Evaluar Pendientes", key="btn_eval_sims", use_container_width=True):
                with st.spinner("Evaluando pronósticos pendientes con resultados de partidos..."):
                    res = BettingController.evaluate_pending_bets(db_manager, league_id, season)
                if res.get("evaluated", 0) > 0:
                    st.success(f"✅ ¡{res['evaluated']} pronósticos evaluados! (Ganados: {res['won']} | Perdidos: {res['lost']})")
                    st.rerun()
                else:
                    st.info("No hay pronósticos con partidos finalizados pendientes de evaluar.")

        df_history = BettingController.get_history_df(db_manager, league_id, season)

        if not df_history.empty:
            st.dataframe(df_history, use_container_width=True)
            
            # Botón de exportación a CSV
            csv_data = df_history.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Historial en CSV",
                data=csv_data,
                file_name="historial_apuestas_simuladas.csv",
                mime="text/csv"
            )
        else:
            st.info("Aún no tienes apuestas simuladas registradas.")