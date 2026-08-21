# databases/team_repository.py
from typing import Dict, Any, List
from databases.connection import DatabaseManager

class TeamRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.init_table()

    def init_table(self):
        """Inicializa las tablas de equipos y metadatos si no existen."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    team_id INTEGER PRIMARY KEY,
                    league_id INTEGER,
                    season INTEGER,
                    name TEXT,
                    code TEXT,
                    country TEXT,
                    founded INTEGER,
                    logo TEXT,
                    updated_at TEXT
                )
            """)
            
            # --- Migración defensiva para todas las columnas faltantes ---
            columns_to_add = [
                ("season", "INTEGER"),
                ("code", "TEXT"),
                ("country", "TEXT"),
                ("founded", "INTEGER"),
                ("logo", "TEXT"),
                ("updated_at", "TEXT")
            ]
            
            for col_name, col_type in columns_to_add:
                try:
                    cursor.execute(f"ALTER TABLE teams ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass  # La columna ya existe

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_teams_league_season ON teams(league_id, season)")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    entity_name TEXT PRIMARY KEY,
                    last_sync_timestamp TEXT
                )
            """)

    def get_last_sync(self, entity_name: str) -> str:
        """Obtiene la última fecha de sincronización para una entidad dada."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT last_sync_timestamp FROM sync_metadata WHERE entity_name = ?", (entity_name,))
                row = cursor.fetchone()
                if row:
                    return row[0] if isinstance(row, tuple) else row["last_sync_timestamp"]
            except Exception:
                pass
        return "Nunca sincronizado"

    def update_sync_timestamp(self, entity_name: str, timestamp: str):
        """Actualiza o inserta el registro de sincronización."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_metadata (entity_name, last_sync_timestamp) 
                VALUES (?, ?)
                ON CONFLICT(entity_name) DO UPDATE SET last_sync_timestamp = ?
            """, (entity_name, timestamp, timestamp))

    def get_teams_by_league(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Obtiene todos los equipos de una liga y temporada."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT team_id, league_id, season, name, code, country, founded, logo, updated_at
                FROM teams
                WHERE league_id = ? AND season = ?
                ORDER BY name
            """, (league_id, season))
            rows = cursor.fetchall()
            
        return [
            {
                "team_id": r[0], "league_id": r[1], "season": r[2],
                "name": r[3], "code": r[4], "country": r[5],
                "founded": r[6], "logo": r[7], "updated_at": r[8]
            }
            for r in rows
        ]

    def save_teams(self, records: List[Dict[str, Any]], batch_size: int = 100):
        """Inserta o actualiza lotes de equipos utilizando upsert (ON CONFLICT)."""
        if not records:
            return

        query = """
            INSERT INTO teams (
                team_id, league_id, season, name, code, country, founded, logo, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                league_id = excluded.league_id,
                season = excluded.season,
                name = excluded.name,
                code = excluded.code,
                country = excluded.country,
                founded = excluded.founded,
                logo = excluded.logo,
                updated_at = excluded.updated_at
        """

        data_to_insert = [
            (
                r.get("team_id"),
                r.get("league_id"),
                r.get("season"),
                r.get("name"),
                r.get("code"),
                r.get("country"),
                r.get("founded"),
                r.get("logo"),
                r.get("updated_at")
            )
            for r in records
        ]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for i in range(0, len(data_to_insert), batch_size):
                chunk = data_to_insert[i:i + batch_size]
                cursor.executemany(query, chunk)