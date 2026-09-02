# scripts/fixtures_sync.py
import sys
import os
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from databases.connection import DatabaseManager
from controllers.fixture_controller import FixtureController
from controllers.betting_controller import BettingController
from config.constants import TARGET_LEAGUES, get_current_season_for_league

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def run_sync():
    db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
    db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
    
    for league_id in TARGET_LEAGUES:
        season = get_current_season_for_league(league_id)
        logging.info(f"Sincronizando Liga {league_id} (Temporada {season})...")
        
        # 1. Sync partidos con idempotencia
        FixtureController.sync_fixtures_and_stats(db_manager, league_id, season, sync_all_season=False)
        
        # 2. Obtener picks y guardarlos con 'save_bet_unique'
        picks = BettingController.get_high_probability_bets(db_manager, league_id, season)
        for pick in picks:
            if BettingController.save_bet_unique(db_manager, pick):
                logging.info(f"Nuevo pick guardado: {pick['match_name']}")
            else:
                logging.debug(f"Pick ya existente (omitido): {pick['match_name']}")

if __name__ == "__main__":
    run_sync()