import sqlite3
import pandas as pd

class BettingSimulator:
    def __init__(self, db_path="fouls_tracker.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER UNIQUE,
                    match_date TEXT,
                    league_id INTEGER,
                    home_team TEXT,
                    away_team TEXT,
                    referee_name TEXT,
                    predicted_fouls REAL,
                    bet_line REAL,
                    bet_type TEXT,
                    edge REAL,
                    status TEXT DEFAULT 'PENDING'
                )
            """)
            conn.commit()

    def evaluate_and_save_bet(self, fixture_info: dict, predicted_fouls: float, min_edge: float):
        """Calcula si hay valor y guarda la apuesta en la BD."""
        linea_casa = round(predicted_fouls) - 0.5
        diferencia = abs(predicted_fouls - linea_casa)
        bet_type = "OVER" if predicted_fouls > linea_casa else "UNDER"

        if diferencia >= min_edge:
            bet_data = {
                "fixture_id": fixture_info["fixture_id"],
                "match_date": fixture_info["match_date"],
                "league_id": fixture_info["league_id"],
                "home_team": fixture_info["home_team"],
                "away_team": fixture_info["away_team"],
                "referee_name": fixture_info.get("referee", "Desconocido"),
                "predicted_fouls": predicted_fouls,
                "bet_line": linea_casa,
                "bet_type": bet_type,
                "edge": round(diferencia, 2)
            }
            self._save_bet(bet_data)
            return {"placed": True, "type": bet_type, "line": linea_casa, "edge": diferencia}
        
        return {"placed": False, "edge": diferencia}

    def _save_bet(self, bet_data: dict):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO simulated_bets 
                (fixture_id, match_date, league_id, home_team, away_team, referee_name, predicted_fouls, bet_line, bet_type, edge)
                VALUES (:fixture_id, :match_date, :league_id, :home_team, :away_team, :referee_name, :predicted_fouls, :bet_line, :bet_type, :edge)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    predicted_fouls=excluded.predicted_fouls,
                    bet_line=excluded.bet_line,
                    bet_type=excluded.bet_type,
                    edge=excluded.edge
            """, bet_data)
            conn.commit()

    def get_bets_history(self) -> pd.DataFrame:
        with self._get_connection() as conn:
            return pd.read_sql("SELECT * FROM simulated_bets ORDER BY id DESC", conn)