# core/notifications.py
import requests
import streamlit as st

def send_telegram_alert(message: str):
    """Envía un mensaje a un canal/chat de Telegram."""
    try:
        # Obtiene las llaves desde st.secrets o variables de entorno
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
        
        if not bot_token or not chat_id:
            print("Telegram credentials not configured.")
            return

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error enviando alerta de Telegram: {e}")