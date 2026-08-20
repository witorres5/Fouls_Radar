import os
import requests
import streamlit as st

# Intenta leer desde secrets local (.streamlit/secrets.toml) o pide por consola
try:
    bot_token = st.secrets["TELEGRAM_BOT_TOKEN"]
    chat_id = st.secrets["TELEGRAM_CHAT_ID"]
except Exception:
    bot_token = input("Pega tu TELEGRAM_BOT_TOKEN aquí: ").strip()
    chat_id = input("Pega tu TELEGRAM_CHAT_ID aquí (ej: 8879384808): ").strip()

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": "🧪 Prueba local desde test_telegram.py"
}

print("Enviando petición a Telegram...")
res = requests.post(url, json=payload, timeout=10)

print(f"Status Code: {res.status_code}")
print(f"Respuesta del Servidor:\n{res.json()}")