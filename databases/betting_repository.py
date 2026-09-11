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
    def get_all_pending_bets(db_manager: DatabaseManager, league_id: Optional[int] = None, season: Optional[int] = None) -> list:
        """
        Obtiene TODAS las apuestas con estado 'PENDIENTE' sin restringir por fecha,
        permitiendo evaluar partidos jugados en cualquier fecha pasada o reciente.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            conditions = ["status = 'PENDIENTE'"]
            params = []

            if league_id is not None:
                conditions.append("league_id = ?")
                params.append(league_id)
            if season is not None:
                conditions.append("season = ?")
                params.append(season)

            where_clause = " AND ".join(conditions)
            query = f"""
                SELECT id, match_name, market, fixture_id, league_id, season, match_date
                FROM simulated_bets 
                WHERE {where_clause}
                ORDER BY match_date ASC, id ASC
            """
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

    @staticmethod
    def get_pending_bets_by_date(db_manager: DatabaseManager, league_id: int, season: int, today_str: Optional[str] = None) -> list:
        """Alias compatible que delega en get_all_pending_bets para evitar que apuestas queden atrapadas."""
        return BettingRepository.get_all_pending_bets(db_manager, league_id, season)

    @staticmethod
    def get_fixture_result(db_manager: DatabaseManager, match_name: str, league_id: int, season: int, fixture_id: Optional[int] = None):
        """Busca el resultado del partido por fixture_id o coincidencia flexible de nombres."""
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

            # Limpieza y búsqueda por nombres de equipos
            clean_name = match_name.replace(" - ", " vs ")
            teams = clean_name.split(" vs ")
            if len(teams) == 2:
                home_raw, away_raw = teams[0].strip(), teams[1].strip()
                # Quitar prefijos/sufijos comunes para maximizar match
                strip_words = ["FC", "CF", "SC", "CD", "AC", "Club", "Atlético", "Atletico", "Real", "Deportivo"]
                home_core = home_raw
                away_core = away_raw
                for w in strip_words:
                    home_core = home_core.replace(w, "").strip()
                    away_core = away_core.replace(w, "").strip()
                
                query = """
                    SELECT fixture_id, status, total_fouls, total_yellow_cards 
                    FROM match_fixtures 
                    WHERE league_id = ? 
                      AND season = ? 
                      AND (
                          (UPPER(home_team) LIKE UPPER(?) AND UPPER(away_team) LIKE UPPER(?))
                          OR (UPPER(home_team) LIKE UPPER(?) AND UPPER(away_team) LIKE UPPER(?))
                      )
                    LIMIT 1;
                """
                cursor.execute(query, (
                    league_id, season,
                    f"%{home_raw}%", f"%{away_raw}%",
                    f"%{home_core}%", f"%{away_core}%"
                ))
                res = cursor.fetchone()
                if res:
                    return res
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
                res = cursor.fetchone()
                if res:
                    return res
                
            return None

    @staticmethod
    def update_bet_fixture_id(db_manager: DatabaseManager, bet_id: int, fixture_id: int):
        """Asocia el fixture_id exacto a una apuesta para acelerar evaluaciones futuras."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE simulated_bets SET fixture_id = ? WHERE id = ?", (fixture_id, bet_id))

    @staticmethod
    def update_bet_status(db_manager: DatabaseManager, bet_id: int, new_status: str):
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE simulated_bets SET status = ? WHERE id = ?
            """, (new_status, bet_id))

    @staticmethod
    def fixture_has_player_stats(db_manager: DatabaseManager, fixture_id: int) -> bool:
        """Verifica si un fixture ya tiene estadísticas individuales de jugadores registradas."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM player_fixture_stats WHERE fixture_id = ?", (fixture_id,))
            row = cursor.fetchone()
            return bool(row and row[0] > 0)


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
                WHERE notified_telegram = 0 AND status = 'PENDIENTE' 
                  AND (match_date LIKE ? OR match_date IS NULL)
                  AND probability >= 90.0
                ORDER BY probability DESC
            """, (f"%{today_str}%",))
            return cursor.fetchall()

    @staticmethod
    def get_player_stats_by_fixture(db_manager: DatabaseManager, fixture_id: int, player_name: str) -> Optional[dict]:
        """
        Obtiene las estadísticas de un jugador en un fixture con soporte para
        nombres abreviados ('N. Kanté'), acentos ('Muñoz' vs 'Munoz') y búsquedas por apellido.
        """
        import unicodedata
        
        def strip_accents(s: str) -> str:
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

        clean_name = player_name.strip()
        norm_name = strip_accents(clean_name).lower()

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Búsqueda directa exacta/LIKE
            cursor.execute("""
                SELECT player_name, COALESCE(fouls_committed, 0), COALESCE(yellow_cards, 0)
                FROM player_fixture_stats
                WHERE fixture_id = ?
            """, (fixture_id,))
            rows = cursor.fetchall()
            
            if not rows:
                return None

            # 2. Match exacto o por contención en memoria (quitando acentos y mayúsculas)
            for r in rows:
                db_pname = r[0] or ""
                db_norm = strip_accents(db_pname).lower()
                
                # Match directo o subcadena
                if norm_name in db_norm or db_norm in norm_name:
                    return {"fouls_committed": r[1], "yellow_cards": r[2]}

            # 3. Match por apellido o palabras significativas (>= 3 letras)
            # Ej: "N. Kanté" -> "kante", "Marc Bernal" -> "bernal", "V. Muñoz" -> "munoz"
            words = [w.replace(".", "").replace("'", "").strip() for w in norm_name.split() if len(w.replace(".", "").strip()) >= 3]
            if words:
                # Priorizar la última palabra (apellido)
                for w in reversed(words):
                    for r in rows:
                        db_norm = strip_accents(r[0] or "").lower()
                        if w in db_norm:
                            return {"fouls_committed": r[1], "yellow_cards": r[2]}

            return None


    @staticmethod
    def save_player_fixture_stats(db_manager: DatabaseManager, stats_list: list):
        """Inserta o actualiza las estadísticas de jugadores para un fixture."""
        if not stats_list:
            return

        query = """
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
        """
        normalized_stats = []
        for p in stats_list:
            if len(p) == 9:
                normalized_stats.append(p)
            elif len(p) == 7:
                # (fix_id, p_id, p_name, t_id, fouls, yellow, red) -> añadir minutes=0, drawn=0
                normalized_stats.append((p[0], p[1], p[2], p[3], 0, p[4], 0, p[5], p[6]))
            elif len(p) == 8:
                normalized_stats.append((p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], 0))
            else:
                normalized_stats.append(p)

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, normalized_stats)
            
    @staticmethod
    def mark_as_notified(db_manager: DatabaseManager, bet_id: int) -> bool:
        """Marca una apuesta como notificada para prevenir duplicados futuros."""
        query = "UPDATE simulated_bets SET notified_telegram = 1 WHERE id = ? AND notified_telegram = 0"
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (bet_id,))
            return cursor.rowcount > 0