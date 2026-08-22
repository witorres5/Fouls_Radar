# databases/fixture_repository.py
import logging
from typing import Dict, Any
from databases.connection import DatabaseManager
import pandas as pd

logger = logging.getLogger("FoulsTracker.FixtureRepository")

class FixtureRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._init_db()

    def _init_db(self):
        """Crea la tabla de metadatos de sincronización y asegura sus columnas."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    entity_name TEXT PRIMARY KEY,
                    last_updated TEXT
                )
            """)
            # Por si la tabla ya existía creada desde otro repositorio sin la columna last_updated:
            try:
                cursor.execute("ALTER TABLE sync_metadata ADD COLUMN last_updated TEXT")
            except Exception:
                # La columna ya existe, ignoramos el error de manera segura
                pass
            conn.commit()

    def update_player_match_stats(self, player_stats: Dict[int, Dict[str, Any]], league_id: int, season: int) -> None:
        """Actualiza e incrementa las estadísticas acumuladas (minutos, faltas, tarjetas) por jugador."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            for player_id, stats in player_stats.items():
                minutes = stats.get("minutes_played", 0)
                committed = stats.get("fouls_committed", 0)
                drawn = stats.get("fouls_drawn", 0)
                yellow = stats.get("yellow_cards", 0)
                red = stats.get("red_cards", 0)

                cursor.execute("""
                    UPDATE players 
                    SET minutes_played = minutes_played + ?,
                        fouls_committed = fouls_committed + ?,
                        fouls_drawn = fouls_drawn + ?,
                        yellow_cards = yellow_cards + ?,
                        red_cards = red_cards + ?
                    WHERE player_id = ? AND league_id = ? AND season = ?
                """, (minutes, committed, drawn, yellow, red, player_id, league_id, season))
            
            conn.commit()
            logger.info(f"Estadísticas de partidos actualizadas para la liga {league_id}, temporada {season}.")

    def get_last_sync(self, entity_name: str) -> str:
        """Obtiene la última fecha de sincronización de fixtures desde la tabla de metadatos."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_updated FROM sync_metadata WHERE entity_name = ?", (entity_name,))
            row = cursor.fetchone()
            return row[0] if row else "Nunca"

    def update_sync_timestamp(self, entity_name: str, current_time: str) -> None:
        """Actualiza o inserta la marca de tiempo de sincronización."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_metadata (entity_name, last_updated) 
                VALUES (?, ?)
                ON CONFLICT(entity_name) DO UPDATE SET last_updated = ?
            """, (entity_name, current_time, current_time))
            conn.commit()
            
    # Dentro de la clase FixtureRepository en databases/fixture_repository.py

    # databases/fixture_repository.py

    def get_top_fouler_for_team(self, team_id: int, season: int) -> dict:
        """Acceso a datos para obtener el jugador más sancionado del equipo."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_name, fouls_committed 
                FROM players 
                WHERE team_id = ? AND season = ?
                ORDER BY fouls_committed DESC
                LIMIT 1
            """, (team_id, season))
            row = cursor.fetchone()
            if row:
                return {"name": row[0], "avg": float(row[1])}
        return {"name": "N/D", "avg": 0.0}
    
    
    def get_competition_fouls_summary(self, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene el resumen de faltas y tarjetas de la competición."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_name, minutes_played, fouls_committed, yellow_cards, red_cards, fouls_per_90
                FROM players 
                WHERE league_id = ? AND season = ? AND minutes_played > 0
                ORDER BY fouls_committed DESC
                LIMIT 15
            """, (league_id, season))
            rows = cursor.fetchall()
            
        if rows:
            return pd.DataFrame(rows, columns=["Jugador", "Minutos", "Faltas Cometidas", "Tarjetas Amarillas", "Tarjetas Rojas", "Faltas por 90'"])
        return pd.DataFrame()
    
    def get_competition_summary(self, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene el resumen de faltas y tarjetas de la competición desde la base de datos."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_name, minutes_played, fouls_committed, yellow_cards, red_cards, fouls_per_90
                FROM players 
                WHERE league_id = ? AND season = ? AND minutes_played > 0
                ORDER BY fouls_committed DESC
                LIMIT 15
            """, (league_id, season))
            rows = cursor.fetchall()
            
        if rows:
            return pd.DataFrame(rows, columns=["Jugador", "Minutos", "Faltas Cometidas", "Tarjetas Amarillas", "Tarjetas Rojas", "Faltas por 90'"])
        return pd.DataFrame()
    
    
    def get_top_foulers_for_teams(self, team_ids: list, season: int) -> dict:
        """Obtiene el top de faltas para una lista de equipos en una sola consulta SQL."""
        if not team_ids:
            return {}
            
        placeholders = ','.join(['?'] * len(team_ids))
        query = f"""
            SELECT team_id, player_name, fouls_committed 
            FROM (
                SELECT team_id, player_name, fouls_committed,
                       ROW_NUMBER() OVER(PARTITION BY team_id ORDER BY fouls_committed DESC) as rn
                FROM players 
                WHERE team_id IN ({placeholders}) AND season = ?
            ) 
            WHERE rn = 1
        """
        params = list(team_ids) + [season]
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
        result = {}
        for row in rows:
            # Si usas row_factory = sqlite3.Row, puedes acceder por nombre, 
            # de lo contrario por índice: row[0], row[1], etc.
            team_id = row["team_id"] if hasattr(row, "keys") else row[0]
            player_name = row["player_name"] if hasattr(row, "keys") else row[1]
            fouls = row["fouls_committed"] if hasattr(row, "keys") else row[2]
            
            result[team_id] = {"name": player_name, "avg": float(fouls)}
        return result
    
    # databases/fixture_repository.py (Ejemplo de lógica)
    def save_fixture(self, fixture_data):
        """Guarda o actualiza un partido sin duplicar."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # NOTA: Asegúrate de que la tabla 'fixtures' tenga 'fixture_id' como UNIQUE
            cursor.execute("""
                INSERT OR REPLACE INTO fixtures (fixture_id, league_id, season, match_name, referee, match_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                fixture_data['id'], 
                fixture_data['league_id'], 
                fixture_data['season'], 
                fixture_data['match_name'], 
                fixture_data['referee'], 
                fixture_data['date'], 
                fixture_data['status']
            ))
            
    def save_fixture_info(self, fixture_id, league_id, season, home_team, away_team, status, match_date, total_fouls=0, total_yellow_cards=0):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                INSERT INTO match_fixtures (fixture_id, league_id, season, home_team, away_team, status, match_date, total_fouls, total_yellow_cards)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    status = excluded.status,
                    home_team = excluded.home_team,
                    away_team = excluded.away_team,
                    match_date = excluded.match_date,
                    total_fouls = excluded.total_fouls,
                    total_yellow_cards = excluded.total_yellow_cards;
            """
            cursor.execute(query, (fixture_id, league_id, season, home_team, away_team, status, match_date, total_fouls, total_yellow_cards))