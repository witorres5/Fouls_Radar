# databases/betting_repository.py
import pandas as pd
from typing import Dict, Any, List, Optional
from databases.connection import DatabaseManager

class BettingRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save_bet_unique(self, bet_data: Dict[str, Any]) -> bool:
        """Guarda solo si no existe la misma apuesta para este partido y mercado."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            clean_match = str(bet_data.get('match_name', '')).strip()
            clean_market = str(bet_data.get('market', '')).strip()
            league_id = bet_data.get('league_id')
            season = bet_data.get('season')
            
            cursor.execute("""
                SELECT id FROM simulated_bets 
                WHERE league_id = ? 
                  AND season = ? 
                  AND UPPER(TRIM(match_name)) = UPPER(?) 
                  AND UPPER(TRIM(market)) = UPPER(?)
            """, (league_id, season, clean_match, clean_market))
            
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO simulated_bets (
                        fixture_id, league_id, season, match_name, referee,
                        market, probability, simulated_odds, odds, stake, match_date, status, notified_telegram
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
                """, (
                    bet_data.get('fixture_id'),
                    league_id, 
                    season, 
                    clean_match, 
                    bet_data.get('referee', 'Árbitro no asignado'), 
                    clean_market, 
                    bet_data.get('probability', 0.0), 
                    bet_data.get('simulated_odds', bet_data.get('odds', 1.85)),
                    bet_data.get('odds', 1.85),
                    bet_data.get('stake', 10.0),
                    bet_data.get("match_date"),
                    bet_data.get("notified_telegram", 0)
                ))
                return True
        return False

    def exists_bet(self, league_id: int, season: int, match_name: str, market: str) -> bool:
        """Verifica si una apuesta ya existe en la base de datos."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM simulated_bets 
                WHERE league_id = ? 
                  AND season = ? 
                  AND UPPER(TRIM(match_name)) = UPPER(?) 
                  AND UPPER(TRIM(market)) = UPPER(?)
                LIMIT 1;
            """, (league_id, season, match_name.strip(), market.strip()))
            return cursor.fetchone() is not None

    def get_simulated_bets(self, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene el historial de apuestas simuladas para la vista."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT match_name, referee, market, probability, odds, status, created_at
                FROM simulated_bets
                WHERE league_id = ? AND season = ?
                ORDER BY created_at DESC
            """, (league_id, season))
            rows = cursor.fetchall()
            
        if rows:
            return pd.DataFrame(rows, columns=["Partido", "Árbitro", "Mercado", "Probabilidad", "Cuota", "Estado", "Fecha"])
        return pd.DataFrame()

    @staticmethod
    def get_pending_bets_by_date(db_manager: DatabaseManager, league_id: int, season: int, today_str: str) -> list:
        """Obtiene las apuestas pendientes para la fecha actual o general."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, match_name, market, fixture_id
                FROM simulated_bets 
                WHERE status = 'PENDIENTE' 
                  AND league_id = ? 
                  AND season = ?
                  AND (match_date LIKE ? OR match_date IS NULL OR match_date = '')
            """
            cursor.execute(query, (league_id, season, f'%{today_str}%'))
            return cursor.fetchall()

    @staticmethod
    def get_fixture_result(db_manager: DatabaseManager, match_name: str, league_id: int, season: int, fixture_id: Optional[int] = None):
        """Busca el resultado del partido por fixture_id o coincidencia de nombres."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            if fixture_id:
                cursor.execute("""
                    SELECT fixture_id, status, total_fouls, total_yellow_cards 
                    FROM match_fixtures 
                    WHERE fixture_id = ?
                    LIMIT 1;
                """, (fixture_id,))
                res = cursor.fetchone()
                if res:
                    return res

            teams = match_name.split(" vs ") if " vs " in match_name else match_name.split(" - ")
            if len(teams) == 2:
                home_part, away_part = f"%{teams[0].strip()}%", f"%{teams[1].strip()}%"
                query = """
                    SELECT fixture_id, status, total_fouls, total_yellow_cards 
                    FROM match_fixtures 
                    WHERE league_id = ? 
                      AND season = ? 
                      AND UPPER(home_team) LIKE UPPER(?)
                      AND UPPER(away_team) LIKE UPPER(?)
                    LIMIT 1;
                """
                cursor.execute(query, (league_id, season, home_part, away_part))
            else:
                query = """
                    SELECT fixture_id, status, total_fouls, total_yellow_cards 
                    FROM match_fixtures 
                    WHERE league_id = ? 
                      AND season = ? 
                      AND UPPER(home_team || ' vs ' || away_team) LIKE UPPER(?)
                    LIMIT 1;
                """
                cursor.execute(query, (league_id, season, f"%{match_name.strip()}%"))
                
            return cursor.fetchone()

    @staticmethod
    def update_bet_status(db_manager: DatabaseManager, bet_id: int, new_status: str):
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE simulated_bets SET status = ? WHERE id = ?
            """, (new_status, bet_id))

    @staticmethod
    def get_evaluated_bets(db_manager: DatabaseManager, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene las apuestas con estado GANADA o PERDIDA con fallback seguro para odds/stake."""
        query = """
            SELECT 
                match_date, 
                match_name, 
                market, 
                probability, 
                COALESCE(odds, simulated_odds, 1.85) as odds, 
                COALESCE(stake, 10.0) as stake, 
                status, 
                created_at
            FROM simulated_bets
            WHERE status IN ('GANADA', 'PERDIDA')
              AND league_id = ? AND season = ?
            ORDER BY match_date ASC
        """
        with db_manager.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=(league_id, season))

    @staticmethod
    def get_high_prob_pending_bets_today(db_manager: DatabaseManager, today_str: str) -> list:
        """Obtiene las apuestas pendientes de hoy con probabilidad >= 90%."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, 
                    match_name, 
                    market, 
                    referee, 
                    probability, 
                    COALESCE(odds, simulated_odds, 1.80) AS odds, 
                    match_date
                FROM simulated_bets
                WHERE status = 'PENDIENTE' 
                  AND (match_date LIKE ? OR match_date IS NULL)
                  AND probability >= 90.0
                ORDER BY probability DESC
            """, (f"%{today_str}%",))
            return cursor.fetchall()

    @staticmethod
    def get_player_stats_by_fixture(db_manager: DatabaseManager, fixture_id: int, player_name: str) -> Optional[dict]:
        """Obtiene las estadísticas de un jugador en un fixture."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            clean_name = player_name.strip()

            cursor.execute("""
                SELECT 
                    COALESCE(fouls_committed, 0) AS fouls_committed, 
                    COALESCE(yellow_cards, 0) AS yellow_cards
                FROM player_fixture_stats
                WHERE fixture_id = ? 
                  AND UPPER(player_name) LIKE UPPER(?)
                LIMIT 1
            """, (fixture_id, f"%{clean_name}%"))
            row = cursor.fetchone()

            if not row and ("." in clean_name or " " in clean_name):
                surname = clean_name.split()[-1].replace(".", "").strip()
                if len(surname) > 2:
                    cursor.execute("""
                        SELECT 
                            COALESCE(fouls_committed, 0) AS fouls_committed, 
                            COALESCE(yellow_cards, 0) AS yellow_cards
                        FROM player_fixture_stats
                        WHERE fixture_id = ? 
                          AND UPPER(player_name) LIKE UPPER(?)
                        LIMIT 1
                    """, (fixture_id, f"%{surname}%"))
                    row = cursor.fetchone()

            if row:
                return {
                    "fouls_committed": row[0],
                    "yellow_cards": row[1]
                }
            return None

    @staticmethod
    def save_player_fixture_stats(db_manager: DatabaseManager, stats_list: list):
        """Inserta o actualiza las estadísticas de jugadores para un fixture."""
        if not stats_list:
            return

        query = """
            INSERT INTO player_fixture_stats 
                (fixture_id, player_id, player_name, team_id, fouls_committed, yellow_cards, red_cards)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id, player_id) DO UPDATE SET
                player_name = excluded.player_name,
                team_id = excluded.team_id,
                fouls_committed = excluded.fouls_committed,
                yellow_cards = excluded.yellow_cards,
                red_cards = excluded.red_cards
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, stats_list)