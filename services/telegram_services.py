# services/telegram_services.py
import os
import requests
import logging

logger = logging.getLogger("FoulsTracker.TelegramService")

try:
    import streamlit as st
except ImportError:
    st = None

class TelegramNotifier:

    @classmethod
    def send_alert(cls, message: str) -> bool:
        """Envía un mensaje formateado en Markdown a Telegram."""
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if not bot_token and st and hasattr(st, "secrets") and "TELEGRAM_BOT_TOKEN" in st.secrets:
            bot_token = st.secrets["TELEGRAM_BOT_TOKEN"]
        if not chat_id and st and hasattr(st, "secrets") and "TELEGRAM_CHAT_ID" in st.secrets:
            chat_id = st.secrets["TELEGRAM_CHAT_ID"]

        if not bot_token or not chat_id:
            logger.warning("Telegram Bot Token o Chat ID no configurados. Omitiendo notificación.")
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Notificación enviada a Telegram con éxito.")
                return True
            else:
                logger.error(f"Error devuelto por Telegram API [{response.status_code}]: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error de red al enviar notificación a Telegram: {e}")
            return False

def send_telegram_message(message: str) -> bool:
    """Función de conveniencia compatible con scripts."""
    return TelegramNotifier.send_alert(message)
