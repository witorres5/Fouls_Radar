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