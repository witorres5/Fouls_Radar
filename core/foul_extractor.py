from typing import List, Dict, Any, Union
from models.foul_stats import PlayerFoulStats

def parse_player_fouls(raw_response: Union[List[Dict[str, Any]], Dict[str, Any]], league_id: int, season: int) -> List[PlayerFoulStats]:
    """Parsea los datos de API-Football devolviendo solo registros disciplinarios."""
    parsed_stats = []
    
    # Manejar si recibe la lista procesada por fetch_paginated o el JSON directo
    if isinstance(raw_response, dict):
        items = raw_response.get("response", [])
    else:
        items = raw_response  # Ya es la lista de jugadores

    for item in items:
        player_info = item.get("player", {})
        statistics = item.get("statistics", [])
        
        for stat in statistics:
            fouls = stat.get("fouls", {})
            cards = stat.get("cards", {})
            games = stat.get("games", {})
            team = stat.get("team", {})
            
            committed = fouls.get("committed") or 0
            drawn = fouls.get("drawn") or 0
            minutes = games.get("minutes") or 0
            
            foul_record = PlayerFoulStats(
                player_id=player_info.get("id"),
                player_name=player_info.get("name"),
                team_id=team.get("id"),
                team_name=team.get("name"),
                league_id=league_id,
                season=season,
                minutes_played=minutes,
                fouls_committed=committed,
                fouls_drawn=drawn,
                yellow_cards=cards.get("yellow") or 0,
                red_cards=cards.get("red") or 0
            )
            parsed_stats.append(foul_record)
            
    return parsed_stats
    """Parsea el objeto JSON de API-Football devolviendo solo registros disciplinarios."""
    parsed_stats = []
    
    for item in raw_response.get("response", []):
        player_info = item.get("player", {})
        statistics = item.get("statistics", [])
        
        for stat in statistics:
            fouls = stat.get("fouls", {})
            cards = stat.get("cards", {})
            games = stat.get("games", {})
            team = stat.get("team", {})
            
            # Solo procesar registros con minutos jugados o faltas registradas
            committed = fouls.get("committed") or 0
            drawn = fouls.get("drawn") or 0
            minutes = games.get("minutes") or 0
            
            foul_record = PlayerFoulStats(
                player_id=player_info.get("id"),
                player_name=player_info.get("name"),
                team_id=team.get("id"),
                team_name=team.get("name"),
                league_id=league_id,
                season=season,
                minutes_played=minutes,
                fouls_committed=committed,
                fouls_drawn=drawn,
                yellow_cards=cards.get("yellow") or 0,
                red_cards=cards.get("red") or 0
            )
            parsed_stats.append(foul_record)
            
    return parsed_stats