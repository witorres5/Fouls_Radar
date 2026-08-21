# run_local_sync.py
import os
import logging
from databases.connection import DatabaseManager
from controllers.fixture_controller import FixtureController
from controllers.betting_controller import BettingController
from config.constants import TARGET_LEAGUES, CURRENT_SEASON

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_full_sync():
    try:
        # Usamos tu base de datos local predeterminada o la que tengas en entorno
        db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
        auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
        
        db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
        logging.info("🔌 Conexión establecida con la base de datos local.")

        # Recorremos todas las ligas configuradas en TARGET_LEAGUES
        for league_id, league_info in TARGET_LEAGUES.items():
            league_name = league_info.get("name", f"Liga {league_id}")
            
            # Sincronizamos para la temporada actual
            for season in [CURRENT_SEASON]:
                logging.info(f"🔄 Sincronizando {league_name} (ID: {league_id}) - Temporada {season}...")
                
                try:
                    # 1. Sincronizar partidos y estadísticas de la liga
                    FixtureController.sync_fixtures_and_stats(db_manager, league_id, season)
                    
                    # 2. Generar automáticamente apuestas simuladas de alta probabilidad (>80%)
                    picks = BettingController.get_high_probability_bets(db_manager, league_id, season)
                    for pick in picks:
                        BettingController.save_simulation(db_manager, pick)
                        
                    logging.info(f"✅ Sincronización exitosa para {league_name} ({season}).")
                except Exception as sub_err:
                    logging.error(f"⚠️ Error sincronizando {league_name} ({season}): {sub_err}")

        logging.info("🎉 ¡Sincronización global local completada con éxito!")

    except Exception as e:
        logging.error(f"❌ Error crítico en el proceso de sincronización: {e}")

if __name__ == "__main__":
    run_full_sync()