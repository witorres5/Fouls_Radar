"""
core/api_client.py
Cliente HTTP optimizado para API-Football (API-Sports v3).
Incluye:
  - Cache manual seguro para evitar re-peticiones y almacenamiento de respuestas vacías.
  - Paginación transparente y manejo estricto de errores de la API.
  - Fallbacks por equipo si el endpoint global de liga no devuelve registros.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import requests
import requests_cache
import streamlit as st

from config.constants import BASE_URL, API_KEY

logger = logging.getLogger("FoulsTracker.APIClient")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class APIFootballClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_name: str = "api_football_cache",
        cache_expire_after: int = 86400,  # 24 horas
        rate_limit_delay: float = 1.5
    ):
        
        # 1. Priorizar el argumento directo
        # 2. Buscar en Streamlit Secrets
        # 3. Buscar en variables de entorno (.env)
        self.api_key = (
            api_key 
            or st.secrets.get("API_FOOTBALL_KEY") 
            or os.getenv("API_FOOTBALL_KEY")
        )
        
        if not self.api_key:
            raise ValueError("API Key no proporcionada. Configura API_FOOTBALL_KEY en Secrets o .env")
        self.api_key = api_key or API_KEY
        if not self.api_key:
            raise ValueError("API Key no proporcionada. Configura API_FOOTBALL_KEY en .env o constants.py")

        self.headers = {
            "x-apisports-key": self.api_key,
            "Accept": "application/json"
        }
        
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0.0

        # Inicialización de la sesión con caché
        self.session = requests_cache.CachedSession(
            cache_name=cache_name,
            backend="sqlite",
            expire_after=cache_expire_after,
            allowable_codes=[200]
        )

    def _wait_for_rate_limit(self):
        """Garantiza la pausa entre peticiones reales a la red."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _execute_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta peticiones GET con validación completa de errores devueltos por API-Football."""
        url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
        max_retries = 3

        for attempt in range(max_retries):
            self._wait_for_rate_limit()

            response = self.session.get(url, headers=self.headers, params=params)
            from_cache = getattr(response, "from_cache", False)

            if response.status_code == 200:
                data = response.json()
                errors = data.get("errors")

                # Captura de cualquier estructura de error enviada por API-Football
                if errors:
                    if isinstance(errors, dict) and errors:
                        logger.error(f"Error devuelto por la API: {errors}")
                        if "requests" in errors:
                            raise PermissionError(f"Límite diario alcanzado: {errors['requests']}")
                    elif isinstance(errors, list) and len(errors) > 0:
                        logger.error(f"Errores en la petición: {errors}")

                # Si la respuesta es vacía y no vino de caché, evitamos que persista
                if not data.get("response") and not from_cache:
                    logger.warning(f"Respuesta vacía para {url} con parámetros {params}.")

                return data

            elif response.status_code == 429:
                wait_time = (attempt + 1) * 5
                logger.warning(f"Rate limit 429. Esperando {wait_time}s antes de reintentar...")
                time.sleep(wait_time)

            elif response.status_code >= 500:
                logger.warning(f"Error {response.status_code} en API-Football. Reintento {attempt + 1}/{max_retries}")
                time.sleep(2.0)

            else:
                response.raise_for_status()

        raise RuntimeError(f"Fallo al consultar {endpoint} tras {max_retries} intentos.")

    def fetch_paginated(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Recorre la paginación de API-Football e integra todos los resultados."""
        all_results = []
        current_page = 1
        total_pages = 1

        params_copy = params.copy()

        while current_page <= total_pages:
            params_copy["page"] = current_page
            logger.info(f"Obteniendo página {current_page}/{total_pages} para {endpoint}...")

            data = self._execute_request(endpoint, params_copy)
            results_page = data.get("response", [])

            if not results_page:
                logger.warning(f"La página {current_page} no retornó datos. Deteniendo paginación.")
                break

            all_results.extend(results_page)

            paging_info = data.get("paging", {})
            total_pages = paging_info.get("total", 1)
            current_page += 1

        return all_results

    def get_player_season_fouls(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Intenta descargar las estadísticas acumuladas de la liga completa."""
        endpoint = "/players"
        params = {
            "league": league_id,
            "season": season
        }
        logger.info(f"Iniciando descarga de estadísticas para Liga {league_id}, Temporada {season}")
        results = self.fetch_paginated(endpoint, params)
        
        # Si la liga completa no trae resultados (p. ej. Brasil 2025/2026), hacemos fallback por equipos
        if not results:
            logger.info("Consulta global por liga sin datos. Intentando extracción por equipos de la liga...")
            results = self.get_players_by_league_teams(league_id, season)

        return results

    def get_players_by_league_teams(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Fallback: Obtiene los equipos de la liga y descarga las plantillas una a una."""
        teams_endpoint = "/teams"
        teams_data = self._execute_request(teams_endpoint, {"league": league_id, "season": season})
        teams_response = teams_data.get("response", [])

        if not teams_response:
            logger.warning("No se encontraron equipos registrados para esta liga/temporada.")
            return []

        all_players = []
        for team_item in teams_response:
            team_id = team_item["team"]["id"]
            team_name = team_item["team"]["name"]
            logger.info(f"Extrayendo jugadores del equipo: {team_name} (ID: {team_id})...")
            
            player_params = {
                "team": team_id,
                "season": season
            }
            team_players = self.fetch_paginated("/players", player_params)
            all_players.extend(team_players)

        return all_players

    def get_fixture_player_fouls(self, fixture_id: int) -> List[Dict[str, Any]]:
        endpoint = "/fixtures/players"
        params = {"fixture": fixture_id}
        data = self._execute_request(endpoint, params)
        return data.get("response", [])

    def get_fixtures_by_league_season(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        endpoint = "/fixtures"
        params = {"league": league_id, "season": season}
        data = self._execute_request(endpoint, params)
        return data.get("response", [])
    
    def get_next_fixtures(self, league_id: int, next_n: int = 10) -> list:
        """Obtiene los próximos N partidos de una liga determinada desde la API."""
        # Detecta si la clase usa BASE_URL (mayúsculas) o base_url
        base_url = getattr(self, "BASE_URL", getattr(self, "base_url", "https://v3.football.api-sports.io"))
        url = f"{base_url}/fixtures"
        params = {
            "league": league_id,
            "next": next_n
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                return response.json().get("response", [])
            logger.error(f"Error al obtener partidos: {response.status_code} - {response.text}")
            return []
        except Exception as e:
            logger.error(f"Excepción consultando fixtures: {e}")
            return []