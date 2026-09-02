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

            # 8. Migraciones defensivas de columnas existentes en Turso/SQLite
            self._apply_defensive_migrations(cursor)

    def _apply_defensive_migrations(self, cursor):
        """Verifica las columnas existentes en cada tabla y agrega automáticamente las que falten."""
        migrations = {
            "player_fixture_stats": [
                ("player_name", "TEXT"),
                ("team_id", "INTEGER"),
                ("minutes_played", "INTEGER DEFAULT 0"),
                ("fouls_committed", "INTEGER DEFAULT 0"),
                ("fouls_drawn", "INTEGER DEFAULT 0"),
                ("yellow_cards", "INTEGER DEFAULT 0"),
                ("red_cards", "INTEGER DEFAULT 0"),
            ],
            "players": [
                ("team_id", "INTEGER"),
                ("player_name", "TEXT"),
                ("minutes_played", "INTEGER DEFAULT 0"),
                ("fouls_committed", "INTEGER DEFAULT 0"),
                ("fouls_drawn", "INTEGER DEFAULT 0"),
                ("yellow_cards", "INTEGER DEFAULT 0"),
                ("red_cards", "INTEGER DEFAULT 0"),
                ("fouls_per_90", "REAL DEFAULT 0.0"),
                ("updated_at", "TEXT"),
            ],
            "match_fixtures": [
                ("home_team", "TEXT"),
                ("away_team", "TEXT"),
                ("status", "TEXT"),
                ("match_date", "TEXT"),
                ("total_fouls", "INTEGER DEFAULT 0"),
                ("total_yellow_cards", "INTEGER DEFAULT 0"),
                ("referee_name", "TEXT"),
                ("processed_for_stats", "INTEGER DEFAULT 0"),
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ],
            "simulated_bets": [
                ("fixture_id", "INTEGER"),
                ("match_name", "TEXT"),
                ("referee", "TEXT"),
                ("market", "TEXT"),
                ("probability", "REAL DEFAULT 0.0"),
                ("simulated_odds", "REAL DEFAULT 1.85"),
                ("odds", "REAL DEFAULT 1.85"),
                ("stake", "REAL DEFAULT 10.0"),
                ("match_date", "TEXT"),
                ("status", "TEXT DEFAULT 'PENDIENTE'"),
                ("notified_telegram", "INTEGER DEFAULT 0"),
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ],
            "teams": [
                ("name", "TEXT"),
                ("code", "TEXT"),
                ("country", "TEXT"),
                ("founded", "INTEGER"),
                ("logo", "TEXT"),
                ("updated_at", "TEXT"),
            ]
        }

        for table_name, columns in migrations.items():
            try:
                cursor.execute(f"PRAGMA table_info({table_name})")
                rows = cursor.fetchall()
                existing_cols = set()
                for r in rows:
                    if isinstance(r, (list, tuple)):
                        existing_cols.add(str(r[1]).lower())
                    elif hasattr(r, "keys") and "name" in r.keys():
                        existing_cols.add(str(r["name"]).lower())
                    elif isinstance(r, dict) and "name" in r:
                        existing_cols.add(str(r["name"]).lower())
                
                for col_name, col_def in columns:
                    if col_name.lower() not in existing_cols:
                        try:
                            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
                            logger.info(f"Columna '{col_name}' añadida con éxito a '{table_name}'.")
                        except Exception as e:
                            logger.debug(f"Columna {col_name} en {table_name} ya existía o error: {e}")
            except Exception as table_err:
                logger.debug(f"Error verificando columnas para {table_name}: {table_err}")

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

    # ──────────────────────────────────────────────────────────────────────────
    # Cache de constraints por tabla (detectado una sola vez por sesión)
    # ──────────────────────────────────────────────────────────────────────────
    _constraint_cache: dict = {}

    def _has_unique_constraint(self, cursor, table: str, key_cols: tuple) -> bool:
        """
        Detecta si la tabla tiene un PRIMARY KEY o UNIQUE constraint sobre key_cols.
        El resultado se cachea en memoria para no repetir el PRAGMA en cada fila.
        """
        cache_key = (table, key_cols)
        if cache_key in self._constraint_cache:
            return self._constraint_cache[cache_key]

        has_it = False
        try:
            # Comprobar PRIMARY KEY vía PRAGMA table_info (pk > 0 marca columnas PK)
            cursor.execute(f"PRAGMA table_info({table})")
            rows = cursor.fetchall()
            pk_cols = set()
            for r in rows:
                # r = (cid, name, type, notnull, dflt_value, pk)
                pk_val = r[5] if isinstance(r, (list, tuple)) else (r.get("pk", 0) if hasattr(r, "get") else 0)
                name_val = r[1] if isinstance(r, (list, tuple)) else (r.get("name", "") if hasattr(r, "get") else "")
                if pk_val and pk_val > 0:
                    pk_cols.add(str(name_val).lower())

            expected = {c.lower() for c in key_cols}
            if expected.issubset(pk_cols):
                has_it = True

            if not has_it:
                # Comprobar UNIQUE indexes vía PRAGMA index_list + index_info
                cursor.execute(f"PRAGMA index_list({table})")
                idx_rows = cursor.fetchall()
                for idx_r in idx_rows:
                    is_unique = idx_r[2] if isinstance(idx_r, (list, tuple)) else (idx_r.get("unique", 0) if hasattr(idx_r, "get") else 0)
                    idx_name = idx_r[1] if isinstance(idx_r, (list, tuple)) else (idx_r.get("name", "") if hasattr(idx_r, "get") else "")
                    if not is_unique:
                        continue
                    cursor.execute(f"PRAGMA index_info({idx_name})")
                    idx_cols = set()
                    for ic in cursor.fetchall():
                        col = ic[2] if isinstance(ic, (list, tuple)) else (ic.get("name", "") if hasattr(ic, "get") else "")
                        idx_cols.add(str(col).lower())
                    if expected == idx_cols:
                        has_it = True
                        break
        except Exception as e:
            logger.debug(f"_has_unique_constraint error para {table}{key_cols}: {e}")

        self._constraint_cache[cache_key] = has_it
        logger.debug(f"Constraint {table}{key_cols}: {'ENCONTRADO' if has_it else 'NO encontrado'} → {'upsert directo' if has_it else 'delete+insert'}")
        return has_it

    def safe_upsert(
        self,
        cursor,
        table: str,
        key_cols: tuple,
        insert_cols: tuple,
        values: tuple,
        update_cols: tuple,
    ) -> None:
        """
        Upsert seguro compatible con Turso/libSQL incluso cuando la tabla fue creada
        sin PRIMARY KEY o UNIQUE constraint (tablas legacy).

        Estrategia:
          - Si la tabla TIENE el constraint → usa INSERT ... ON CONFLICT DO UPDATE (rápido).
          - Si NO tiene el constraint      → usa DELETE + INSERT (compatible con schemas legacy).

        Args:
            cursor:      Cursor activo de la conexión.
            table:       Nombre de la tabla.
            key_cols:    Columnas que forman la clave única (p.ej. ('fixture_id', 'player_id')).
            insert_cols: Todas las columnas a insertar (en el mismo orden que values).
            values:      Tupla de valores para insert_cols.
            update_cols: Columnas a actualizar en caso de conflicto (ignora las key_cols).
        """
        if self._has_unique_constraint(cursor, table, key_cols):
            # Camino rápido: upsert nativo
            placeholders = ", ".join("?" * len(insert_cols))
            col_names = ", ".join(insert_cols)
            update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
            key_clause = ", ".join(key_cols)
            sql = (
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
                f"ON CONFLICT({key_clause}) DO UPDATE SET {update_clause}"
            )
            cursor.execute(sql, values)
        else:
            # Camino seguro: DELETE por clave + INSERT fresco
            key_indices = [insert_cols.index(k) for k in key_cols]
            where_clause = " AND ".join(f"{k} = ?" for k in key_cols)
            key_values = tuple(values[i] for i in key_indices)
            cursor.execute(f"DELETE FROM {table} WHERE {where_clause}", key_values)

            placeholders = ", ".join("?" * len(insert_cols))
            col_names = ", ".join(insert_cols)
            cursor.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)

    def safe_upsert_many(
        self,
        cursor,
        table: str,
        key_cols: tuple,
        insert_cols: tuple,
        rows: list,
        update_cols: tuple,
    ) -> None:
        """Ejecuta safe_upsert en lote para una lista de tuplas de valores."""
        for values in rows:
            self.safe_upsert(cursor, table, key_cols, insert_cols, values, update_cols)