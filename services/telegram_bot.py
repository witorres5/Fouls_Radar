# services/telegram_bot.py
import os
import requests
import logging

def send_telegram_message(message: str) -> bool:
    """Envía un mensaje a través del bot de Telegram."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logging.warning("⚠️ TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no están configurados.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            logging.error(f"Error al enviar mensaje a Telegram: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Excepción al conectar con Telegram: {e}")
        return False