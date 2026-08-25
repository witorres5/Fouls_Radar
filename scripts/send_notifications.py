# scripts/send_notifications.py
import os
import logging
from databases.connection import DatabaseManager
from services.telegram_services import send_telegram_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def send_daily_report_and_alerts():
    db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
    db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Alerta de Alta Probabilidad (> 95%) no notificadas
        cursor.execute("""
            SELECT match_name, market, probability, simulated_odds 
            FROM simulated_bets 
            WHERE probability >= 0.95 AND notified_telegram = 0
        """)
        high_profs = cursor.fetchall()
        
        for match, market, prob, odds in high_profs:
            msg = (
                f"🚨 *¡ALERTA DE ALTA CONFIABILIDAD (>95%)!* 🚨\n\n"
                f"⚽ *Partido:* {match}\n"
                f"🎯 *Mercado:* {market}\n"
                f"📈 *Probabilidad:* {prob * 100:.1f}%\n"
                f"💰 *Cuota:* {odds}"
            )
            if send_telegram_message(msg):
                cursor.execute("""
                    UPDATE simulated_bets SET notified_telegram = 1 
                    WHERE match_name = ? AND market = ?
                """, (match, market))
                conn.commit()

        # 2. Resumen del día (Apuestas generadas, ganadas y perdidas)
        # Puedes filtrar por la fecha actual si tienes una columna de timestamp, o un acumulado reciente
        cursor.execute("""
            SELECT status, COUNT(*) FROM simulated_bets 
            GROUP BY status
        """)
        summary = cursor.fetchall()
        
        summary_text = "📊 *REPORTE DIARIO DE APUESTAS* 📊\n\n"
        for status, count in summary:
            summary_text += f"• *{status}:* {count}\n"
            
        # Enviamos el reporte periódico
        send_telegram_message(summary_text)

    logging.info("Notificaciones y reportes enviados con éxito.")

if __name__ == "__main__":
    send_daily_report_and_alerts()