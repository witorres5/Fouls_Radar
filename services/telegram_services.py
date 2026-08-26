# services/telegram_bot.py
import os
import requests
import logging

class TelegramNotifier:

    @classmethod
    def send_alert(cls, message: str) -> bool:
        """Envía un mensaje formateado en Markdown a Telegram."""
        BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
        CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
        
        print(f">>> Enviando desde TelegramNotifier ...")
        if not BOT_TOKEN or not CHAT_ID:
            print(f">>> no token o chatid revisar ...")
            return False
        
        url = f"https://api.telegram.org/bot{cls.BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": cls.CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"Error enviando notificación a Telegram: {e}")
            return False
