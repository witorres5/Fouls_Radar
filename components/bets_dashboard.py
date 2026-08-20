import streamlit as st
import pandas as pd
import libsql
from core.reconciliation import reconcile_daily_bets

def render_bets_tracker_tab(client=None):
    st.subheader("🤖 Panel de Auto-Apuestas y Balance")

    # Botón para forzar verificación manual de resultados
    c_left, c_right = st.columns([4, 1])
    with c_right:
        if st.button("🔄 Verificadores / Reconciliar", use_container_width=True):
            if client:
                msg = reconcile_daily_bets(client)
                st.toast(msg, icon="⚽")
                st.rerun()

    # Lectura directamente desde Turso / LibSQL
    try:
        turso_url = st.secrets["TURSO_DATABASE_URL"]
        turso_token = st.secrets["TURSO_AUTH_TOKEN"]
        
        conn = libsql.connect(database=turso_url, auth_token=turso_token)
        df_bets = pd.read_sql_query("SELECT * FROM auto_bets ORDER BY id DESC", conn)
        conn.close()
    except Exception as e:
        st.warning(f"No se pudieron cargar las apuestas desde Turso: {e}")
        return

    if df_bets.empty:
        st.info("Aún no hay apuestas registradas en la base de datos.")
        return

    # Métrica de Profit considerando Stake de 10 unidades por apuesta y cuota base
    df_bets['odds_calc'] = df_bets['odds'].apply(lambda x: x if x and x > 1.0 else 1.85)
    
    evaluated = df_bets[df_bets["status"].isin(["WON", "LOST"])]
    total_bets = len(evaluated)
    won_bets = len(df_bets[df_bets["status"] == "WON"])
    
    # Cálculo de Ganancia/Pérdida (Stake unitario = $10)
    stk = 10.0
    profit = 0.0
    for idx, row in evaluated.iterrows():
        if row["status"] == "WON":
            profit += (stk * row["odds_calc"]) - stk
        elif row["status"] == "LOST":
            profit -= stk

    win_rate = (won_bets / total_bets * 100) if total_bets > 0 else 0.0

    # KPIs Principales
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Apuestas Evaluadas", total_bets)
    m2.metric("Acertadas", won_bets)
    m3.metric("Tasa de Acierto", f"{win_rate:.1f}%")
    m4.metric("Balance Estimado", f"${profit:+.2f}", delta_color="normal" if profit >= 0 else "inverse")

    st.divider()

    # Tabla Interactiva Formateada
    st.dataframe(
        df_bets,
        column_config={
            "id": "ID",
            "fixture_id": None, # Ocultar columna técnica
            "created_at": None,
            "odds": None,       # Ocultar columna cruda de odds si usas odds_calc
            "match_date": "Fecha",
            "home_team": "Local",
            "away_team": "Visitante",
            "player_name": "Jugador",
            "bet_line": "Línea",
            "tier": "Categoría",
            "probability": st.column_config.NumberColumn("Prob. Modelo", format="%.1f%%"),
            "odds_calc": st.column_config.NumberColumn("Cuota Est.", format="%.2f"),
            "status": st.column_config.SelectboxColumn("Estado", options=["PENDING", "WON", "LOST"]),
            "actual_fouls": st.column_config.NumberColumn("Faltas Reales", format="%d")
        },
        use_container_width=True,
        hide_index=True
    )