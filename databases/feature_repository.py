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