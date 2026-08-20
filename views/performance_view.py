# views/performance_view.py
import streamlit as st
import pandas as pd
import plotly.express as px
from database.data_loader import get_db_client

def render_performance_dashboard():
    st.title("📈 Performance y Rentabilidad (ROI / Yield)")
    st.caption("Análisis cuantitativo de las apuestas automáticas registradas.")

    client = get_db_client()
    if not client:
        st.error("No se pudo conectar a la base de datos Turso.")
        return

    # 1. Cargar todas las apuestas
    try:
        res = client.execute("""
            SELECT id, fixture_id, match_date, home_team, away_team, 
                   player_name, bet_line, tier, probability, status, actual_fouls
            FROM auto_bets
            ORDER BY match_date DESC
        """)
        
        cols = ["id", "fixture_id", "match_date", "home_team", "away_team", 
                "player_name", "bet_line", "tier", "probability", "status", "actual_fouls"]
        
        rows = res.rows if hasattr(res, 'rows') else res.fetchall()
        df = pd.DataFrame(rows, columns=cols)
    except Exception as e:
        st.error(f"Error cargando datos de auto_bets: {e}")
        return

    if df.empty:
        st.info("Aún no hay apuestas automáticas registradas en el sistema.")
        return

    # Cuota promedio estándar y stake fijo de 1 unidad por apuesta
    FLAT_ODDS = 1.85
    FLAT_STAKE = 1.0

    # Filtrar apuestas resueltas (incluyendo VOID)
    df_settled = df[df["status"].isin(["WON", "LOST", "VOID"])].copy()
    
    # Ordenar por fecha ascendente para cálculo acumulado
    df_settled["match_date"] = pd.to_datetime(df_settled["match_date"])
    df_settled = df_settled.sort_values("match_date")

    # Profit individual: WON = +(odds - 1), LOST = -1, VOID = 0
    def calculate_profit(status):
        if status == "WON":
            return (FLAT_ODDS - 1.0) * FLAT_STAKE
        elif status == "LOST":
            return -FLAT_STAKE
        return 0.0  # Estado VOID devuelven el stake

    df_settled["profit"] = df_settled["status"].apply(calculate_profit)
    df_settled["cum_profit"] = df_settled["profit"].cumsum()

    # Métricas Globales
    total_bets = len(df)
    won_bets = len(df_settled[df_settled["status"] == "WON"])
    lost_bets = len(df_settled[df_settled["status"] == "LOST"])
    void_bets = len(df_settled[df_settled["status"] == "VOID"])
    pending_bets = len(df[df["status"] == "PENDING"])

    # El Win Rate y Total Staked solo toman en cuenta las apuestas efectivas (WON + LOST)
    effective_settled = won_bets + lost_bets
    win_rate = (won_bets / effective_settled * 100) if effective_settled > 0 else 0.0
    
    total_profit = df_settled["profit"].sum() if len(df_settled) > 0 else 0.0
    total_staked = effective_settled * FLAT_STAKE
    yield_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0.0

    # 2. Tarjetas KPI Superior
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Total Apuestas", total_bets, f"{pending_bets} pend. | {void_bets} void")
    kpi2.metric("Win Rate Efectivo", f"{win_rate:.1f}%", f"{won_bets}W - {lost_bets}L")
    kpi3.metric("Beneficio Neto", f"{total_profit:+.2f} u", delta=f"{total_profit:+.2f} u")
    kpi4.metric("Yield / ROI", f"{yield_pct:+.1f}%")
    kpi5.metric("Cuota Promedio", f"{FLAT_ODDS:.2f}")

    st.markdown("---")

    # 3. Gráfico de Evolución de Bankroll / Unidades
    st.subheader("📉 Evolución del Bankroll (Acumulado de Unidades)")
    if not df_settled.empty:
        fig_bankroll = px.line(
            df_settled,
            x="match_date",
            y="cum_profit",
            markers=True,
            labels={"match_date": "Fecha", "cum_profit": "Unidades (+u / -u)"},
            title="Curva de Rendimiento Acumulado"
        )
        fig_bankroll.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_bankroll, use_container_width=True)
    else:
        st.info("Esperando resolución de partidos para graficar la curva de ganancias.")

    # 4. Rendimiento Desglosado por Nivel (Tier)
    st.subheader("🎯 Rendimiento por Nivel (Tier)")
    if not df_settled.empty:
        tier_summary = df_settled.groupby("tier").agg(
            Total=("id", "count"),
            Ganadas=("status", lambda x: (x == "WON").sum()),
            Perdidas=("status", lambda x: (x == "LOST").sum()),
            Nulas=("status", lambda x: (x == "VOID").sum()),
            Profit=("profit", "sum")
        ).reset_index()

        tier_summary["Efectivas"] = tier_summary["Ganadas"] + tier_summary["Perdidas"]
        tier_summary["Win Rate %"] = tier_summary.apply(
            lambda r: round((r["Ganadas"] / r["Efectivas"] * 100), 1) if r["Efectivas"] > 0 else 0.0, 
            axis=1
        )
        st.dataframe(
            tier_summary[["tier", "Total", "Ganadas", "Perdidas", "Nulas", "Win Rate %", "Profit"]],
            use_container_width=True
        )

    # 5. Tabla con Detalle Histórico completo
    st.subheader("📋 Historial de Apuestas Registradas")
    st.dataframe(
        df[["match_date", "home_team", "away_team", "player_name", "bet_line", "tier", "probability", "actual_fouls", "status"]],
        use_container_width=True
    )