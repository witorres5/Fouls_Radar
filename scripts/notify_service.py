# scripts/notify_service.py
import os
import sys
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from databases.connection import DatabaseManager
from services.telegram_services import send_telegram_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def check_and_send_alerts():
    db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
    db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Alerta de Alta Probabilidad (>= 90%) que no hayan sido notificadas
        cursor.execute("""
            SELECT match_name, market, probability, odds, referee 
            FROM simulated_bets 
            WHERE probability >= 90.0 AND (notified_telegram = 0 OR notified_telegram IS NULL)
        """)
        high_profs = cursor.fetchall()
        
        for row in high_profs:
            match = row[0]
            market = row[1]
            prob = float(row[2])
            odds = float(row[3])
            referee = row[4] if len(row) > 4 else "Árbitro no asignado"

            msg = (
                f"🚨 *¡ALERTA DE ALTA CONFIABILIDAD (≥90%)!* 🚨\n\n"
                f"⚽ *Partido:* {match}\n"
                f"👤 *Árbitro:* {referee}\n"
                f"🎯 *Mercado:* {market}\n"
                f"📈 *Probabilidad:* {prob:.1f}%\n"
                f"💰 *Cuota:* {odds:.2f}"
            )
            if send_telegram_message(msg):
                cursor.execute("""
                    UPDATE simulated_bets SET notified_telegram = 1 
                    WHERE match_name = ? AND market = ?
                """, (match, market))
                conn.commit()
                logging.info(f"Notificación enviada para {match} - {market}")
        
    logging.info("Chequeo de notificaciones completado.")

if __name__ == "__main__":
    check_and_send_alerts()