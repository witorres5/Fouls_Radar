# databases/player_repository.py
from typing import Dict, Any, List
from databases.connection import DatabaseManager

class PlayerRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.init_table()

    def init_table(self):
        """Inicializa las tablas necesarias si no existen."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    player_id INTEGER PRIMARY KEY,
                    team_id INTEGER,
                    player_name TEXT,
                    league_id INTEGER,
                    season INTEGER,
                    minutes_played INTEGER,
                    fouls_committed INTEGER,
                    fouls_drawn INTEGER,
                    yellow_cards INTEGER,
                    red_cards INTEGER,
                    fouls_per_90 REAL,
                    updated_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_league_season ON players(league_id, season)")
            
            # Asegurar tabla de metadata de sincronización por si no existe
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
                if row and row[0]:
                    return row[0]
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
            conn.commit()

    def get_players_by_league(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Obtiene todos los jugadores de una liga y temporada."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_id, team_id, player_name, league_id, season,
                       minutes_played, fouls_committed, fouls_drawn,
                       yellow_cards, red_cards, fouls_per_90, updated_at
                FROM players
                WHERE league_id = ? AND season = ?
                ORDER BY player_name
            """, (league_id, season))
            rows = cursor.fetchall()
            
        return [
            {
                "player_id": r[0], "team_id": r[1], "player_name": r[2],
                "league_id": r[3], "season": r[4], "minutes_played": r[5],
                "fouls_committed": r[6], "fouls_drawn": r[7], "yellow_cards": r[8],
                "red_cards": r[9], "fouls_per_90": r[10], "updated_at": r[11]
            }
            for r in rows
        ]

    def get_players_by_team(self, team_id: int) -> List[Dict[str, Any]]:
        """Obtiene todos los jugadores de un equipo específico."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_id, team_id, player_name, league_id, season,
                       minutes_played, fouls_committed, fouls_drawn,
                       yellow_cards, red_cards, fouls_per_90, updated_at
                FROM players
                WHERE team_id = ?
                ORDER BY player_name
            """, (team_id,))
            rows = cursor.fetchall()
            
        return [
            {
                "player_id": r[0], "team_id": r[1], "player_name": r[2],
                "league_id": r[3], "season": r[4], "minutes_played": r[5],
                "fouls_committed": r[6], "fouls_drawn": r[7], "yellow_cards": r[8],
                "red_cards": r[9], "fouls_per_90": r[10], "updated_at": r[11]
            }
            for r in rows
        ]

    def save_players(self, records: List[Dict[str, Any]], batch_size: int = 100):
        """Inserta o actualiza lotes de jugadores utilizando upsert (ON CONFLICT)."""
        if not records:
            return

        query = """
            INSERT INTO players (
                player_id, team_id, player_name, league_id, season,
                minutes_played, fouls_committed, fouls_drawn,
                yellow_cards, red_cards, fouls_per_90, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                team_id = excluded.team_id,
                player_name = excluded.player_name,
                minutes_played = excluded.minutes_played,
                fouls_committed = excluded.fouls_committed,
                fouls_drawn = excluded.fouls_drawn,
                yellow_cards = excluded.yellow_cards,
                red_cards = excluded.red_cards,
                fouls_per_90 = excluded.fouls_per_90,
                updated_at = excluded.updated_at
        """

        data_to_insert = [
            (
                r.get("player_id"),
                r.get("team_id"),
                r.get("player_name"),
                r.get("league_id"),
                r.get("season"),
                r.get("minutes_played", 0),
                r.get("fouls_committed", 0),
                r.get("fouls_drawn", 0),
                r.get("yellow_cards", 0),
                r.get("red_cards", 0),
                r.get("fouls_per_90", 0.0),
                r.get("updated_at")
            )
            for r in records
        ]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for i in range(0, len(data_to_insert), batch_size):
                chunk = data_to_insert[i:i + batch_size]
                cursor.executemany(query, chunk)
            conn.commit()