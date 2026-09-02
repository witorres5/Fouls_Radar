import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()  # Carga las variables desde el archivo .env

COLOMBIA_TZ = pytz.timezone("America/Bogota")

# Ligas que se juegan en año calendario (Enero - Diciembre):
# 71: Serie A Brazil, 73: Copa Do Brasil, 239: Liga BetPlay (Colombia), 
# 103: Eliteserien (Noruega), 13: Copa Libertadores, 11: Copa Sudamericana
CALENDAR_YEAR_LEAGUES = {71, 73, 239, 103, 13, 11}

def get_current_season_for_league(league_id: int) -> int:
    """Calcula dinámicamente la temporada actual según el calendario de la competición."""
    now = datetime.now(COLOMBIA_TZ)
    if league_id in CALENDAR_YEAR_LEAGUES:
        return now.year
    # Ligas europeas (Agosto a Mayo)
    return now.year if now.month >= 7 else now.year - 1

now_col = datetime.now(COLOMBIA_TZ)
CURRENT_SEASON = now_col.year if now_col.month >= 7 else now_col.year - 1

BASE_URL = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
API_KEY = os.getenv("API_FOOTBALL_KEY", "")

# Headers requeridos por API-Football (API-Sports)
HTTP_HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

# Ligas objetivo (ID oficial de API-Football)
TARGET_LEAGUES = {
    39: {"name": "Premier League", "country": "England"},
    140: {"name": "La Liga", "country": "Spain"},
    135: {"name": "Serie A", "country": "Italy"},
    78: {"name": "Bundesliga", "country": "Germany"},
    61: {"name": "Ligue 1", "country": "France"},
    88: {"name": "Eredivisie", "country": "Netherlands"},
    73: {"name": "Copa Do Brasil", "country": "Brazil"},
    71: {"name": "Serie A Brazil", "country": "Brazil"},
    239: {"name": "Liga BetPlay", "country": "Colombia"},
    2: {"name": "UEFA Champions League", "country": "World"},
    103: {"name": "Eliteserien", "country": "Norway"},
    13: {"name": "Copa Libertadores", "country": "World"},
    11: {"name": "Copa Sudamericana", "country": "World"}
}

# Endpoints relevantes para la métrica de faltas
ENDPOINTS = {
    "PLAYER_STATS": f"{BASE_URL}/players",
    "FIXTURE_PLAYERS": f"{BASE_URL}/fixtures/players",
    "SQUADS": f"{BASE_URL}/players/squads"
}

# Mapeo de campos dentro de response[i].statistics[j]
FOUL_METRICS_PATH = {
    "committed": ("fouls", "committed"),
    "drawn": ("fouls", "drawn"),
    "yellow_cards": ("cards", "yellow"),
    "red_cards": ("cards", "red"),
    "minutes_played": ("games", "minutes")
}
