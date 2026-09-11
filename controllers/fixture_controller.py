# controllers/fixture_controller.py
from datetime import datetime
import time
import logging
from config.constants import COLOMBIA_TZ
from databases.connection import DatabaseManager
from databases.fixture_repository import FixtureRepository
from services.alert_services import AlertService
from services.api_service import APIFootballService

logger = logging.getLogger("FoulsTracker.FixtureController")

try:
    import streamlit as st
    cache_decorator = st.cache_data(ttl=600, show_spinner=False)
except Exception:
    def cache_decorator(func):
        return func

class FixtureController:

    @staticmethod
    def sync_fixtures_and_stats(
        db_manager: DatabaseManager, 
        league_id: int, 
        season: int, 
        sync_all_season: bool = False
    ):
        """
        Orquesta la obtención de partidos finalizados y actualiza estadísticas de forma idempotente.
        
        Optimizaciones:
          - Salta fixtures ya procesados (processed_for_stats = 1) para no llamar a la API de nuevo.
          - Agrupa las escrituras a Turso en batches de BATCH_SIZE fixtures para minimizar roundtrips.
          - Sleep adaptativo: solo duerme cuando se acerque al límite de la API (< 10 req restantes).
          - Recalcula acumulados de players al final del batch, no por fixture individual.
        """
        BATCH_SIZE = 20  # fixtures por lote de escritura a Turso

        api_service = APIFootballService()
        fixture_repo = FixtureRepository(db_manager)
        
        current_time = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        today_str    = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d")
        entity_name  = f"fixtures_league_{league_id}_{season}"
        
        if sync_all_season:
            logger.info(f"Obteniendo todos los partidos finalizados: liga {league_id}, temporada {season}...")
            fixtures = api_service.get_completed_fixtures_by_season(league_id, season)
        else:
            logger.info(f"Obteniendo partidos finalizados de hoy: liga {league_id}, fecha {today_str}...")
            fixtures = api_service.get_completed_fixtures_by_date(league_id, season, today_str)
        
        if not fixtures:
            logger.info(f"No se encontraron partidos finalizados para procesar en liga {league_id}.")
            fixture_repo.update_sync_timestamp(entity_name, current_time)
            return True

        # ── 1. Obtener IDs ya procesados para saltarlos sin llamar a la API ─────────
        already_done_ids: set = fixture_repo.get_already_processed_fixture_ids(league_id, season)
        pending = [f for f in fixtures if f.get("fixture", {}).get("id") not in already_done_ids]
        skipped  = len(fixtures) - len(pending)
        logger.info(
            f"Total fixtures: {len(fixtures)} | Ya procesados (skip): {skipped} | "
            f"Pendientes a sincronizar: {len(pending)}"
        )

        processed_fixtures = 0
        api_requests_made  = 0

        # ── 2. Procesar en batches ────────────────────────────────────────────────
        for batch_start in range(0, len(pending), BATCH_SIZE):
            batch = pending[batch_start : batch_start + BATCH_SIZE]

            # Acumuladores del batch
            fixture_infos:     list = []   # parámetros para save_fixture_info
            all_player_stats:  dict = {}   # fixture_id → list[tuple]

            for fixture in batch:
                fixture_info = fixture.get("fixture", {})
                fixture_id   = fixture_info.get("id")
                teams        = fixture.get("teams", {})
                referee      = fixture_info.get("referee") or "Árbitro no asignado"

                if not fixture_id:
                    continue
                    
                try:
                    player_stats_map = api_service.get_fixture_player_stats(fixture_id)
                    api_requests_made += 1

                    total_fouls        = 0
                    total_yellow_cards = 0
                    player_stats_list  = []
                    
                    if player_stats_map:
                        for p_id, p in player_stats_map.items():
                            if isinstance(p, dict):
                                fouls_val   = int(p.get("fouls_committed") or 0)
                                drawn_val   = int(p.get("fouls_drawn")     or 0)
                                yellow_val  = int(p.get("yellow_cards")    or 0)
                                red_val     = int(p.get("red_cards")       or 0)
                                minutes_val = int(p.get("minutes_played")  or 0)
                                
                                total_fouls        += fouls_val
                                total_yellow_cards += yellow_val

                                player_stats_list.append((
                                    fixture_id,
                                    p_id,
                                    str(p.get("player_name") or f"Jugador {p_id}").strip(),
                                    p.get("team_id"),
                                    minutes_val,
                                    fouls_val,
                                    drawn_val,
                                    yellow_val,
                                    red_val
                                ))

                    raw_date   = fixture_info.get("date", "")
                    match_date = raw_date.split("T")[0] if "T" in raw_date else (raw_date[:10] if raw_date else today_str)
                    status     = fixture_info.get("status", {}).get("short", "FT")

                    fixture_infos.append({
                        "fixture_id":         fixture_id,
                        "league_id":          league_id,
                        "season":             season,
                        "home_team":          teams.get("home", {}).get("name", "Local"),
                        "away_team":          teams.get("away", {}).get("name", "Visitante"),
                        "status":             status,
                        "match_date":         match_date,
                        "total_fouls":        total_fouls,
                        "total_yellow_cards": total_yellow_cards,
                        "referee":            referee,
                    })

                    if player_stats_list:
                        all_player_stats[fixture_id] = player_stats_list
                        processed_fixtures += 1

                    # ── Sleep adaptativo: evita saturar la API ──────────────────
                    # Solo duerme si queda poco margen de requests (rate limit)
                    if api_requests_made % 10 == 0:
                        time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error al llamar la API para fixture ID {fixture_id}: {e}")

            # ── 3. Escritura batch a Turso (1 conexión por lote, no por fixture) ──
            if fixture_infos:
                try:
                    fixture_repo.save_fixture_batch(fixture_infos)
                except Exception as e:
                    logger.error(f"Error guardando batch de fixtures: {e}")

            if all_player_stats:
                try:
                    fixture_repo.save_player_stats_batch(all_player_stats, league_id, season)
                except Exception as e:
                    logger.error(f"Error guardando batch de stats: {e}")

            logger.info(
                f"Lote {batch_start // BATCH_SIZE + 1}: "
                f"{len(fixture_infos)} fixtures guardados, "
                f"{sum(len(v) for v in all_player_stats.values())} registros de jugadores."
            )

        fixture_repo.update_sync_timestamp(entity_name, current_time)
        logger.info(f"Sincronización completada. Procesados: {processed_fixtures} | API calls: {api_requests_made}")
        
        # ── 4. Evaluación de alertas al finalizar ──────────────────────────────────
        try:
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
                AlertService.process_and_notify_fixtures(
                    upcoming_fixtures=upcoming_fixtures,
                    top_foulers_map=top_foulers_map,
                    db_manager=db_manager,
                    league_id=league_id,
                    season=season
                )
        except Exception as e:
            logger.error(f"Error evaluando alertas: {e}")

        # ── 5. Evaluación y liquidación de apuestas pendientes ─────────────────────
        try:
            from controllers.betting_controller import BettingController
            eval_res = BettingController.evaluate_pending_bets(db_manager, league_id, season)
            if eval_res.get("evaluated", 0) > 0:
                logger.info(
                    f"Apuestas liquidadas tras sincronización: {eval_res['evaluated']} "
                    f"(Ganadas: {eval_res['won']}, Perdidas: {eval_res['lost']})"
                )
        except Exception as e:
            logger.error(f"Error evaluando apuestas pendientes tras sincronización: {e}")
        
        return True


    
    @staticmethod
    def get_team_top_fouler(db_manager: DatabaseManager, team_id: int, season: int) -> dict:
        repo = FixtureRepository(db_manager)
        return repo.get_top_fouler_for_team(team_id, season)
    
    @staticmethod
    def get_competition_summary(db_manager: DatabaseManager, league_id: int, season: int):
        repo = FixtureRepository(db_manager)
        return repo.get_competition_summary(league_id, season)
    
    @staticmethod
    @cache_decorator
    def get_upcoming_fixtures_cached(league_id: int, season: int, days: int = 3):
        """Controla la llamada a la API con caché para evitar latencia de red."""
        api_service = APIFootballService()
        try:
            return api_service.get_upcoming_fixtures(league_id, season, days=days)
        except Exception:
            return []
        
    @staticmethod
    def get_teams_top_foulers(db_manager: DatabaseManager, team_ids: list, season: int):
        repo = FixtureRepository(db_manager)
        return repo.get_top_foulers_for_teams(team_ids, season)
    
    @staticmethod
    def get_last_sync(db_manager: DatabaseManager, entity_name: str):
        repo = FixtureRepository(db_manager)
        return repo.get_last_sync(entity_name)
    