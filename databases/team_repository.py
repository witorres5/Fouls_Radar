# databases/team_repository.py
from typing import Dict, Any, List
from databases.connection import DatabaseManager

class TeamRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

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
        """Inserta o actualiza lotes de equipos de forma segura (compatible con schemas legacy)."""
        if not records:
            return

        INSERT_COLS = ("team_id", "league_id", "season", "name", "code", "country", "founded", "logo", "updated_at")
        UPDATE_COLS = ("name", "code", "country", "founded", "logo", "updated_at")

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
                self.db.safe_upsert_many(
                    cursor,
                    table="teams",
                    key_cols=("team_id", "league_id", "season"),
                    insert_cols=INSERT_COLS,
                    rows=chunk,
                    update_cols=UPDATE_COLS,
                )