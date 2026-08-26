import logging
from typing import Dict, Any, List
from databases.connection import DatabaseManager
import pandas as pd
from typing import List

logger = logging.getLogger("FoulsTracker.FixtureRepository")

class FixtureRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._init_db()

    def _init_db(self):
        """Crea las tablas necesarias y asegura sus columnas."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    entity_name TEXT PRIMARY KEY,
                    last_updated TEXT
                )
            """)
            try:
                cursor.execute("ALTER TABLE sync_metadata ADD COLUMN last_updated TEXT")
            except Exception:
                pass
            conn.commit()

    def update_player_match_stats(self, player_stats: Dict[int, Dict[str, Any]], league_id: int, season: int) -> None:
        """Actualiza e incrementa estadísticas acumuladas recalculando fouls_per_90 de forma eficiente."""
        
        if not player_stats:
            return

        # Preparamos los parámetros para executemany
        payload = []
        for player_id, stats in player_stats.items():
            minutes = int(stats.get("minutes_played", 0) or 0)
            committed = int(stats.get("fouls_committed", 0) or 0)
            drawn = int(stats.get("fouls_drawn", 0) or 0)
            yellow = int(stats.get("yellow_cards", 0) or 0)
            red = int(stats.get("red_cards", 0) or 0)
            
            payload.append((minutes, committed, drawn, yellow, red, player_id, league_id, season))

        query = """
            UPDATE players 
            SET minutes_played = COALESCE(minutes_played, 0) + ?,
                fouls_committed = COALESCE(fouls_committed, 0) + ?,
                fouls_drawn = COALESCE(fouls_drawn, 0) + ?,
                yellow_cards = COALESCE(yellow_cards, 0) + ?,
                red_cards = COALESCE(red_cards, 0) + ?,
                fouls_per_90 = CASE 
                    WHEN (COALESCE(minutes_played, 0) + ?) > 0 THEN 
                        ROUND((CAST(COALESCE(fouls_committed, 0) + ? AS FLOAT) / (COALESCE(minutes_played, 0) + ?)) * 90.0, 2)
                    ELSE 0.0 
                END
            WHERE player_id = ? AND league_id = ? AND season = ?
        """

        # Duplicamos minutos y fouls_committed en la tupla para el cálculo directo
        exec_payload = [
            (
                p[0], p[1], p[2], p[3], p[4], # deltas: min, committed, drawn, yellow, red
                p[0], p[1], p[0],             # us de minutes y committed para el CASE
                p[5], p[6], p[7]              # WHERE: player_id, league_id, season
            )
            for p in payload
        ]

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, exec_payload)
            conn.commit()
            
        logger.info(f"Estadísticas de {len(player_stats)} jugadores actualizadas eficientemente.")

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

    def get_top_fouler_for_team(self, team_id: int, season: int) -> dict:
        """Obtiene el jugador con más faltas de un equipo."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT player_name, COALESCE(fouls_committed, 0)
                FROM players 
                WHERE team_id = ? AND season = ?
                ORDER BY fouls_committed DESC
                LIMIT 1
            """, (team_id, season))
            row = cursor.fetchone()
            if row:
                return {"name": row[0], "avg": float(row[1])}
        return {"name": "N/D", "avg": 0.0}

    def get_competition_summary(self, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene el resumen ordenado y mapeado de la competición para evitar desalineación de columnas."""
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

    def get_competition_fouls_summary(self, league_id: int, season: int) -> pd.DataFrame:
        """Redirige al resumen unificado de la competición."""
        return self.get_competition_summary(league_id, season)

    def get_top_foulers_for_teams(self, team_ids: List[int], season: int) -> dict:
        """Obtiene el top de faltas y faltas por 90 min para una lista de equipos en una sola consulta batch."""
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
            team_id = row["team_id"] if hasattr(row, "keys") else row[0]
            player_name = row["player_name"] if hasattr(row, "keys") else row[1]
            fouls = float(row["fouls_committed"] if hasattr(row, "keys") else row[2])
            minutes = float(row["minutes_played"] if hasattr(row, "keys") else row[3])
            f90_sql = float(row["fouls_per_90"] if hasattr(row, "keys") else row[4])
            
            # Estrategia de cálculo de fouls_per_90:
            # 1. Usa fouls_per_90 de la base de datos si existe y es > 0.
            # 2. Si es 0 pero hay minutos jugados, calcula: (faltas / minutos) * 90.
            # 3. Si no hay minutos guardados, asume 3 partidos estándar (~270 mins) como estimación.
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

    def save_fixture(self, fixture_data: dict) -> None:
        """Guarda o actualiza un partido general en la tabla fixtures."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
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
                conn.commit()

    def get_team_avg_fouls(self, team_name: str, league_id: int, season: int) -> float:
        """Calcula el promedio de faltas cometidas por partido de un equipo."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT AVG(total_fouls) 
                FROM (
                    SELECT total_fouls FROM match_fixtures 
                    WHERE league_id = ? AND season = ? AND UPPER(home_team) LIKE UPPER(?) AND status = 'FT'
                    UNION ALL
                    SELECT total_fouls FROM match_fixtures 
                    WHERE league_id = ? AND season = ? AND UPPER(away_team) LIKE UPPER(?) AND status = 'FT'
                );
            """
            pattern = f"%{team_name.strip()}%"
            cursor.execute(query, (league_id, season, pattern, league_id, season, pattern))
            res = cursor.fetchone()
            return float(res[0]) if res and res[0] is not None else 12.0

    def get_referee_avg_fouls(self, referee_name: str) -> float:
        """Obtiene el promedio de faltas pitadas por un árbitro."""
        if not referee_name or "Estándar" in referee_name or "no asignado" in referee_name.lower():
            return 24.0
            
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT AVG(total_fouls) 
                FROM match_fixtures 
                WHERE UPPER(referee_name) LIKE UPPER(?) AND status = 'FT';
            """
            cursor.execute(query, (f"%{referee_name.strip()}%",))
            res = cursor.fetchone()
            return float(res[0]) if res and res[0] is not None else 24.0