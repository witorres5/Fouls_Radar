import streamlit as st
import plotly.graph_objects as go
from controllers.betting_controller import BettingController
from components.futuristic_ui import get_cyber_plotly_layout

def render_backtesting_dashboard(db_manager, league_id, season):
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h3 style="margin: 0; color: #00F5FF; font-family: 'Space Grotesk', sans-serif;">
            📈 QUANT PERFORMANCE // BACKTESTING & BANKROLL HUD
        </h3>
        <p style="color: #8B949E; margin-top: 4px; font-size: 0.9rem;">
            Métricas de rendimiento acumulado, tasa de acierto y retorno de inversión en tiempo real.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Invocación con auto-evaluación integrada
    data = BettingController.get_performance_metrics(db_manager, league_id, season)

    if not data.get("has_data"):
        st.info("📡 No hay pronósticos evaluados todavía para esta liga y temporada. Sincroniza partidos o evalúa apuestas pendientes.")
        return

    df = data["df"]

    # 1. Tarjetas KPI Cuánticas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Pronósticos", f"{data['total_bets']}")
    with col2:
        st.metric("Win Rate (% Acierto)", f"{data['win_rate']:.1f}%")
    with col3:
        profit_val = data['net_profit']
        st.metric("Beneficio Neto (P/L)", f"${profit_val:,.2f}", delta=f"{profit_val:+,.2f}")
    with col4:
        yield_val = data['yield_pct']
        st.metric("ROI / Yield", f"{yield_val:.2f}%", delta=f"{yield_val:+.2f}%")

    st.markdown("<div style='margin: 20px 0;'></div>", unsafe_allow_html=True)

    # 2. Gráfico Cyberpunk de Curva de Capital (Bankroll Growth)
    st.markdown("##### ⚡ Curva de Rendimiento Acumulado (Profit/Loss)")
    
    fig_bankroll = go.Figure()
    fig_bankroll.add_trace(go.Scatter(
        x=df['match_date'],
        y=df['cumulative_profit'],
        mode='lines+markers',
        name='Bankroll Acumulado',
        line=dict(color='#00F5FF', width=3, shape='spline'),
        marker=dict(size=7, color='#00FFA3', line=dict(color='#060911', width=2)),
        fill='tozeroy',
        fillcolor='rgba(0, 245, 255, 0.08)'
    ))
    
    # Línea cero de referencia
    fig_bankroll.add_hline(y=0, line_dash="dash", line_color="rgba(255, 255, 255, 0.25)")
    
    layout_bankroll = get_cyber_plotly_layout("Crecimiento de Capital ($)")
    fig_bankroll.update_layout(layout_bankroll)
    st.plotly_chart(fig_bankroll, use_container_width=True)

    # 3. Gráficos de distribución y desglose por mercado
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.markdown("##### 🎯 Rendimiento por Tipo de Mercado")
        st.dataframe(data["market_stats"], use_container_width=True)

    with col_right:
        st.markdown("##### 🎲 Distribución de Resultados")
        status_counts = df['status'].value_counts()
        
        color_map = {'GANADA': '#00FFA3', 'PERDIDA': '#FF4B6E', 'ANULADA': '#FFB800'}
        colors = [color_map.get(s, '#00F5FF') for s in status_counts.index]

        fig_donut = go.Figure(data=[go.Pie(
            labels=status_counts.index,
            values=status_counts.values,
            hole=0.55,
            marker=dict(colors=colors, line=dict(color='#060911', width=3)),
            textinfo='percent+label',
            textfont=dict(family="JetBrains Mono", size=12)
        )])
        layout_donut = get_cyber_plotly_layout("Efectividad Global")
        fig_donut.update_layout(layout_donut)
        st.plotly_chart(fig_donut, use_container_width=True)

    # 4. Tabla Detallada
    with st.expander("📝 Detalle de Transacciones Liquidadas"):
        st.dataframe(
            df[['match_date', 'match_name', 'market', 'probability', 'odds', 'status', 'profit']], 
            use_container_width=True
        )

    # 5. Panel de Calibración Platt (Bucle de Retroalimentación)
    st.markdown("---")
    st.markdown("##### 🎚️ Calibración Platt Scaling (Retroalimentación Real)")
    cal_info = BettingController.get_calibrator_info()

    if cal_info.get("available"):
        st.caption(
            f"Entrenado: **{cal_info.get('trained_at', cal_info.get('last_modified'))}** "
            f"| Muestras: **{cal_info.get('n_samples', 0)}** "
            f"| Win Rate real: **{cal_info.get('win_rate_real', 0)}%** "
            f"| Brier: **{cal_info.get('brier', 0)}**"
        )
        cur_col, btn_col = st.columns([2, 1])
        with cur_col:
            st.caption(f"Prob. promedio antes: {cal_info.get('avg_pred_old')}% → nueva: {cal_info.get('avg_pred_new')}%")
        with btn_col:
            if st.button("♻️ Reentrenar Calibrador", use_container_width=True, key="btn_retrain_calibrator"):
                with st.spinner("Entrenando calibrador con resultados reales..."):
                    r = BettingController.train_calibrator(db_manager)
                if r.get("success"):
                    st.success(f"Calibrador actualizado: {r['n_samples']} muestras | Brier {r['brier']}")
                    st.rerun()
                else:
                    st.warning(r.get("message", "No se pudo reentrenar."))
    else:
        est_col, btn_col = st.columns([2, 1])
        with est_col:
            st.info(f"⚙️ Calibrador no entrenado. Se activa con apuestas evaluadas ({cal_info.get('message', '')})")
        with btn_col:
            if st.button("🎯 Entrenar Calibrador", use_container_width=True, key="btn_train_calibrator"):
                with st.spinner("Entrenando calibrador Platt..."):
                    r = BettingController.train_calibrator(db_manager)
                if r.get("success"):
                    st.success(f"Calibrador entrenado: {r['n_samples']} muestras | Win rate {r['win_rate_real']}% | Brier {r['brier']}")
                    st.rerun()
                else:
                    st.error(r.get("message", "No se pudo entrenar el calibrador."))

    deciles = cal_info.get("deciles")
    if cal_info.get("available") and deciles:
        with st.expander("📊 Curva de Calibración (Predicho vs Real por Quintil)"):
            st.dataframe(deciles, use_container_width=True)