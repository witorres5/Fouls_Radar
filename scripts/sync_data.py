import sys
import os
from datetime import datetime
import pytz
import logging

# Asegura el path de los módulos si lo necesitas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.constants import TARGET_LEAGUES
from databases.connection import DatabaseManager
from controllers.fixture_controller import FixtureController
from controllers.betting_controller import BettingController
# Importa tus ligas configuradas
# from config.constants import TARGET_LEAGUES, CURRENT_SEASON

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_daily_sync():
    try:
        # Configurar conexión a la base de datos (Soporta local y GitHub Actions)
        db_url = os.environ.get("TURSO_DATABASE_URL", "local.db")
        auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
        db_manager = DatabaseManager(db_url=db_url, auth_token=auth_token)
        logging.info("🔗 Conexión establecida con la base de datos.")

        # Obtener la fecha actual en la zona horaria de Colombia
        colombia_tz = pytz.timezone('America/Bogota')
        today_str = datetime.now(colombia_tz).strftime('%Y-%m-%d')
        current_year = datetime.now(colombia_tz).year
        
        logging.info(f"📅 Sincronizando partidos para el día de hoy: {today_str} (Temporada: {current_year})")

        # Recorremos las ligas configuradas
        for league_id, league_info in TARGET_LEAGUES.items():
            league_name = league_info.get("name", f"Liga {league_id}")
            
            try:
                logging.info(f"⚽ Consultando {league_name} para la fecha {today_str}...")
                
                # Opción A: Si tu controlador permite buscar por fecha exacta (Recomendado)
                # FixtureController.sync_fixtures_by_date(db_manager, league_id, current_year, today_str)
                
                # Opción B: Si usas el método actual pero acotado a la temporada en curso sin bucles históricos
                FixtureController.sync_fixtures_and_stats(db_manager, league_id, current_year)

                # Generar apuestas simuladas de alta probabilidad basadas en los datos frescos
                picks = BettingController.get_high_probability_bets(db_manager, league_id, current_year)
                for pick in picks:
                    BettingController.save_simulation(db_manager, pick)

                logging.info(f"✅ Sincronización exitosa para {league_name} (Hoy).")
                
            except Exception as sub_err:
                logging.error(f"⚠️ Error sincronizando {league_name}: {sub_err}")

        logging.info("🎉 ¡Sincronización diaria completada con éxito!")

    except Exception as e:
        logging.error(f"❌ Error crítico en el proceso de sincronización: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_daily_sync()