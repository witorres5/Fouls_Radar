# databases/player_repository.py
from typing import Dict, Any, List, Optional
from databases.connection import DatabaseManager

class PlayerRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def get_last_sync(self, entity_name: str) -> str:
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
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_metadata (entity_name, last_sync_timestamp) 
                VALUES (?, ?)
                ON CONFLICT(entity_name) DO UPDATE SET last_sync_timestamp = ?
            """, (entity_name, timestamp, timestamp))

    def get_players_by_league(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Obtiene métricas de jugadores alineadas explícitamente por liga y temporada."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    player_id, 
                    team_id, 
                    player_name, 
                    league_id, 
                    season,
                    COALESCE(minutes_played, 0) as minutes_played, 
                    COALESCE(fouls_committed, 0) as fouls_committed, 
                    COALESCE(fouls_drawn, 0) as fouls_drawn,
                    COALESCE(yellow_cards, 0) as yellow_cards, 
                    COALESCE(red_cards, 0) as red_cards, 
                    COALESCE(fouls_per_90, 0.0) as fouls_per_90, 
                    updated_at
                FROM players
                WHERE CAST(league_id AS INTEGER) = CAST(? AS INTEGER) 
                  AND CAST(season AS INTEGER) = CAST(? AS INTEGER)
                ORDER BY fouls_committed DESC, minutes_played DESC
            """, (league_id, season))
            rows = cursor.fetchall()
            
        return [
            {
                "player_id": r[0], 
                "team_id": r[1], 
                "player_name": r[2],
                "league_id": r[3], 
                "season": r[4], 
                "minutes_played": r[5],
                "fouls_committed": r[6], 
                "fouls_drawn": r[7], 
                "yellow_cards": r[8],
                "red_cards": r[9], 
                "fouls_per_90": r[10], 
                "updated_at": r[11]
            }
            for r in rows
        ]

    def save_players(self, player_records: list):
        """
        Inserta o actualiza jugadores provenientes de plantillas sin sobreescribir
        las estadísticas acumuladas a cero.
        """
        if not player_records:
            return

        query = """
            INSERT INTO players (
                player_id,
                team_id,
                player_name,
                league_id,
                season,
                minutes_played,
                fouls_committed,
                fouls_drawn,
                yellow_cards,
                red_cards,
                fouls_per_90,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, league_id, season) DO UPDATE SET
                team_id = excluded.team_id,
                player_name = excluded.player_name,
                updated_at = excluded.updated_at
        """

        tuple_records = [
            (
                p.get("player_id"),
                p.get("team_id"),
                p.get("player_name"),
                p.get("league_id"),
                p.get("season"),
                p.get("minutes_played", 0),
                p.get("fouls_committed", 0),
                p.get("fouls_drawn", 0),
                p.get("yellow_cards", 0),
                p.get("red_cards", 0),
                p.get("fouls_per_90", 0.0),
                p.get("updated_at")
            )
            for p in player_records
        ]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            chunk_size = 500
            for i in range(0, len(tuple_records), chunk_size):
                chunk = tuple_records[i:i + chunk_size]
                cursor.executemany(query, chunk)
            
    def get_players_by_team(self, team_id: int, season: Optional[int] = None) -> List[Dict[str, Any]]:
        """Obtiene los jugadores de un equipo con sus métricas filtradas por temporada."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if season:
                query = """
                    SELECT 
                        player_id, team_id, player_name, league_id, season,
                        minutes_played, fouls_committed, fouls_drawn,
                        yellow_cards, red_cards, fouls_per_90, updated_at
                    FROM players 
                    WHERE team_id = ? AND season = ?
                    ORDER BY fouls_committed DESC, minutes_played DESC;
                """
                cursor.execute(query, (team_id, season))
            else:
                query = """
                    SELECT 
                        player_id, team_id, player_name, league_id, season,
                        minutes_played, fouls_committed, fouls_drawn,
                        yellow_cards, red_cards, fouls_per_90, updated_at
                    FROM players 
                    WHERE team_id = ?
                    ORDER BY fouls_committed DESC, minutes_played DESC;
                """
                cursor.execute(query, (team_id,))
            rows = cursor.fetchall()

            return [
                {
                    "player_id": row[0],
                    "team_id": row[1],
                    "player_name": row[2],
                    "league_id": row[3],
                    "season": row[4],
                    "minutes_played": row[5],
                    "fouls_committed": row[6],
                    "fouls_drawn": row[7],
                    "yellow_cards": row[8],
                    "red_cards": row[9],
                    "fouls_per_90": row[10],
                    "updated_at": row[11]
                }
                for row in rows
            ]