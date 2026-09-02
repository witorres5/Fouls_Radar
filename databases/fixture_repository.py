# databases/fixture_repository.py
import logging
from typing import Dict, Any, List, Optional, Tuple
from databases.connection import DatabaseManager
import pandas as pd

logger = logging.getLogger("FoulsTracker.FixtureRepository")

class FixtureRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_last_sync(self, entity_name: str) -> str:
        """Obtiene la última fecha de sincronización de fixtures."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_sync_timestamp FROM sync_metadata WHERE entity_name = ?", (entity_name,))
            row = cursor.fetchone()
            return row[0] if row else "Nunca"

    def update_sync_timestamp(self, entity_name: str, current_time: str) -> None:
        """Actualiza o inserta la marca de tiempo de sincronización."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_metadata (entity_name, last_sync_timestamp) 
                VALUES (?, ?)
                ON CONFLICT(entity_name) DO UPDATE SET last_sync_timestamp = ?
            """, (entity_name, current_time, current_time))

    def save_fixture_info(
        self, 
        fixture_id: int, 
        league_id: int, 
        season: int, 
        home_team: str, 
        away_team: str, 
        status: str, 
        match_date: str, 
        referee: str = "N/A", 
        total_fouls: int = 0, 
        total_yellow_cards: int = 0
    ) -> None:
        """Registra o actualiza la información detallada del partido en match_fixtures."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                INSERT INTO match_fixtures (
                    fixture_id, 
                    league_id, 
                    season, 
                    home_team, 
                    away_team, 
                    status, 
                    match_date, 
                    total_fouls, 
                    total_yellow_cards, 
                    referee_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    league_id = excluded.league_id,
                    season = excluded.season,
                    status = excluded.status,
                    home_team = excluded.home_team,
                    away_team = excluded.away_team,
                    match_date = excluded.match_date,
                    total_fouls = excluded.total_fouls,
                    total_yellow_cards = excluded.total_yellow_cards,
                    referee_name = excluded.referee_name;
            """
            cursor.execute(query, (
                fixture_id, 
                league_id, 
                season, 
                home_team, 
                away_team, 
                status, 
                match_date, 
                total_fouls, 
                total_yellow_cards, 
                referee
            ))

    def save_and_recalculate_fixture_stats(
        self, 
        fixture_id: int, 
        league_id: int, 
        season: int, 
        player_stats_list: List[tuple]
    ) -> None:
        """
        Inserta estadísticas en player_fixture_stats de forma idempotente y recalcula
        los acumulados en players para evitar duplicaciones.
        """
        if not player_stats_list:
            return

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Guardar o actualizar datos de cada jugador en este fixture
            cursor.executemany("""
                INSERT INTO player_fixture_stats (
                    fixture_id, player_id, player_name, team_id,
                    minutes_played, fouls_committed, fouls_drawn,
                    yellow_cards, red_cards
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id, player_id) DO UPDATE SET
                    player_name = excluded.player_name,
                    team_id = excluded.team_id,
                    minutes_played = excluded.minutes_played,
                    fouls_committed = excluded.fouls_committed,
                    fouls_drawn = excluded.fouls_drawn,
                    yellow_cards = excluded.yellow_cards,
                    red_cards = excluded.red_cards
            """, [
                (
                    p[0], p[1], p[2], p[3],
                    p[4] if len(p) > 7 else 0, # minutes_played
                    p[4] if len(p) <= 7 else p[5], # fouls_committed
                    p[5] if len(p) <= 7 else p[6], # fouls_drawn
                    p[6] if len(p) <= 7 else p[7], # yellow_cards
                    p[7] if len(p) <= 7 else (p[8] if len(p) > 8 else 0) # red_cards
                ) if len(p) >= 7 else p
                for p in player_stats_list
            ])

            # 2. Recalcular las estadísticas acumuladas en players agregando sobre los fixtures
            cursor.execute("""
                INSERT INTO players (
                    player_id, team_id, player_name, league_id, season,
                    minutes_played, fouls_committed, fouls_drawn,
                    yellow_cards, red_cards, fouls_per_90, updated_at
                )
                SELECT 
                    pfs.player_id,
                    pfs.team_id,
                    pfs.player_name,
                    mf.league_id,
                    mf.season,
                    SUM(pfs.minutes_played) AS minutes_played,
                    SUM(pfs.fouls_committed) AS fouls_committed,
                    SUM(pfs.fouls_drawn) AS fouls_drawn,
                    SUM(pfs.yellow_cards) AS yellow_cards,
                    SUM(pfs.red_cards) AS red_cards,
                    CASE 
                        WHEN SUM(pfs.minutes_played) > 0 THEN 
                            ROUND((CAST(SUM(pfs.fouls_committed) AS FLOAT) / SUM(pfs.minutes_played)) * 90.0, 2)
                        ELSE 0.0 
                    END AS fouls_per_90,
                    CURRENT_TIMESTAMP
                FROM player_fixture_stats pfs
                JOIN match_fixtures mf ON pfs.fixture_id = mf.fixture_id
                WHERE mf.league_id = ? AND mf.season = ? AND pfs.player_id IN (
                    SELECT player_id FROM player_fixture_stats WHERE fixture_id = ?
                )
                GROUP BY pfs.player_id, pfs.team_id, pfs.player_name, mf.league_id, mf.season
                ON CONFLICT(player_id, league_id, season) DO UPDATE SET
                    team_id = excluded.team_id,
                    player_name = excluded.player_name,
                    minutes_played = excluded.minutes_played,
                    fouls_committed = excluded.fouls_committed,
                    fouls_drawn = excluded.fouls_drawn,
                    yellow_cards = excluded.yellow_cards,
                    red_cards = excluded.red_cards,
                    fouls_per_90 = excluded.fouls_per_90,
                    updated_at = excluded.updated_at
            """, (league_id, season, fixture_id))

    def get_league_averages(self, league_id: int, season: int) -> Tuple[float, float]:
        """Obtiene el promedio de faltas y tarjetas por partido para una liga y temporada."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    AVG(total_fouls), 
                    AVG(total_yellow_cards) 
                FROM match_fixtures 
                WHERE league_id = ? AND season = ? AND status IN ('FT', 'AET', 'PEN')
            """, (league_id, season))
            row = cursor.fetchone()
            avg_fouls = float(row[0]) if (row and row[0] is not None) else 22.5
            avg_cards = float(row[1]) if (row and row[1] is not None) else 4.2
            return avg_fouls, avg_cards

    def get_referee_historical_stats(self, referee_name: str) -> Tuple[int, float, float]:
        """Obtiene la cantidad de partidos dirigidos y los promedios históricos de un árbitro."""
        if not referee_name or "no asignado" in referee_name.lower():
            return 0, 0.0, 0.0

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(fixture_id),
                    AVG(total_fouls),
                    AVG(total_yellow_cards)
                FROM match_fixtures
                WHERE UPPER(TRIM(referee_name)) = UPPER(TRIM(?))
                  AND status IN ('FT', 'AET', 'PEN')
                  AND total_fouls > 0
            """, (referee_name,))
            row = cursor.fetchone()
            if row and row[0]:
                matches_count = int(row[0])
                avg_fouls = float(row[1]) if row[1] is not None else 0.0
                avg_cards = float(row[2]) if row[2] is not None else 0.0
                return matches_count, avg_fouls, avg_cards
            return 0, 0.0, 0.0

    def get_top_fouler_for_team(self, team_id: int, season: int) -> dict:
        """Obtiene el jugador con más faltas de un equipo."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_name, COALESCE(fouls_committed, 0), COALESCE(fouls_per_90, 0.0)
                FROM players 
                WHERE team_id = ? AND season = ?
                ORDER BY fouls_committed DESC
                LIMIT 1
            """, (team_id, season))
            row = cursor.fetchone()
            if row:
                return {"name": row[0], "avg": float(row[1]), "fouls_per_90": float(row[2])}
        return {"name": "N/D", "avg": 0.0, "fouls_per_90": 0.0}

    def get_top_foulers_for_teams(self, team_ids: List[int], season: int) -> dict:
        """Obtiene el top de faltas y faltas por 90 min para una lista de equipos en una sola consulta."""
        if not team_ids:
            return {}
            
        placeholders = ','.join(['?'] * len(team_ids))
        query = f"""
            SELECT team_id, player_name, fouls_committed, minutes_played, fouls_per_90
            FROM (
                SELECT 
                    team_id, 
                    player_name, 
                    COALESCE(fouls_committed, 0) as fouls_committed,
                    COALESCE(minutes_played, 0) as minutes_played,
                    COALESCE(fouls_per_90, 0.0) as fouls_per_90,
                    ROW_NUMBER() OVER(PARTITION BY team_id ORDER BY COALESCE(fouls_committed, 0) DESC) as rn
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
            team_id = row[0]
            player_name = row[1]
            fouls = float(row[2])
            minutes = float(row[3])
            f90_sql = float(row[4])
            
            if f90_sql > 0:
                f90 = f90_sql
            elif minutes > 0:
                f90 = (fouls / minutes) * 90.0
            else:
                f90 = fouls / 3.0

            result[team_id] = {
                "name": player_name, 
                "avg": fouls,
                "fouls_per_90": round(f90, 2)
            }
            
        return result

    def get_competition_summary(self, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene el resumen ordenado de la competición para la vista."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    player_name, 
                    COALESCE(minutes_played, 0) AS minutes_played, 
                    COALESCE(fouls_committed, 0) AS fouls_committed, 
                    COALESCE(yellow_cards, 0) AS yellow_cards, 
                    COALESCE(red_cards, 0) AS red_cards, 
                    COALESCE(fouls_per_90, 0.0) AS fouls_per_90
                FROM players 
                WHERE CAST(league_id AS INTEGER) = CAST(? AS INTEGER) 
                  AND CAST(season AS INTEGER) = CAST(? AS INTEGER) 
                  AND minutes_played > 0
                ORDER BY fouls_committed DESC
                LIMIT 20
            """, (league_id, season))
            rows = cursor.fetchall()
            
        columns = ["Jugador", "Minutos", "Faltas Cometidas", "Tarjetas Amarillas", "Tarjetas Rojas", "Faltas por 90'"]
        if rows:
            return pd.DataFrame(rows, columns=columns)
        return pd.DataFrame(columns=columns)