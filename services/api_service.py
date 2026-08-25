# services/api_service.py
import os
import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger("FoulsTracker.ApiService")

class APIFootballService:
    def __init__(self):
        self.api_key = os.getenv("API_FOOTBALL_KEY", "")
        self.base_url = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
        
        if not self.api_key:
            logger.warning("No se encontró la API Key de API-Football (API_FOOTBALL_KEY). Las consultas fallarán si no se configura.")

        self.headers = {
            "x-apisports-key": self.api_key
        }

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Método genérico para realizar peticiones GET a la API con manejo básico de errores."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Verificar si la API devolvió errores en su estructura interna
            errors = data.get("errors")
            if errors:
                logger.error(f"Error devuelto por API-Football en {endpoint}: {errors}")
            
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de red o conexión al consultar {url}: {e}")
            return {}

    def get_teams_by_league(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Obtiene la lista de equipos participantes en una liga para una temporada dada."""
        data = self._get("teams", {"league": league_id, "season": season})
        return data.get("response", [])


    def get_completed_fixtures(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Obtiene todos los partidos finalizados ('FT') de una liga y temporada."""
        data = self._get("fixtures", {"league": league_id, "season": season, "status": "FT"})
        return data.get("response", [])

    def get_fixture_details(self, fixture_id: int) -> Dict[str, Any]:
        """Obtiene los detalles completos (eventos, tarjetas, etc.) de un partido por su ID."""
        data = self._get("fixtures/events", {"fixture": fixture_id})
        response_list = data.get("response", [])
        return response_list[0] if response_list else {}

    def get_fixture_player_stats(self, fixture_id: int) -> Dict[int, Dict[str, Any]]:
        """Obtiene las estadísticas detalladas por jugador para un partido específico (faltas, minutos, etc.)."""
        data = self._get("fixtures/players", {"fixture": fixture_id})
        result = {}
        for team_data in data.get("response", []):
            for player_entry in team_data.get("players", []):
                player_id = player_entry.get("player", {}).get("id")
                stats_list = player_entry.get("statistics", [])
                if player_id and stats_list:
                    # Tomamos el primer bloque de estadísticas del jugador en ese partido
                    stats = stats_list[0]
                    fouls = stats.get("fouls", {}) or {}
                    cards = stats.get("cards", {}) or {}
                    games = stats.get("games", {}) or {}
                    
                    result[player_id] = {
                        "minutes_played": games.get("minutes", 0) or 0,
                        "fouls_committed": fouls.get("committed", 0) or 0,
                        "fouls_drawn": fouls.get("drawn", 0) or 0,
                        "yellow_cards": 1 if cards.get("yellow") else 0,
                        "red_cards": 1 if cards.get("red") else 0,
                    }
        return result
    
    def get_upcoming_fixtures(self, league_id: int, season: int, days: int = 3) -> List[Dict[str, Any]]:
            """Obtiene los partidos próximos que aún no han comenzado en los siguientes N días."""
            from datetime import datetime, timedelta
            
            today = datetime.now().strftime("%Y-%m-%d")
            to_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            
            params = {
                "league": league_id,
                "season": season,
                "from": today,
                "to": to_date
            }
            data = self._get("fixtures", params)
            fixtures = data.get("response", [])
            
            # Filtramos para mostrar únicamente los partidos que aún NO han comenzado (ej. 'NS' o 'TBD')
            upcoming_fixtures = []
            for fixture in fixtures:
                status = fixture.get("fixture", {}).get("status", {}).get("short")
                # 'NS' = Not Started, 'TBD' = Time To Be Defined
                if status in ["NS", "TBD"]:
                    upcoming_fixtures.append(fixture)
                       
            return upcoming_fixtures
    
    def get_completed_fixtures_by_date(self, league_id: int, season: int, date_str: str) -> list:
        """Obtiene los partidos finalizados de una liga específica para una fecha exacta (YYYY-MM-DD)."""
        endpoint = "fixtures"
        params = {
            "league": league_id,
            "season": season,
            "date": date_str,
            "status": "FT"  # Filtrar solo partidos finalizados (Finished)
        }
        
        try:
            response = self._get(endpoint, params=params)
            if response and "response" in response:
                return response["response"]
        except Exception as e:
            print(f">>> ERROR obteniendo fixtures por fecha para la liga {league_id}: {e}")
            
        return []
    
    def get_completed_fixtures_by_season(self, league_id: int, season: int) -> list:
        """Obtiene los partidos finalizados de una liga específica para una fecha exacta (YYYY-MM-DD)."""
        endpoint = "fixtures"
        params = {
            "league": league_id,
            "season": season,
            "status": "FT"  # Filtrar solo partidos finalizados (Finished)
        }
    
        try:
            response = self._get(endpoint, params=params)
            if response and "response" in response:
                return response["response"]
        except Exception as e:
            print(f">>> ERROR obteniendo fixtures por fecha para la liga {league_id}: {e}")
            
        return []
    
    # En tu clase APIFootballService (ej: services/api_football_service.py)

    def get_players_by_team(self, team_id: int, season: int) -> list:
        """
        Obtiene la lista/plantilla de jugadores de un equipo para una temporada dada.
        Endpoint API-Football: /players/squads o /players
        """
        url = f"{self.base_url}/players/squads"  # O el endpoint que utilices (ej: /players?team={team_id}&season={season})
        params = {
            "team": team_id
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                response_list = data.get("response", [])
                if response_list and isinstance(response_list, list):
                    # /players/squads retorna la plantilla del equipo en 'players'
                    players = response_list[0].get("players", [])
                    return players
                return []
            else:
                print(f">>> ERROR API [{response.status_code}]: No se pudo obtener plantilla para el equipo {team_id}")
                return []
        except Exception as e:
            print(f">>> EXCEPCIÓN en get_players_by_team para team_id {team_id}: {e}")
            return []