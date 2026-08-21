# controllers/fixture_controller.py
from datetime import datetime
import time
from config.constants import COLOMBIA_TZ
from databases.connection import DatabaseManager
from databases.fixture_repository import FixtureRepository
from services.api_service import APIFootballService
import streamlit as st

class FixtureController:

    @staticmethod
    def sync_fixtures_and_stats(db_manager: DatabaseManager, league_id: int, season: int):
        """Orquesta la obtención de partidos finalizados del día y actualiza las estadísticas detalladas de faltas por jugador."""
        api_service = APIFootballService()
        fixture_repo = FixtureRepository(db_manager)
        
        current_time = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        today_str = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d") # Fecha de hoy exacta
        entity_name = f"fixtures_league_{league_id}_{season}"
        
        # 1. Obtener partidos finalizados ('FT') exclusivamente del día de hoy
        print(f">>> DEBUG: Obteniendo partidos finalizados para la liga {league_id}, fecha {today_str}...")
        
        # Nota: Asegúrate de tener implementado en api_service un método que reciba la fecha o use el parámetro date=
        # Si tu servicio usa un método genérico, puedes ajustarlo para que envíe el parámetro '&date=today_str'
        fixtures = api_service.get_completed_fixtures_by_date(league_id, season, today_str)
        
        print(f">>> DEBUG: Total de partidos finalizados hoy encontrados: {len(fixtures)}")
        
        if not fixtures:
            print(">>> ADVERTENCIA: No se encontraron partidos finalizados hoy para procesar.")
            return False

        processed_fixtures = 0
        
        # 2. Iterar cada partido para extraer estadísticas detalladas por jugador
        for fixture in fixtures:
            fixture_info = fixture.get("fixture", {})
            fixture_id = fixture_info.get("id")
            
            if not fixture_id:
                continue
                
            try:
                # Obtener estadísticas detalladas (faltas, minutos, tarjetas) de los jugadores en este partido
                player_stats_map = api_service.get_fixture_player_stats(fixture_id)
                
                if player_stats_map:
                    # Actualizar de forma acumulativa en la base de datos
                    fixture_repo.update_player_match_stats(player_stats_map, league_id, season)
                    processed_fixtures += 1
                    print(f">>> DEBUG: Fixture ID {fixture_id} procesado ({len(player_stats_map)} jugadores con stats).")
                
                # Pausa corta para cuidar el rate limit de la API
                time.sleep(0.3)
            except Exception as e:
                print(f">>> ERROR procesando el fixture ID {fixture_id}: {e}")

        # 3. Actualizar la marca de tiempo de sincronización
        fixture_repo.update_sync_timestamp(entity_name, current_time)
        print(f">>> DEBUG: Sincronización de fixtures completada. Partidos procesados: {processed_fixtures}")
        
        return True
    
    @staticmethod
    def get_team_top_fouler(db_manager, team_id, season):
        """Lógica para obtener el top jugador con faltas de un equipo."""
        from databases.fixture_repository import FixtureRepository
        repo = FixtureRepository(db_manager)
        return repo.get_top_fouler_for_team(team_id, season)
    
    @staticmethod
    def get_competition_summary(db_manager, league_id, season):
        """Orquesta la obtención del resumen de comportamiento de la competición."""
        repo = FixtureRepository(db_manager)
        return repo.get_competition_summary(league_id, season)
    
    @staticmethod
    @st.cache_data(ttl=600)
    def get_upcoming_fixtures_cached(league_id: int, season: int, days: int = 3):
        """Controla la llamada a la API con caché para evitar latencia de red repetitiva."""
        api_service = APIFootballService()
        try:
            return api_service.get_upcoming_fixtures(league_id, season, days=days)
        except Exception:
            return []
        
    @staticmethod
    def get_teams_top_foulers(db_manager, team_ids, season):
        """Orquesta la obtención masiva del top de faltas por equipo."""
        repo = FixtureRepository(db_manager)
        return repo.get_top_foulers_for_teams(team_ids, season)