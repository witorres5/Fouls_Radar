# views/backtesting_view.py
import streamlit as st
import plotly.express as px
from databases.betting_repository import BettingRepository
from controllers.backtesting_controller import BacktestingController

def render_backtesting_dashboard(db_manager, league_id, season):
    st.title("📈 Módulo de Backtesting & Performance de Bankroll")

    # Inyección de dependencias
    repository = BettingRepository(db_manager)
    controller = BacktestingController(repository)

    # Obtención de datos procesados
    data = controller.get_performance_metrics(league_id, season)

    if not data["has_data"]:
        st.warning("⚠️ No hay apuestas evaluadas aún para generar métricas de backtesting.")
        return

    df = data["df"]

    # 1. Tarjetas KPI
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Apuestas Evaluadas", data["total_bets"])
    col2.metric("Win Rate (% Acierto)", f"{data['win_rate']:.1f}%")
    col3.metric("Beneficio Neto", f"${data['net_profit']:,.2f}", delta=f"{data['net_profit']:,.2f}")
    col4.metric("Yield", f"{data['yield_pct']:.2f}%", delta=f"{data['yield_pct']:.2f}%")

    st.markdown("---")

    # 2. Gráfico Curva de Rendimiento
    st.subheader("📊 Curva de Rendimiento Acumulado (Profit/Loss)")
    fig_bankroll = px.line(
        df, 
        x='match_date', 
        y='cumulative_profit',
        title="Crecimiento del Capital a lo largo del tiempo",
        labels={'match_date': 'Fecha', 'cumulative_profit': 'Beneficio Acumulado ($)'},
        markers=True
    )
    fig_bankroll.add_hline(y=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_bankroll, use_container_width=True)

    # 3. Gráficos de distribución y desglose por mercado
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🎯 Rendimiento por Tipo de Mercado")
        st.dataframe(data["market_stats"], use_container_width=True)

    with col_right:
        st.subheader("🎲 Distribución de Resultados")
        fig_pie = px.pie(
            df, 
            names='status', 
            title='Efectividad Global', 
            color='status',
            color_discrete_map={'GANADA': '#2ecc71', 'PERDIDA': '#e74c3c'}
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # 4. Tabla Detallada
    with st.expander("📝 Ver Detalle de Apuestas Evaluadas"):
        st.dataframe(
            df[['match_date', 'match_name', 'market', 'probability', 'odds', 'status', 'profit']], 
            use_container_width=True
        )