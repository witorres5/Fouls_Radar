# databases/feature_repository.py   repositorio para trabajar con pyspark
import pandas as pd
from databases.connection import DatabaseManager

class FeatureRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_player_spark_metrics(self, player_id: int, season: int) -> dict:
        """Consulta instantánea de features precalculadas por PySpark."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT rolling_f90_l5, total_matches_played
                FROM player_spark_features
                WHERE player_id = ? AND season = ?
            """, (player_id, season))
            row = cursor.fetchone()
            
            if row:
                return {
                    "rolling_f90_l5": row[0],
                    "total_matches": row[1]
                }
            return {"rolling_f90_l5": 0.0, "total_matches": 0}
        
    def get_team_top_foulers(self, team_id: int, season: int, limit: int = 3) -> list:
        """Obtiene los infractores top de un equipo según su promedio móvil PySpark (rolling_f90_l5)."""
        query = """
            SELECT player_id, player_name, rolling_f90_l5, total_matches_played
            FROM player_spark_features
            WHERE team_id = ? AND season = ? AND total_matches_played >= 2
            ORDER BY rolling_f90_l5 DESC
            LIMIT ?
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (team_id, season, limit))
            rows = cursor.fetchall()
            return [
                {
                    "player_id": r[0],
                    "name": r[1],
                    "rolling_f90": r[2],
                    "matches": r[3]
                }
                for r in rows
            ]

    def get_team_avg_fouls_l5(self, team_id: int, season: int) -> float:
        """Promedio proyectado de faltas por partido para el equipo completo."""
        query = """
            SELECT AVG(rolling_f90_l5)
            FROM player_spark_features
            WHERE team_id = ? AND season = ?
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (team_id, season))
            row = cursor.fetchone()
            return float(row[0]) if row and row[0] else 12.0