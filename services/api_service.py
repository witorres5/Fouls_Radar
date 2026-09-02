# services/api_service.py
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from config.constants import COLOMBIA_TZ

logger = logging.getLogger("FoulsTracker.ApiService")

try:
    import streamlit as st
except ImportError:
    st = None

class APIFootballService:
    def __init__(self):
        self.api_key = os.getenv("API_FOOTBALL_KEY", "")
        if not self.api_key and st and hasattr(st, "secrets") and "API_FOOTBALL_KEY" in st.secrets:
            self.api_key = st.secrets["API_FOOTBALL_KEY"]

        self.base_url = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
        
        if not self.api_key:
            logger.warning("No se encontró la API Key de API-Football (API_FOOTBALL_KEY). Las consultas remotas fallarán.")

        self.headers = {
            "x-apisports-key": self.api_key,
            "Accept": "application/json"
        }

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Método genérico para realizar peticiones GET a la API con manejo estructurado de errores."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=25)
            response.raise_for_status()
            data = response.json()
            
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
        """Obtiene los detalles completos de un partido por su ID."""
        data = self._get("fixtures/events", {"fixture": fixture_id})
        response_list = data.get("response", [])
        return response_list[0] if response_list else {}

    def get_fixture_player_stats(self, fixture_id: int) -> dict:
        """Consulta la API de API-Football para /fixtures/players y retorna el mapa de estadísticas."""
        response = self._get("fixtures/players", {"fixture": fixture_id})
        player_stats_map = {}
        if not response or "response" not in response:
            return player_stats_map

        for team_data in response.get("response", []):
            team_info = team_data.get("team", {})
            team_id = team_info.get("id")
            
            for player_entry in team_data.get("players", []):
                player_info = player_entry.get("player", {})
                player_id = player_info.get("id")
                player_name = player_info.get("name")
                
                stats_list = player_entry.get("statistics", [])
                if not stats_list or not player_id:
                    continue
                    
                stats = stats_list[0]
                games = stats.get("games", {}) or {}
                fouls = stats.get("fouls", {}) or {}
                cards = stats.get("cards", {}) or {}
                
                player_stats_map[player_id] = {
                    "player_id": player_id,
                    "player_name": player_name,
                    "team_id": team_id,
                    "minutes_played": games.get("minutes") or 0,
                    "fouls_committed": fouls.get("committed") or 0,
                    "fouls_drawn": fouls.get("drawn") or 0,
                    "yellow_cards": cards.get("yellow") or 0,
                    "red_cards": cards.get("red") or 0
                }

        return player_stats_map

    def get_upcoming_fixtures(self, league_id: int, season: int, days: int = 3) -> List[Dict[str, Any]]:
        """Obtiene los partidos próximos con filtro de zona horaria Colombia."""
        now = datetime.now(COLOMBIA_TZ)
        today = now.strftime("%Y-%m-%d")
        to_date = (now + timedelta(days=days)).strftime("%Y-%m-%d")
        
        params = {
            "league": league_id,
            "season": season,
            "from": today,
            "to": to_date
        }
        data = self._get("fixtures", params)
        fixtures = data.get("response", [])
        
        upcoming_fixtures = []
        for fixture in fixtures:
            status = fixture.get("fixture", {}).get("status", {}).get("short")
            if status in ["NS", "TBD"]:
                upcoming_fixtures.append(fixture)
                   
        return upcoming_fixtures

    def get_completed_fixtures_by_date(self, league_id: int, season: int, date_str: str) -> list:
        """Obtiene los partidos finalizados de una liga específica para una fecha exacta (YYYY-MM-DD)."""
        params = {
            "league": league_id,
            "season": season,
            "date": date_str,
            "status": "FT"
        }
        data = self._get("fixtures", params=params)
        return data.get("response", [])

    def get_completed_fixtures_by_season(self, league_id: int, season: int) -> list:
        """Obtiene todos los partidos finalizados de una liga para toda la temporada."""
        return self.get_completed_fixtures(league_id, season)

    def get_players_by_team(self, team_id: int, season: int) -> list:
        """Obtiene la plantilla de jugadores de un equipo."""
        data = self._get("players/squads", {"team": team_id})
        response_list = data.get("response", [])
        if response_list and isinstance(response_list, list):
            return response_list[0].get("players", [])
        return []