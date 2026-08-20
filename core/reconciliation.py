# core/reconciliation.py
import logging
from database.data_loader import get_db_client
from core.notifications import send_telegram_alert

logger = logging.getLogger("FoulsTracker.Reconciliation")

def reconcile_daily_bets(api_client=None):
    """
    Verifica las apuestas PENDING en Turso contra la API de resultados,
    gestiona estados (WON/LOST/VOID) considerando minutos jugados,
    actualiza la BD y envía un resumen detallado a Telegram.
    """
    client = get_db_client()
    if not client:
        return "Error al conectar a la base de datos."

    try:
        cursor = client.cursor() if hasattr(client, 'cursor') else client

        # 1. Obtener apuestas pendientes
        cursor.execute("SELECT id, fixture_id, player_name, bet_line, status FROM auto_bets WHERE status = 'PENDING'")
        pending_bets = cursor.fetchall() if hasattr(cursor, 'fetchall') else getattr(cursor, 'rows', [])

        if not pending_bets:
            msg = "ℹ️ *Reconciliación Diaria*\n\nNo hay apuestas pendientes por verificar."
            send_telegram_alert(msg)
            return "No hay apuestas pendientes."

        won_count = 0
        lost_count = 0
        void_count = 0
        updated_count = 0

        # 2. Procesar cada apuesta pendiente
        for row in pending_bets:
            bet_id, fixture_id, player_name, bet_line, _ = row
            
            fixture_stats = api_client.get_fixture_player_stats(fixture_id) if (api_client and hasattr(api_client, 'get_fixture_player_stats')) else None

            if fixture_stats:
                # Se asume que fixture_stats puede retornar dict con 'fouls' y 'minutes' o el int directo
                p_data = fixture_stats.get(player_name, None)
                
                if p_data is not None:
                    if isinstance(p_data, dict):
                        player_fouls = p_data.get("fouls", 0)
                        player_minutes = p_data.get("minutes", 0)
                    else:
                        player_fouls = p_data
                        player_minutes = 90  # Fallback si la API solo retorna número directo de faltas

                    # CASO VOID: Si el jugador no disputó el partido (0 minutos)
                    if player_minutes == 0 or player_minutes is None:
                        new_status = "VOID"
                        actual_fouls = 0
                        void_count += 1
                    else:
                        actual_fouls = player_fouls
                        target_fouls = 1 if ("0.5" in str(bet_line) or "1+" in str(bet_line)) else 2
                        
                        if player_fouls >= target_fouls:
                            new_status = "WON"
                            won_count += 1
                        else:
                            new_status = "LOST"
                            lost_count += 1

                    cursor.execute(
                        "UPDATE auto_bets SET status = ?, actual_fouls = ? WHERE id = ?",
                        (new_status, actual_fouls, bet_id)
                    )
                    updated_count += 1

        if hasattr(client, 'commit'):
            client.commit()

        # 3. Obtener el acumulado histórico total de la BD
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'WON' THEN 1 ELSE 0 END) as won,
                SUM(CASE WHEN status = 'LOST' THEN 1 ELSE 0 END) as lost,
                SUM(CASE WHEN status = 'VOID' THEN 1 ELSE 0 END) as void,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending
            FROM auto_bets
        """)
        
        row_stats = cursor.fetchone() if hasattr(cursor, 'fetchone') else (0, 0, 0, 0, 0)
        total_all = row_stats[0]
        won_all = row_stats[1] or 0
        lost_all = row_stats[2] or 0
        void_all = row_stats[3] or 0
        pending_all = row_stats[4] or 0
        
        # El Win Rate se calcula únicamente sobre apuestas resueltas efectivas (WON + LOST)
        total_settled_effective = won_all + lost_all
        win_rate = (won_all / total_settled_effective * 100) if total_settled_effective > 0 else 0.0

        # 4. Construir y enviar mensaje a Telegram
        msg = (
            f"📊 *REPORTE DE RECONCILIACIÓN DIARIA*\n\n"
            f"🔄 *Procesadas Hoy:* {updated_count}\n"
            f"✅ *Ganadas Hoy:* {won_count}\n"
            f"❌ *Perdidas Hoy:* {lost_count}\n"
            f"⚪ *Nulas/Canceladas (VOID) Hoy:* {void_count}\n\n"
            f"📈 *ESTADÍSTICAS TOTALES ACUMULADAS*\n"
            f"🟢 *Ganadas:* {won_all}\n"
            f"🔴 *Perdidas:* {lost_all}\n"
            f"⚪ *Nulas (VOID):* {void_all}\n"
            f"⏳ *Pendientes:* {pending_all}\n"
            f"🎯 *Win Rate Efectivo:* `{win_rate:.1f}%`"
        )

        send_telegram_alert(msg)
        return f"Reconciliación completada. Ganadas: {won_count}, Perdidas: {lost_count}, VOID: {void_count}"

    except Exception as e:
        logger.error(f"Error en reconciliación: {e}")
        send_telegram_alert(f"📌 *Estado:* Error en la reconciliación: {e}")
        return f"Error en la reconciliación: {e}"