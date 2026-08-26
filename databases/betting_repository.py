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
                    match_date TEXT,
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
        """Busca el resultado del partido por coincidencia flexible del nombre del encuentro."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Separar los nombres de los equipos si vienen en formato "Local vs Visitante"
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
                # Búsqueda general si el formato del string es diferente
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
    def update_bet_status(db_manager, bet_id, new_status):
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE simulated_bets SET status = ? WHERE id = ?
            """, (new_status, bet_id))
            conn.commit()
            
    @staticmethod
    def get_pending_bets_by_date(db_manager, league_id, season, today_str):
        """Obtiene las apuestas pendientes para la fecha actual consultando directamente el campo match_date."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, match_name, market 
                FROM simulated_bets 
                WHERE status = 'PENDIENTE' 
                  AND league_id = ? 
                  AND season = ?
                  AND match_date LIKE ?
            """
            cursor.execute(query, (league_id, season, f'%{today_str}%'))
            return cursor.fetchall()


    def save_bet_unique(self, bet_data):
            """Guarda solo si no existe la misma apuesta para este partido y mercado."""
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                clean_match = bet_data['match_name'].strip()
                clean_market = bet_data['market'].strip()
                
                # Comprobación estricta usando UPPER y TRIM
                cursor.execute("""
                    SELECT id FROM simulated_bets 
                    WHERE league_id = ? 
                      AND season = ? 
                      AND UPPER(TRIM(match_name)) = UPPER(?) 
                      AND UPPER(TRIM(market)) = UPPER(?)
                """, (bet_data['league_id'], bet_data['season'], clean_match, clean_market))
                
                if cursor.fetchone() is None:
                    cursor.execute("""
                        INSERT INTO simulated_bets (league_id, season, match_name, referee, market, probability, simulated_odds,match_date, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?,?, 'PENDIENTE')
                    """, (
                        bet_data['league_id'], 
                        bet_data['season'], 
                        clean_match, 
                        bet_data.get('referee', 'Árbitro no asignado'), 
                        clean_market, 
                        bet_data['probability'], 
                        bet_data.get('odds', bet_data.get('simulated_odds', 1.80)),
                        bet_data.get("match_date")
                    ))
                    return True
            return False
        

    @staticmethod
    def get_evaluated_bets(db_manager, league_id: int, season: int) -> pd.DataFrame:
        """Obtiene las apuestas con estado GANADA o PERDIDA con fallback para odds/stake."""
        query = """
            SELECT 
                match_date, 
                match_name, 
                market, 
                probability, 
                COALESCE(odds, 1.85) as odds, 
                COALESCE(stake, 10.0) as stake, 
                status, 
                created_at
            FROM simulated_bets
            WHERE status IN ('GANADA', 'PERDIDA')
              AND league_id = ? AND season = ?
            ORDER BY match_date ASC
        """
        with db_manager.get_connection() as conn:
            try:
                return pd.read_sql_query(query, conn, params=(league_id, season))
            except Exception:
                # Fallback en caso de que las columnas odds/stake aún no existan
                fallback_query = """
                    SELECT 
                        match_date, match_name, market, probability, 
                        1.85 as odds, 10.0 as stake, status, created_at
                    FROM simulated_bets
                    WHERE status IN ('GANADA', 'PERDIDA')
                      AND league_id = ? AND season = ?
                    ORDER BY match_date ASC
                """
                return pd.read_sql_query(fallback_query, conn, params=(league_id, season))       


    def get_high_prob_pending_bets_today(db_manager, today_str: str) -> list:
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
                    COALESCE(simulated_odds, 1.80) AS odds, 
                    match_date
                FROM simulated_bets
                WHERE status = 'PENDIENTE' 
                  AND match_date LIKE ? 
                  AND probability >= 90.0
                ORDER BY probability DESC
            """, (f"%{today_str}%",))
            return cursor.fetchall()