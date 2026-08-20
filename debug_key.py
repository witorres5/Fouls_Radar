import os
import streamlit as st
from dotenv import load_dotenv

st.title("🔍 Inspección de Claves Detectadas")

# 1. Forzar carga de .env
load_dotenv()

# 2. Ver qué claves existen en st.secrets
st.subheader("Contenido de st.secrets:")
try:
    keys_in_secrets = list(st.secrets.keys())
    st.write("Claves de primer nivel encontradas:", keys_in_secrets)
except Exception as e:
    st.error(f"Error leyendo st.secrets: {e}")

# 3. Ver qué clave existe en os.environ
st.subheader("Contenido de variables de entorno (.env):")
env_key = os.getenv("API_FOOTBALL_KEY")
if env_key:
    st.success("✅ 'API_FOOTBALL_KEY' cargada exitosamente mediante load_dotenv()")
else:
    st.warning("⚠️ No se encontró 'API_FOOTBALL_KEY' en el entorno.")