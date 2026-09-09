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
        """Obtiene los infractores top ajustando filtros y realizando fallback a la tabla de jugadores."""
        # 1. Consulta directa en player_spark_features (filtro >= 1 partido)
        query_direct = """
            SELECT player_id, player_name, rolling_f90_l5, total_matches_played
            FROM player_spark_features
            WHERE team_id = ? AND season = ? AND total_matches_played >= 1
            ORDER BY rolling_f90_l5 DESC
            LIMIT ?
        """
        
        # 2. Consulta fallback uniendo con la tabla players por si team_id vino nulo en Spark
        query_fallback = """
            SELECT psf.player_id, psf.player_name, psf.rolling_f90_l5, psf.total_matches_played
            FROM player_spark_features psf
            JOIN players p ON psf.player_id = p.player_id AND psf.season = p.season
            WHERE p.team_id = ? AND psf.season = ?
            ORDER BY psf.rolling_f90_l5 DESC
            LIMIT ?
        """

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Intento 1: Búsqueda directa
            cursor.execute(query_direct, (team_id, season, limit))
            rows = cursor.fetchall()

            # Intento 2: Fallback vía tabla de jugadores
            if not rows:
                cursor.execute(query_fallback, (team_id, season, limit))
                rows = cursor.fetchall()

            return [
                {
                    "player_id": r[0],
                    "name": r[1],
                    "rolling_f90": float(r[2]),
                    "matches": int(r[3])
                }
                for r in rows
            ]

    def get_team_avg_fouls_l5(self, team_id: int, season: int) -> float:
        """Promedio proyectado de faltas por equipo sumando la media de sus jugadores."""
        query = """
            SELECT SUM(rolling_f90_l5) / 11.0
            FROM (
                SELECT rolling_f90_l5 
                FROM player_spark_features 
                WHERE team_id = ? AND season = ?
                ORDER BY rolling_f90_l5 DESC 
                LIMIT 11
            )
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (team_id, season))
            row = cursor.fetchone()
            
            # Retorna el promedio real o 0.0 si la liga no tiene datos históricos sincronizados
            if row and row[0] is not None and row[0] > 0:
                return float(row[0])
            return 0.0
        
    def get_matchup_frictions(self, home_team_id: int, away_team_id: int, season: int) -> list:
        """
        Calcula los Duelos de Alta Fricción cruzando:
        1. Infractores Local (F90) vs Provocadores Visitante (FD90)
        2. Infractores Visitante (F90) vs Provocadores Local (FD90)
        """
        query_committers = """
            SELECT player_id, player_name, rolling_f90_l5
            FROM player_spark_features
            WHERE (team_id = ? OR player_id IN (SELECT player_id FROM players WHERE team_id = ?))
              AND season = ?
            ORDER BY rolling_f90_l5 DESC
            LIMIT 2
        """
        
        query_drawers = """
            SELECT player_id, player_name, rolling_fd90_l5
            FROM player_spark_features
            WHERE (team_id = ? OR player_id IN (SELECT player_id FROM players WHERE team_id = ?))
              AND season = ?
            ORDER BY rolling_fd90_l5 DESC
            LIMIT 2
        """

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Cruce 1: Infractores Local vs Provocadores Visitante
            cursor.execute(query_committers, (home_team_id, home_team_id, season))
            home_committers = cursor.fetchall()

            cursor.execute(query_drawers, (away_team_id, away_team_id, season))
            away_drawers = cursor.fetchall()

            # Cruce 2: Infractores Visitante vs Provocadores Local
            cursor.execute(query_committers, (away_team_id, away_team_id, season))
            away_committers = cursor.fetchall()

            cursor.execute(query_drawers, (home_team_id, home_team_id, season))
            home_drawers = cursor.fetchall()

            matchups = []

            # Evaluar Cruce 1
            for hc in home_committers:
                for ad in away_drawers:
                    f90 = float(hc[2]) if hc[2] else 0.0
                    fd90 = float(ad[2]) if ad[2] else 0.0
                    if f90 > 0 and fd90 > 0:
                        friction_index = round(f90 * fd90, 2)
                        matchups.append({
                            "committer": hc[1],
                            "committer_side": "Local",
                            "committer_f90": f90,
                            "drawer": ad[1],
                            "drawer_side": "Visitante",
                            "drawer_fd90": fd90,
                            "friction_index": friction_index
                        })

            # Evaluar Cruce 2
            for ac in away_committers:
                for hd in home_drawers:
                    f90 = float(ac[2]) if ac[2] else 0.0
                    fd90 = float(hd[2]) if hd[2] else 0.0
                    if f90 > 0 and fd90 > 0:
                        friction_index = round(f90 * fd90, 2)
                        matchups.append({
                            "committer": ac[1],
                            "committer_side": "Visitante",
                            "committer_f90": f90,
                            "drawer": hd[1],
                            "drawer_side": "Local",
                            "drawer_fd90": fd90,
                            "friction_index": friction_index
                        })

            # Ordenar por el mayor Índice de Fricción
            return sorted(matchups, key=lambda x: x["friction_index"], reverse=True)