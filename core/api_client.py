"""
core/api_client.py
Cliente HTTP optimizado para API-Football (API-Sports v3).
Incluye:
  - Cache manual seguro con fallback a tempdir para evitar errores de IO en la nube.
  - Paginación paralela ultrarrápida y manejo estricto de errores de la API.
  - Rate limiting adaptable con lock thread-safe.
  - Fallbacks por equipo si el endpoint global de liga no devuelve registros.
"""

import os
import time
import tempfile
import logging
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import requests_cache
import streamlit as st

from config.constants import BASE_URL

logger = logging.getLogger("FoulsTracker.APIClient")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class APIFootballClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_name: str = "api_football_cache",
        cache_expire_after: int = 86400,  # 24 horas
        rate_limit_delay: float = 0.15     # Ajustado para suscripciones de pago / alto rendimiento
    ):
        # 1. Obtener la clave desde Streamlit Secrets de forma segura
        api_key_from_secrets = None
        try:
            if "API_FOOTBALL_KEY" in st.secrets:
                api_key_from_secrets = st.secrets["API_FOOTBALL_KEY"]
        except Exception:
            pass

        # 2. Asignar prioridad: Argumento > Secrets > Variables de entorno (.env)
        self.api_key = (
            api_key 
            or api_key_from_secrets 
            or os.getenv("API_FOOTBALL_KEY")
        )
        
        if not self.api_key:
            raise ValueError("API Key no proporcionada. Configura API_FOOTBALL_KEY en Secrets o .env")
        
        # Atributo Base URL explícito
        self.base_url = BASE_URL if BASE_URL else "https://v3.football.api-sports.io"

        self.headers = {
            "x-apisports-key": self.api_key,
            "x-rapidapi-host": "v3.football.api-sports.io",
            "Accept": "application/json"
        }
        
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0.0
        self._lock = threading.Lock()

        # Ruta segura para SQLite en entornos cloud (e.g. Streamlit Cloud)
        cache_path = os.path.join(tempfile.gettempdir(), cache_name)

        # Inicialización de la sesión con caché
        self.session = requests_cache.CachedSession(
            cache_name=cache_path,
            backend="sqlite",
            expire_after=cache_expire_after,
            allowable_codes=[200]
        )

    def _wait_for_rate_limit(self):
        """Garantiza la pausa mínima entre peticiones reales a la red de forma thread-safe."""
        with self._lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
            self.last_request_time = time.time()

    def _execute_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ejecuta peticiones GET con validación completa de errores devueltos por API-Football."""
        if params is None:
            params = {}

        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        max_retries = 3

        for attempt in range(max_retries):
            self._wait_for_rate_limit()

            try:
                response = self.session.get(url, headers=self.headers, params=params)
                from_cache = getattr(response, "from_cache", False)

                if response.status_code == 200:
                    data = response.json()
                    errors = data.get("errors")

                    if errors:
                        if isinstance(errors, dict) and errors:
                            logger.error(f"Error devuelto por la API: {errors}")
                            if "requests" in errors:
                                raise PermissionError(f"Límite diario alcanzado: {errors['requests']}")
                        elif isinstance(errors, list) and len(errors) > 0:
                            logger.error(f"Errores en la petición: {errors}")

                    if not data.get("response") and not from_cache:
                        logger.warning(f"Respuesta vacía para {url} con parámetros {params}.")

                    return data

                elif response.status_code == 429:
                    wait_time = (attempt + 1) * 3
                    logger.warning(f"Rate limit 429. Esperando {wait_time}s antes de reintentar...")
                    time.sleep(wait_time)

                elif response.status_code >= 500:
                    logger.warning(f"Error {response.status_code} en API-Football. Reintento {attempt + 1}/{max_retries}")
                    time.sleep(1.5)

                else:
                    response.raise_for_status()

            except Exception as e:
                logger.error(f"Error en intento {attempt + 1} cargando {url}: {e}")
                if attempt == max_retries - 1:
                    raise e

        raise RuntimeError(f"Fallo al consultar {endpoint} tras {max_retries} intentos.")

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Wrapper auxiliar para retornar directamente la lista 'response'."""
        try:
            data = self._execute_request(endpoint, params)
            return data.get("response", [])
        except Exception as e:
            logger.error(f"Error en _make_request ({endpoint}): {e}")
            return []

    def fetch_paginated(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
            """Recorre la paginación de API-Football de forma secuencial y segura."""
            params_copy = params.copy()
            params_copy["page"] = 1

            # 1. Obtener primera página para conocer total_pages
            data_page_1 = self._execute_request(endpoint, params_copy)
            all_results = data_page_1.get("response", [])

            paging_info = data_page_1.get("paging", {})
            total_pages = paging_info.get("total", 1)

            if total_pages <= 1:
                return all_results

            # 2. Descargar páginas restantes secuencialmente (el pipeline externo ya paraleliza por liga)
            logger.info(f"Descargando páginas 2 a {total_pages} para {endpoint}...")

            for page in range(2, total_pages + 1):
                p_params = params.copy()
                p_params["page"] = page
                try:
                    res = self._execute_request(endpoint, p_params)
                    page_data = res.get("response", [])
                    if page_data:
                        all_results.extend(page_data)
                except Exception as e:
                    logger.error(f"Error descargando página {page} de {total_pages} para {endpoint}: {e}")

            return all_results

    def get_player_season_fouls(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Descarga las estadísticas acumuladas de la liga completa vía paginación directa."""
        endpoint = "/players"
        params = {"league": league_id, "season": season}
        logger.info(f"Iniciando descarga de estadísticas para Liga {league_id}, Temporada {season}")
        
        # 1. Intentar la consulta paginada global
        results = self.fetch_paginated(endpoint, params)
        
        if results:
            logger.info(f"Éxito: {len(results)} registros obtenidos para Liga {league_id}, Temporada {season}")
            return results

        # 2. Si falla la liga global, consultar por equipos
        logger.warning(f"Consulta global vacía para Liga {league_id}. Intentando fallback por equipos...")
        return self._get_players_by_teams_fallback(league_id, season)

    def _get_players_by_teams_fallback(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Fallback seguro: Obtiene los equipos de la liga y consulta /players?team=ID."""
        teams_response = self._make_request("/teams", params={"league": league_id, "season": season})
        if not teams_response:
            return []

        all_players = []
        for item in teams_response:
            team_id = item.get("team", {}).get("id")
            if not team_id:
                continue
            
            team_players = self.fetch_paginated("/players", {"team": team_id, "season": season})
            if team_players:
                all_players.extend(team_players)

        return all_players

    def get_players_by_league_teams(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Fallback: Obtiene los equipos de la liga y descarga las plantillas una a una."""
        teams_response = self._make_request("/teams", {"league": league_id, "season": season})

        if not teams_response:
            logger.warning("No se encontraron equipos registrados para esta liga/temporada.")
            return []

        all_players = []
        for team_item in teams_response:
            team_id = team_item.get("team", {}).get("id")
            team_name = team_item.get("team", {}).get("name")
            logger.info(f"Extrayendo jugadores del equipo: {team_name} (ID: {team_id})...")
            
            player_params = {"team": team_id, "season": season}
            team_players = self.fetch_paginated("/players", player_params)
            all_players.extend(team_players)

        return all_players

    def get_fixture_player_fouls(self, fixture_id: int) -> List[Dict[str, Any]]:
        return self._make_request("/fixtures/players", {"fixture": fixture_id})

    def get_fixtures_by_league_season(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        return self._make_request("/fixtures", {"league": league_id, "season": season})
    
    def get_next_fixtures(self, league_id: int, next_n: int = 10) -> List[Dict[str, Any]]:
        """Obtiene los próximos N partidos de una liga determinada."""
        return self._make_request("/fixtures", {"league": league_id, "next": next_n})
        
    def get_fixture_details(self, fixture_id: int) -> Dict[str, Any]:
        """Obtiene el detalle completo de un partido, incluyendo el árbitro designado."""
        response = self._make_request("/fixtures", {"id": fixture_id})
        return response[0] if response else {}

    def get_completed_fixtures(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Obtiene los partidos finalizados de una liga y temporada (status=FT)."""
        return self._make_request("/fixtures", {"league": league_id, "season": season, "status": "FT"})

    def get_fixture_player_stats(self, fixture_id: int) -> Dict[str, Dict[str, int]]:
        """
        Obtiene las faltas y minutos jugados por cada jugador en un partido.
        Retorna un diccionario estructurado: { 'Nombre Jugador': {'fouls': X, 'minutes': Y} }
        """
        response_data = self._make_request("/fixtures/players", {"fixture": fixture_id})
        player_stats_map = {}

        for team_data in response_data:
            for p in team_data.get("players", []):
                p_name = p.get("player", {}).get("name")
                stats = p.get("statistics", [{}])[0]
                
                minutes = stats.get("games", {}).get("minutes", 0) or 0
                fouls = stats.get("fouls", {}).get("committed", 0) or 0
                
                if p_name:
                    player_stats_map[p_name] = {
                        "fouls": fouls,
                        "minutes": minutes
                    }

        return player_stats_map

    def get_referee_stats(self, referee_name: str, season: Optional[int] = None) -> Dict[str, Any]:
        """
        Calcula las estadísticas acumuladas de un árbitro consultando la base de datos Turso.
        """
        if not referee_name or referee_name.strip() == "":
            return {
                "referee": None,
                "matches": 0,
                "avg_fouls": 0.0,
                "avg_yellows": 0.0,
                "raw_name": referee_name
            }

        clean_referee = referee_name.split(",")[0].strip()
        name_parts = clean_referee.replace(".", "").split()
        last_name = name_parts[-1] if name_parts else clean_referee

        from database.data_loader import get_db_client

        client = get_db_client()
        if not client:
            return {
                "referee": clean_referee, 
                "matches": 0, 
                "avg_fouls": 0.0, 
                "avg_yellows": 0.0, 
                "raw_name": referee_name
            }

        try:
            query = """
                SELECT 
                    COUNT(*) as matches,
                    COALESCE(AVG(total_fouls), 0.0) as avg_fouls,
                    COALESCE(AVG(total_yellow_cards), 0.0) as avg_yellows
                FROM match_fixtures
                WHERE (referee_name = ? OR referee_name LIKE ?)
            """
            params = [clean_referee, f"%{last_name}%"]

            if season:
                query += " AND season = ?"
                params.append(season)

            res = client.execute(query, tuple(params))
            rows = res.rows if hasattr(res, 'rows') else res.fetchall()

            if not rows or len(rows) == 0:
                return {
                    "referee": clean_referee,
                    "matches": 0,
                    "avg_fouls": 0.0,
                    "avg_yellows": 0.0,
                    "raw_name": referee_name
                }

            row = rows[0]
            matches_count = row[0] or 0

            if matches_count == 0:
                return {
                    "referee": clean_referee,
                    "matches": 0,
                    "avg_fouls": 0.0,
                    "avg_yellows": 0.0,
                    "raw_name": referee_name
                }

            return {
                "referee": clean_referee,
                "matches": int(matches_count),
                "avg_fouls": round(float(row[1] or 0.0), 2),
                "avg_yellows": round(float(row[2] or 0.0), 2),
                "raw_name": referee_name
            }

        except Exception as e:
            logger.error(f"Error consultando estadísticas del árbitro ({referee_name}): {e}")
            return {
                "referee": clean_referee,
                "matches": 0,
                "avg_fouls": 0.0,
                "avg_yellows": 0.0,
                "raw_name": referee_name
            }

    def get_completed_fixtures_delta(self, league_id: int, season: int, days_back: int = 7) -> list:
        """Descarga solo los partidos finalizados de los últimos X días.
        Evita consultar el historial completo de la temporada.
        """
        today = datetime.now().date()
        from_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        endpoint = "/fixtures"
        params = {
            "league": league_id,
            "season": season,
            "status": "FT",
            "from": from_date,
            "to": to_date
        }
        
        logger.info(f"Consultando delta de partidos para Liga {league_id} entre {from_date} y {to_date}")
        return self._make_request(endpoint, params=params)