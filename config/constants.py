import os
from dotenv import load_dotenv

load_dotenv()  # Carga las variables desde el archivo .env

BASE_URL = "https://v3.football.api-sports.io"
API_KEY = os.getenv("API_FOOTBALL_KEY")

# Headers requeridos por API-Football (API-Sports)
HTTP_HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

# 10 Ligas objetivo (ID oficial de API-Football)
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
    103: {"name": "Eliteserien", "country": "Norway"}
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