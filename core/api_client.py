"""
core/api_client.py
Cliente HTTP optimizado para API-Football (API-Sports v3).
Incluye:
  - Cache manual seguro con fallback a tempdir para evitar errores de IO en la nube.
  - Paginación transparente y manejo estricto de errores de la API.
  - Fallbacks por equipo si el endpoint global de liga no devuelve registros.
"""

import os
import time
import tempfile
import logging
from typing import Dict, Any, List, Optional
import requests
import requests_cache
import streamlit as st

from config.constants import BASE_URL
from typing import Dict, Any

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
        
        self.headers = {
            "x-apisports-key": self.api_key,
            "Accept": "application/json"
        }
        
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0.0

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
    
    def get_next_fixtures(self, league_id: int, next_n: int = 10) -> List[Dict[str, Any]]:
        """Obtiene los próximos N partidos de una liga determinada pasando por la gestión unificada de peticiones."""
        endpoint = "/fixtures"
        params = {
            "league": league_id,
            "next": next_n
        }
        try:
            data = self._execute_request(endpoint, params)
            return data.get("response", [])
        except Exception as e:
            logger.error(f"Excepción consultando próximos partidos: {e}")
            return []
        
    def get_fixture_details(self, fixture_id: int) -> Dict[str, Any]:
        """Obtiene el detalle completo de un partido, incluyendo el árbitro designado."""
        endpoint = "/fixtures"
        params = {"id": fixture_id}
        data = self._execute_request(endpoint, params)
        response = data.get("response", [])
        return response[0] if response else {}


    def get_referee_stats(self, referee_name: str, season: int = None) -> Dict[str, Any]:
        """
        Calcula las estadísticas acumuladas de un árbitro consultando los partidos
        guardados en la base de datos local (Turso/SQLite).
        """
        if not referee_name or referee_name.strip() == "":
            return {
                "referee": None,
                "matches": 0,
                "avg_fouls": 0.0,
                "avg_yellows": 0.0,
                "raw_name": referee_name
            }

        # 1. Normalización del nombre para la búsqueda
        # "J. Vitor Gobi" -> extrae "Vitor Gobi" o el último apellido "Gobi"
        clean_referee = referee_name.split(",")[0].strip()
        name_parts = clean_referee.replace(".", "").split()
        last_name = name_parts[-1] if name_parts else clean_referee

        conn = self._get_connection()
        cursor = conn.cursor()

        # 2. Consulta SQL: Busca por coincidencia exacta o parcial por apellido
        # Filtra opcionalmente por temporada si se especifica
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

        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        conn.close()

        # 3. Mapeo del resultado
        matches_count = row["matches"] if row else 0

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
            "matches": matches_count,
            "avg_fouls": round(float(row["avg_fouls"]), 2),
            "avg_yellows": round(float(row["avg_yellows"]), 2),
            "raw_name": referee_name
        }
        
    def get_completed_fixtures(self, league_id: int, season: int) -> list:
        """
        Obtiene los partidos finalizados de una liga y temporada específica.
        Endpoint: /fixtures?league={league_id}&season={season}&status=FT
        """
        endpoint = "/fixtures"
        params = {
            "league": league_id,
            "season": season,
            "status": "FT"  # FT = Finished (Partidos terminados)
        }
        
        # Utiliza tu método interno existente para realizar la petición (ej. _make_request, _get, etc.)
        response = self._make_request(endpoint, params=params)
        
        if response and "response" in response:
            return response["response"]
        
        return []