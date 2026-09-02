# scripts/sync_data.py
import sys
import os
from datetime import datetime
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.constants import TARGET_LEAGUES, COLOMBIA_TZ, get_current_season_for_league
from databases.connection import DatabaseManager
from controllers.fixture_controller import FixtureController
from controllers.betting_controller import BettingController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_daily_sync():
    try:
        db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
        auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
        db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
        logging.info("🔗 Conexión establecida con la base de datos.")

        today_str = datetime.now(COLOMBIA_TZ).strftime('%Y-%m-%d')
        logging.info(f"📅 Sincronizando partidos para el día de hoy: {today_str}")

        for league_id, league_info in TARGET_LEAGUES.items():
            league_name = league_info.get("name", f"Liga {league_id}")
            season = get_current_season_for_league(league_id)
            
            try:
                logging.info(f"⚽ Sincronizando {league_name} (Temporada {season}) para fecha {today_str}...")
                
                # 1. Sincronizar partidos y estadísticas del día
                FixtureController.sync_fixtures_and_stats(db_manager, league_id, season, sync_all_season=False)

                # 2. Generar nuevas apuestas simuladas de alta probabilidad basadas en los datos frescos
                picks = BettingController.get_high_probability_bets(db_manager, league_id, season)
                for pick in picks:
                    BettingController.save_simulation(db_manager, pick)

                # 3. Evaluar y cerrar únicamente las apuestas pendientes de los partidos del día de hoy
                BettingController.evaluate_pending_bets(db_manager, league_id, season, today_str)
                logging.info(f"✅ Sincronización exitosa para {league_name}.")
                
            except Exception as sub_err:
                logging.error(f"⚠️ Error sincronizando {league_name}: {sub_err}")

        logging.info("🎉 ¡Sincronización diaria completada con éxito!")

    except Exception as e:
        logging.error(f"❌ Error crítico en el proceso de sincronización: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_daily_sync()