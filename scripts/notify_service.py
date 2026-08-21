# scripts/notify_service.py
import os
import logging
from databases.connection import DatabaseManager
from services.telegram_bot import send_telegram_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def check_and_send_alerts():
    db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
    auth_token = os.environ.get("TELEGRAM_AUTH_TOKEN", "") # O tu token de turso si aplica
    db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
# 1. Alerta de Alta Probabilidad (> 95%) que no hayan sido notificadas
        cursor.execute("""
            SELECT match_name, market, probability, simulated_odds 
            FROM simulated_bets 
            WHERE probability >= 0.95 AND notified_telegram = 0
        """)
        high_profs = cursor.fetchall()
        
        for match, market, prob, odds in high_profs: # <--- Aquí corregimos el "in"
            msg = (
                f"🚨 *¡ALERTA DE ALTA CONFIABILIDAD (>95%)!* 🚨\n\n"
                f"⚽ *Partido:* {match}\n"
                f"🎯 *Mercado:* {market}\n"
                f"📈 *Probabilidad:* {prob * 100:.1f}%\n"
                f"💰 *Cuota:* {odds}"
            )
            if send_telegram_message(msg):
                # Marcamos como notificado para no repetir
                cursor.execute("""
                    UPDATE simulated_bets SET notified_telegram = 1 
                    WHERE match_name = ? AND market = ?
                """, (match, market))
                conn.commit()

        # 2. Reporte periódico (Puedes controlarlo con una bandera o ejecutándolo en horarios específicos con cron)
        # Aquí puedes consultar un resumen de las ganadas/perdidas del día y enviar el parte diario.
        
    logging.info("Chequeo de notificaciones completado.")

if __name__ == "__main__":
    check_and_send_alerts()