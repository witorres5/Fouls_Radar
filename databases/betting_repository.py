# databases/betting_repository.py
import pandas as pd

class BettingRepository:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._init_table()

    def _init_table(self):
        """Crea o reinicia la tabla de apuestas simuladas de forma limpia para evitar columnas obsoletas."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Verificamos si la tabla tiene la columna problemática 'fixture_id'
            cursor.execute("PRAGMA table_info(simulated_bets);")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Si la tabla existe pero tiene la columna vieja 'fixture_id', la recreamos limpia
            if "fixture_id" in columns:
                cursor.execute("DROP TABLE simulated_bets;")

            # Creamos la tabla con la estructura correcta y limpia
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league_id INTEGER,
                    season INTEGER,
                    match_name TEXT,
                    referee TEXT,
                    market TEXT,
                    probability REAL,
                    simulated_odds REAL,
                    status TEXT DEFAULT 'PENDIENTE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_bet(self, league_id, season, match_name, referee, market, probability, odds):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO simulated_bets (league_id, season, match_name, referee, market, probability, simulated_odds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (league_id, season, match_name, referee, market, probability, odds))

    def get_simulated_bets(self, league_id, season) -> pd.DataFrame:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT match_name, referee, market, probability, simulated_odds, status, created_at
                FROM simulated_bets
                WHERE league_id = ? AND season = ?
                ORDER BY created_at DESC
            """, (league_id, season))
            rows = cursor.fetchall()
            
        if rows:
            return pd.DataFrame(rows, columns=["Partido", "Árbitro", "Mercado", "Probabilidad", "Cuota Sim.", "Estado", "Fecha"])
        return pd.DataFrame()
    
    # databases/betting_repository.py
    def save_bet_unique(self, bet_data):
        """Guarda solo si no existe la misma apuesta para este partido."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Comprobamos por un identificador único (partido + mercado)
            cursor.execute("""
                SELECT id FROM simulated_bets 
                WHERE match_name = ? AND market = ? AND season = ?
            """, (bet_data['match_name'], bet_data['market'], bet_data['season']))
            
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO simulated_bets (league_id, season, match_name, referee, market, probability, simulated_odds, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')
                """, (
                    bet_data['league_id'], bet_data['season'], bet_data['match_name'], 
                    bet_data['referee'], bet_data['market'], bet_data['probability'], bet_data['odds']
                ))
                return True
        return False
    
    @staticmethod
    def get_pending_bets(db_manager, league_id, season):
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, match_name, market FROM simulated_bets 
                WHERE status = 'PENDIENTE' AND league_id = ? AND season = ?
            """, (league_id, season))
            return cursor.fetchall()

    @staticmethod
    def get_fixture_result(db_manager, match_name, league_id, season):
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, home_goals, away_goals FROM match_fixtures 
                WHERE match_name = ? AND league_id = ? AND season = ?
            """, (match_name, league_id, season))
            return cursor.fetchone()

    @staticmethod
    def update_bet_status(db_manager, bet_id, new_status):
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE simulated_bets SET status = ? WHERE id = ?
            """, (new_status, bet_id))
            conn.commit()