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
        self.init_metadata_table()
        self.init_performance_indexes() # <-- Inicializar índices de rendimiento

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
        if self.db_url.startswith("libsql://") or self.db_url.startswith("https://"):
            import libsql as libsql
            conn = libsql.connect(database=self.db_url, auth_token=self.auth_token)
        else:
            conn = sqlite3.connect(self.db_url)
            conn.row_factory = sqlite3.Row  # Facilita el mapeo a diccionarios
            
            # --- OPTIMIZACIONES SQLite (Modo WAL y Rendimiento) ---
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            # --- ACTIVAR TRAZA SQL EN TERMINAL (Opcional) ---
            conn.set_trace_callback(lambda query: print(f"[SQL EXEC]: {query}"))
            
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_metadata_table(self):
        """Crea la tabla base de metadatos para los timestamps de sincronización."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    entity_name TEXT PRIMARY KEY,
                    last_sync_timestamp TEXT
                )
            """)

    def init_performance_indexes(self):
        """Crea índices clave para acelerar consultas masivas en SQLite."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Índices orientados a la tabla 'players' para agilizar filtros y ordenamientos
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_league_season ON players (league_id, season);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_team_season ON players (team_id, season);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_fouls ON players (fouls_committed DESC);")

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