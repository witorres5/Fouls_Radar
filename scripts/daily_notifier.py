import os
import sys
import logging
from datetime import datetime
import pytz

# Asegurar path de los módulos raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from databases.connection import DatabaseManager 
from controllers.betting_controller import BettingController
from services.telegram_services import TelegramNotifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    try:
        # Configurar conexión (Soporta local y variables de entorno)
        db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
        auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
        db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
        
        # Obtener fecha actual en zona horaria de Colombia
        colombia_tz = pytz.timezone('America/Bogota')
        today_str = datetime.now(colombia_tz).strftime('%Y-%m-%d')
        
        logging.info(f"🔎 Comprobando apuestas pendientes para el día: {today_str}")

        # Invocación limpia y estática pasando db_manager
        message = BettingController.get_today_high_prob_summary(db_manager, today_str)

        if message:
            TelegramNotifier.send_alert(message)
            logging.info("✅ Notificación enviada a Telegram con éxito.")
        else:
            logging.info("ℹ️ Sin apuestas pendientes de prob >= 90% para el día de hoy.")

    except Exception as e:
        logging.error(f"❌ Error en el proceso de notificación: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()