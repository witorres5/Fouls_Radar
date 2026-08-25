# controllers/fixture_controller.py
from datetime import datetime
import time
from config.constants import COLOMBIA_TZ
from databases.connection import DatabaseManager
from databases.fixture_repository import FixtureRepository
from services.alert_services import AlertService
from services.api_service import APIFootballService
import streamlit as st
import inspect


class FixtureController:

    @staticmethod
    def sync_fixtures_and_stats(db_manager: DatabaseManager, league_id: int, season: int):
        """Orquesta la obtención de partidos finalizados del día, guarda el fixture con sus totales y actualiza las estadísticas de jugadores."""
        api_service = APIFootballService()
        fixture_repo = FixtureRepository(db_manager)
        
        current_time = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        today_str = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d") # Fecha de hoy exacta
        entity_name = f"fixtures_league_{league_id}_{season}"
        
        # Obtener el marco (frame) del llamador (1 nivel arriba en la pila)
        caller_frame = inspect.stack()[1]
        
        nombre_funcion = caller_frame.function  # Nombre de la función
        
        # 1. Obtener partidos finalizados ('FT') exclusivamente del día de hoy
        if(nombre_funcion == "render_fixtures_view"):
            print(f">>> DEBUG: Obteniendo partidos finalizados para la liga {league_id}, temporada {season}...")
            fixtures = api_service.get_completed_fixtures_by_season(league_id, season)
            print(f">>> DEBUG: Total de partidos finalizados ne la temporada {season} encontrados: {len(fixtures)}")
        else:
            print(f">>> DEBUG: Obteniendo partidos finalizados para la liga {league_id}, fecha {today_str}...")
            fixtures = api_service.get_completed_fixtures_by_date(league_id, season, today_str)
            print(f">>> DEBUG: Total de partidos finalizados hoy encontrados: {len(fixtures)}")
        
        if not fixtures:
            print(">>> ADVERTENCIA: No se encontraron partidos finalizados hoy para procesar.")

        processed_fixtures = 0
        
        # 2. Iterar cada partido para extraer estadísticas y registrar el fixture completo
        for fixture in fixtures:
            fixture_info = fixture.get("fixture", {})
            fixture_id = fixture_info.get("id")
            teams = fixture.get("teams", {})
            referee = fixture_info.get("referee")
            
            if not fixture_id:
                continue
                
            try:
                # Obtener estadísticas detalladas (faltas, minutos, tarjetas) de los jugadores
                player_stats_map = api_service.get_fixture_player_stats(fixture_id)
                
                # Calcular acumulados totales de faltas y tarjetas amarillas del partido
                total_fouls = 0
                total_yellow_cards = 0
                
                if player_stats_map:
                    for p in player_stats_map.values():
                        if isinstance(p, dict):
                            # Obtener faltas buscando 'fouls_committed', 'fouls' o el dict anidado
                            fouls_val = p.get("fouls_committed")
                            if fouls_val is None:
                                fouls_val = p.get("fouls", 0)
                            if isinstance(fouls_val, dict):
                                fouls_val = fouls_val.get("committed") or 0
                            
                            total_fouls += int(fouls_val or 0)
                            total_yellow_cards += int(p.get("yellow_cards", 0) or 0)

                # Normalizar la fecha del partido a formato estricto YYYY-MM-DD
                raw_date = fixture_info.get("date", "")
                match_date = raw_date.split("T")[0] if "T" in raw_date else (raw_date[:10] if raw_date else today_str)

                # Registrar o actualizar la información principal del partido en match_fixtures con sus acumulados
                home_name = teams.get("home", {}).get("name")
                away_name = teams.get("away", {}).get("name")
                status = fixture_info.get("status", {}).get("short")

                fixture_repo.save_fixture_info(
                    fixture_id=fixture_id,
                    league_id=league_id,
                    season=season,
                    home_team=home_name,
                    away_team=away_name,
                    status=status,
                    match_date=match_date,
                    total_fouls=total_fouls,
                    total_yellow_cards=total_yellow_cards,
                    referee=referee
                )

                if player_stats_map:
                    # Actualizar estadísticas individuales de forma acumulativa en la base de datos
                    fixture_repo.update_player_match_stats(player_stats_map, league_id, season)
                    processed_fixtures += 1
                    print(f">>> DEBUG: Fixture ID {fixture_id} procesado ({len(player_stats_map)} jugadores | Faltas: {total_fouls}, Tarjetas: {total_yellow_cards}).")
                
                # Pausa corta para cuidar el rate limit de la API
                time.sleep(0.3)
            except Exception as e:
                print(f">>> ERROR procesando el fixture ID {fixture_id}: {e}")

        # 3. Actualizar la marca de tiempo de sincronización
        fixture_repo.update_sync_timestamp(entity_name, current_time)
        print(f">>> DEBUG: Sincronización de fixtures completada. Partidos procesados: {processed_fixtures}")
        
        # 4. EVALUACIÓN Y NOTIFICACIÓN TELEGRAM (Próximos partidos)
        try:
            print(">>> DEBUG: Evaluando probabilidades para enviar alertas a Telegram...")
            upcoming_fixtures = FixtureController.get_upcoming_fixtures_cached(league_id, season, days=3)

            if upcoming_fixtures:
                team_ids = set()
                for fix in upcoming_fixtures:
                    t = fix.get("teams", {})
                    if home_id := t.get("home", {}).get("id"):
                        team_ids.add(home_id)
                    if away_id := t.get("away", {}).get("id"):
                        team_ids.add(away_id)

                top_foulers_map = FixtureController.get_teams_top_foulers(db_manager, list(team_ids), season)
                # Instanciar tu repositorio de apuestas
                
                # Disparar flujo seguro contra duplicados
                AlertService.process_and_notify_fixtures(
                    upcoming_fixtures=upcoming_fixtures,
                    top_foulers_map=top_foulers_map,
                    db_manager=db_manager,
                    league_id=league_id,
                    season=season
                )
                print(">>> DEBUG: Evaluación de alertas Telegram finalizada correctamente.")
        except Exception as e:
            print(f">>> ERROR evaluando/enviando alertas Telegram: {e}")
        
        return True
    
    @staticmethod
    def get_team_top_fouler(db_manager, team_id, season):
        """Lógica para obtener el top jugador con faltas de un equipo."""
        repo = FixtureRepository(db_manager)
        return repo.get_top_fouler_for_team(team_id, season)
    
    @staticmethod
    def get_competition_summary(db_manager, league_id, season):
        """Orquesta la obtención del resumen de comportamiento de la competición."""
        repo = FixtureRepository(db_manager)
        return repo.get_competition_summary(league_id, season)
    
    @staticmethod
    # @st.cache_data(ttl=600)
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