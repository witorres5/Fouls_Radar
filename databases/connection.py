# databases/connection.py
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional
import logging

logger = logging.getLogger("FoulsTracker.Database")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import streamlit as st
except ImportError:
    st = None

class DatabaseManager:
    def __init__(self, db_url: Optional[str] = None, auth_token: Optional[str] = None):
        self.db_url = db_url or self._resolve_db_url()
        self.auth_token = auth_token or self._resolve_auth_token()
        self.init_all_tables()
        self.init_performance_indexes()

    def _resolve_db_url(self) -> str:
        if st and hasattr(st, "secrets") and "TURSO_DATABASE_URL" in st.secrets:
            return st.secrets["TURSO_DATABASE_URL"]
        return os.getenv("TURSO_DATABASE_URL", "local.db")

    def _resolve_auth_token(self) -> str:
        if st and hasattr(st, "secrets") and "TURSO_AUTH_TOKEN" in st.secrets:
            return st.secrets["TURSO_AUTH_TOKEN"]
        return os.getenv("TURSO_AUTH_TOKEN", "")

    @contextmanager
    def get_connection(self):
        """Context manager seguro para manejar conexiones a Turso (remota) o SQLite (local)."""
        is_remote = self.db_url.startswith("libsql://") or self.db_url.startswith("https://")
        if is_remote:
            try:
                import libsql as libsql
            except ImportError:
                import libsql_experimental as libsql
            conn = libsql.connect(database=self.db_url, auth_token=self.auth_token)
        else:
            conn = sqlite3.connect(self.db_url)
            conn.row_factory = sqlite3.Row  # Facilita el mapeo a diccionarios
            
            # Optimización de rendimiento local
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            if os.getenv("DEBUG_SQL", "0") == "1":
                conn.set_trace_callback(lambda query: print(f"[SQL EXEC]: {query}"))
            
        try:
            yield conn
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            raise e
        finally:
            conn.close()

    def init_all_tables(self):
        """Inicializa todas las tablas del sistema de forma segura con migraciones defensivas."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Metadatos de sincronización
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    entity_name TEXT PRIMARY KEY,
                    last_sync_timestamp TEXT NOT NULL
                )
            """)
            
            # 2. Equipos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    team_id INTEGER NOT NULL,
                    league_id INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT,
                    country TEXT,
                    founded INTEGER,
                    logo TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (team_id, league_id, season)
                )
            """)

            # 3. Jugadores
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    player_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    league_id INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    minutes_played INTEGER DEFAULT 0,
                    fouls_committed INTEGER DEFAULT 0,
                    fouls_drawn INTEGER DEFAULT 0,
                    yellow_cards INTEGER DEFAULT 0,
                    red_cards INTEGER DEFAULT 0,
                    fouls_per_90 REAL DEFAULT 0.0,
                    updated_at TEXT,
                    PRIMARY KEY (player_id, league_id, season)
                )
            """)

            # 4. Partidos / Fixtures
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS match_fixtures (
                    fixture_id INTEGER PRIMARY KEY,
                    league_id INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    status TEXT NOT NULL,
                    match_date TEXT NOT NULL,
                    total_fouls INTEGER DEFAULT 0,
                    total_yellow_cards INTEGER DEFAULT 0,
                    referee_name TEXT,
                    processed_for_stats INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 5. Estadísticas de jugadores por fixture individual
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_fixture_stats (
                    fixture_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    team_id INTEGER,
                    minutes_played INTEGER DEFAULT 0,
                    fouls_committed INTEGER DEFAULT 0,
                    fouls_drawn INTEGER DEFAULT 0,
                    yellow_cards INTEGER DEFAULT 0,
                    red_cards INTEGER DEFAULT 0,
                    PRIMARY KEY (fixture_id, player_id)
                )
            """)

            # 6. Fixtures generales
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fixtures (
                    fixture_id INTEGER PRIMARY KEY,
                    league_id INTEGER,
                    season INTEGER,
                    match_name TEXT,
                    referee TEXT,
                    match_date TEXT,
                    status TEXT
                )
            """)

            # 7. Apuestas simuladas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER,
                    league_id INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    match_name TEXT NOT NULL,
                    referee TEXT,
                    market TEXT NOT NULL,
                    probability REAL NOT NULL,
                    simulated_odds REAL NOT NULL,
                    odds REAL DEFAULT 1.85,
                    stake REAL DEFAULT 10.0,
                    match_date TEXT,
                    status TEXT DEFAULT 'PENDIENTE',
                    notified_telegram INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migraciones defensivas de columnas en simulated_bets si la tabla ya existía
            for col_name, col_def in [
                ("fixture_id", "INTEGER"),
                ("odds", "REAL DEFAULT 1.85"),
                ("stake", "REAL DEFAULT 10.0"),
                ("notified_telegram", "INTEGER DEFAULT 0"),
                ("match_date", "TEXT")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE simulated_bets ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

    def init_performance_indexes(self):
        """Crea índices clave para acelerar consultas de forma segura."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_league_season ON players (league_id, season);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_team_season ON players (team_id, season);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_fouls ON players (fouls_committed DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_fixtures_league_season ON match_fixtures (league_id, season, match_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_fixtures_referee ON match_fixtures (referee_name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_simulated_bets_status ON simulated_bets (status, match_date);")

    def get_last_sync_timestamp(self, entity_name: str) -> Optional[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_sync_timestamp FROM sync_metadata WHERE entity_name = ?", (entity_name,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_last_sync_timestamp(self, entity_name: str, timestamp: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_metadata (entity_name, last_sync_timestamp)
                VALUES (?, ?)
                ON CONFLICT(entity_name) DO UPDATE SET last_sync_timestamp = excluded.last_sync_timestamp
            """, (entity_name, timestamp))