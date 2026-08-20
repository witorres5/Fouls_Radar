import libsql
import pandas as pd
import streamlit as st
from main import DatabaseManager

db = DatabaseManager()

@st.cache_data
def load_data() -> pd.DataFrame:
    """Carga y procesa las estadísticas de jugadores desde Turso."""
    turso_url = st.secrets["TURSO_DATABASE_URL"]
    turso_token = st.secrets["TURSO_AUTH_TOKEN"]

    conn = libsql.connect(database=turso_url, auth_token=turso_token)
    df = pd.read_sql("SELECT * FROM player_foul_stats", conn)
    conn.close()
    
    df["minutes_played"] = df["minutes_played"].fillna(0)
    df["fouls_per_90"] = df.apply(
        lambda r: (r["fouls_committed"] / r["minutes_played"] * 90) if r["minutes_played"] > 0 else 0.0, 
        axis=1
    )
    df["fouls_drawn_per_90"] = df.apply(
        lambda r: (r["fouls_drawn"] / r["minutes_played"] * 90) if r["minutes_played"] > 0 else 0.0, 
        axis=1
    )
    return df

@st.cache_data(ttl=300)
def get_team_top_foulers(league_id: int, season: int) -> dict:
    """Obtiene el jugador con más faltas por 90 min de cada equipo."""
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT team_name, player_name, fouls_per_90
            FROM (
                SELECT team_name, player_name, fouls_per_90,
                       ROW_NUMBER() OVER (PARTITION BY team_name ORDER BY fouls_per_90 DESC) as rn
                FROM player_foul_stats
                WHERE league_id = ? AND season = ? AND minutes_played >= 180
            ) WHERE rn = 1
        """
        cursor.execute(query, (league_id, season))
        rows = cursor.fetchall()
        conn.close()
        
        return {
            row[0]: {"player": row[1], "fouls_per_90": row[2]} 
            for row in rows
        }
    except Exception as e:
        print(f"Error consultando top infractores por equipo: {e}")
        return {}

@st.cache_data(ttl=60)
def get_available_seasons() -> list:
    """Obtiene las temporadas disponibles desde la BD."""
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT season FROM player_foul_stats ORDER BY season DESC")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows] if rows else [2026, 2025, 2024, 2022]
    except Exception:
        return [2026, 2025, 2024, 2022]
    
# En database/data_loader.py
import sqlite3

DB_BETS_PATH = "database/bets_tracker.db"

def init_bets_db():
    """Inicializa la tabla de apuestas si no existe."""
    conn = sqlite3.connect(DB_BETS_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER,
            match_date TEXT,
            home_team TEXT,
            away_team TEXT,
            player_name TEXT,
            bet_line TEXT,
            tier TEXT,
            probability REAL,
            odds REAL DEFAULT 0.0,
            status TEXT DEFAULT 'PENDING',
            actual_fouls INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fixture_id, player_name, bet_line)
        )
    """)
    conn.commit()
    conn.close()

def save_auto_bet(bet_data: dict):
    """Guarda una sugerencia de apuesta en la BD."""
    init_bets_db()  # Asegura que la tabla exista antes de insertar
    conn = sqlite3.connect(DB_BETS_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO auto_bets 
        (fixture_id, match_date, home_team, away_team, player_name, bet_line, tier, probability)
        VALUES (:fixture_id, :match_date, :home_team, :away_team, :player_name, :bet_line, :tier, :probability)
    """, bet_data)
    conn.commit()
    conn.close()