# core/reconciliation.py
import logging
from database.data_loader import get_db_client
from core.notifications import send_telegram_alert

logger = logging.getLogger("FoulsTracker.Reconciliation")

def reconcile_daily_bets(api_client):
    """
    Verifica las apuestas PENDING en Turso contra la API de resultados,
    actualiza los estados (WON/LOST) y envía un resumen detallado a Telegram.
    """
    client = get_db_client()
    if not client:
        return "Error al conectar a la base de datos."

    try:
        # 1. Obtener apuestas pendientes
        res = client.execute("SELECT id, fixture_id, player_name, bet_line, status FROM auto_bets WHERE status = 'PENDING'")
        pending_bets = res.rows

        if not pending_bets:
            msg = "ℹ️ *Reconciliación Diaria*\n\nNo hay apuestas pendientes por verificar."
            send_telegram_alert(msg)
            return "No hay apuestas pendientes."

        won_count = 0
        lost_count = 0
        updated_count = 0

        # 2. Procesar cada apuesta pendiente
        for row in pending_bets:
            bet_id, fixture_id, player_name, bet_line, _ = row
            
            # Consultar estadísticas del partido en la API
            # (Ajusta según tu método de consulta de fixtures/player stats en api_client)
            fixture_stats = api_client.get_fixture_player_stats(fixture_id) if hasattr(api_client, 'get_fixture_player_stats') else None

            if fixture_stats:
                player_fouls = fixture_stats.get(player_name, None)
                if player_fouls is not None:
                    # Determinar si ganó según la línea (+0.5 -> 1+, +1.5 -> 2+)
                    target_fouls = 1 if "0.5" in bet_line or "1+" in bet_line else 2
                    new_status = "WON" if player_fouls >= target_fouls else "LOST"

                    client.execute(
                        "UPDATE auto_bets SET status = ?, actual_fouls = ? WHERE id = ?",
                        [new_status, player_fouls, bet_id]
                    )

                    updated_count += 1
                    if new_status == "WON":
                        won_count += 1
                    else:
                        lost_count += 1

        # 3. Obtener el acumulado histórico total de la BD para el reporte global
        stats_res = client.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'WON' THEN 1 ELSE 0 END) as won,
                SUM(CASE WHEN status = 'LOST' THEN 1 ELSE 0 END) as lost,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending
            FROM auto_bets
        """)
        
        row_stats = stats_res.rows[0]
        total_all, won_all, lost_all, pending_all = row_stats[0], row_stats[1] or 0, row_stats[2] or 0, row_stats[3] or 0
        
        total_settled = won_all + lost_all
        win_rate = (won_all / total_settled * 100) if total_settled > 0 else 0.0

        # 4. Construir y enviar mensaje detallado a Telegram
        msg = (
            f"📊 *REPORTE DE RECONCILIACIÓN DIARIA*\n\n"
            f"🔄 *Procesadas Hoy:* {updated_count}\n"
            f"✅ *Ganadas Hoy:* {won_count}\n"
            f"❌ *Perdidas Hoy:* {lost_count}\n\n"
            f"📈 *ESTADÍSTICAS TOTALES ACUMULADAS*\n"
            f"🟢 *Ganadas:* {won_all}\n"
            f"🔴 *Perdidas:* {lost_all}\n"
            f"⏳ *Pendientes:* {pending_all}\n"
            f"🎯 *Win Rate:* `{win_rate:.1f}%`"
        )

        send_telegram_alert(msg)
        return f"Reconciliación completada. Ganadas hoy: {won_count}, Perdidas hoy: {lost_count}"

    except Exception as e:
        logger.error(f"Error en reconciliación: {e}")
        return f"Error en la reconciliación: {e}"