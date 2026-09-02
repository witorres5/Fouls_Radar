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
            INSERT_COLS = (
                "fixture_id", "league_id", "season", "home_team", "away_team",
                "status", "match_date", "total_fouls", "total_yellow_cards", "referee_name"
            )
            UPDATE_COLS = (
                "league_id", "season", "status", "home_team", "away_team",
                "match_date", "total_fouls", "total_yellow_cards", "referee_name"
            )
            self.db_manager.safe_upsert(
                cursor,
                table="match_fixtures",
                key_cols=("fixture_id",),
                insert_cols=INSERT_COLS,
                values=(
                    fixture_id, league_id, season, home_team, away_team,
                    status, match_date, total_fouls, total_yellow_cards, referee
                ),
                update_cols=UPDATE_COLS,
            )

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

        # Normalizar tuplas a 9 elementos: (fix_id, p_id, p_name, t_id, min, fouls_c, fouls_d, yellow, red)
        def normalize(p):
            if len(p) == 9:
                return p
            elif len(p) == 7:
                return (p[0], p[1], p[2], p[3], 0, p[4], 0, p[5], p[6])
            elif len(p) == 8:
                return (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], 0)
            return p

        normalized = [normalize(p) for p in player_stats_list]

        PFS_COLS = (
            "fixture_id", "player_id", "player_name", "team_id",
            "minutes_played", "fouls_committed", "fouls_drawn", "yellow_cards", "red_cards"
        )
        PFS_UPDATE = ("player_name", "team_id", "minutes_played", "fouls_committed", "fouls_drawn", "yellow_cards", "red_cards")

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Upsert seguro en player_fixture_stats (compatible con schemas legacy sin PK)
            self.db_manager.safe_upsert_many(
                cursor,
                table="player_fixture_stats",
                key_cols=("fixture_id", "player_id"),
                insert_cols=PFS_COLS,
                rows=normalized,
                update_cols=PFS_UPDATE,
            )

            # 2. Recalcular acumulados en players desde los fixtures históricos
            player_ids = tuple(set(p[1] for p in normalized))
            placeholders = ",".join("?" * len(player_ids))

            cursor.execute(f"""
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
                    CURRENT_TIMESTAMP as updated_at
                FROM player_fixture_stats pfs
                JOIN match_fixtures mf ON pfs.fixture_id = mf.fixture_id
                WHERE mf.league_id = ? AND mf.season = ? AND pfs.player_id IN ({placeholders})
                GROUP BY pfs.player_id, pfs.team_id, pfs.player_name, mf.league_id, mf.season
            """, (league_id, season, *player_ids))

            aggregated = cursor.fetchall()

            PLAYER_COLS = (
                "player_id", "team_id", "player_name", "league_id", "season",
                "minutes_played", "fouls_committed", "fouls_drawn",
                "yellow_cards", "red_cards", "fouls_per_90", "updated_at"
            )
            PLAYER_UPDATE = (
                "team_id", "player_name", "minutes_played", "fouls_committed",
                "fouls_drawn", "yellow_cards", "red_cards", "fouls_per_90", "updated_at"
            )

            for row in aggregated:
                vals = tuple(row[i] for i in range(12))
                self.db_manager.safe_upsert(
                    cursor,
                    table="players",
                    key_cols=("player_id", "league_id", "season"),
                    insert_cols=PLAYER_COLS,
                    values=vals,
                    update_cols=PLAYER_UPDATE,
                )

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

    def get_team_drawn_fouls_avg(self, team_id: int, season: int) -> float:
        """
        Obtiene la tasa promedio de faltas recibidas (dibujadas) por el equipo rival
        por partido. Se usa como feature 'opp_drawn_per_90' en el modelo ML.
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT AVG(pfs.fouls_drawn)
                FROM player_fixture_stats pfs
                JOIN match_fixtures mf ON pfs.fixture_id = mf.fixture_id
                WHERE pfs.team_id = ?
                  AND mf.season = ?
                  AND mf.status IN ('FT', 'AET', 'PEN')
                  AND pfs.minutes_played >= 45
            """, (team_id, season))
            row = cursor.fetchone()
            val = row[0] if (row and row[0] is not None) else 0.0
            # Normalizar a por-90 (es promedio de faltas totales dibujadas del equipo por partido)
            return round(float(val) / 11.0, 4)  # aprox. por jugador

    def get_training_dataset_size(self, min_minutes: int = 45) -> int:
        """Retorna el número de filas disponibles para entrenar el modelo ML."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM player_fixture_stats pfs
                JOIN match_fixtures mf ON pfs.fixture_id = mf.fixture_id
                WHERE mf.status IN ('FT', 'AET', 'PEN')
                  AND pfs.minutes_played >= ?
                  AND pfs.fouls_committed IS NOT NULL
            """, (min_minutes,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0