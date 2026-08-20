# core/notifications.py
import os
import requests
import streamlit as st

def send_telegram_alert(message: str):
    """Envía un mensaje a Telegram soportando entorno local, Streamlit y GitHub Actions."""
    try:
        # 1. Intentar obtener de variables de entorno (GitHub Actions)
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        # 2. Si no están en el entorno, buscar en st.secrets (Streamlit Cloud)
        if not bot_token or not chat_id:
            try:
                bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN")
                chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
            except Exception:
                pass

        if not bot_token or not chat_id:
            print("⚠️ Credenciales de Telegram no encontradas.")
            return

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload, timeout=5)
        print(f"Telegram status: {response.status_code}")
    except Exception as e:
        print(f"Error enviando alerta de Telegram: {e}")