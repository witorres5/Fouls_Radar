# scripts/fixtures_sync.py
import logging
from databases.connection import DatabaseManager
from controllers.fixture_controller import FixtureController
from controllers.betting_controller import BettingController
from config.constants import TARGET_LEAGUES, CURRENT_SEASON

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def run_sync():
    db_manager = DatabaseManager() # Tu conexión a Turso
    
    for league_id in TARGET_LEAGUES:
        logging.info(f"Sincronizando Liga {league_id}...")
        
        # 1. Sync partidos con lógica 'INSERT OR REPLACE'
        FixtureController.sync_fixtures_and_stats(db_manager, league_id, CURRENT_SEASON)
        
        # 2. Obtener picks y guardarlos con 'save_bet_unique'
        picks = BettingController.get_high_probability_bets(db_manager, league_id, CURRENT_SEASON)
        for pick in picks:
            if BettingController.save_bet_unique(db_manager, pick):
                logging.info(f"Nuevo pick guardado: {pick['match_name']}")
            else:
                logging.info(f"Pick ya existente (omitido): {pick['match_name']}")

if __name__ == "__main__":
    run_sync()