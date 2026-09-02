# controllers/player_controller.py
from datetime import datetime
import time
import logging
from typing import Optional, Dict, Any, Tuple
from config.constants import COLOMBIA_TZ
from databases.connection import DatabaseManager
from databases.player_repository import PlayerRepository
from services.api_service import APIFootballService
from databases.team_repository import TeamRepository

logger = logging.getLogger("FoulsTracker.PlayerController")

class PlayerController:

    @staticmethod
    def get_player_view_data(
        db_manager: DatabaseManager, 
        league_id: int, 
        season: int, 
        selected_team_id: Optional[int] = None
    ) -> Tuple[Dict[str, int], list, str]:
        """Obtiene datos delegando la consulta de equipos al TeamRepository."""
        player_repo = PlayerRepository(db_manager)
        team_repo = TeamRepository(db_manager)
        entity_name = f"players_league_{league_id}_{season}"
        
        last_updated = player_repo.get_last_sync(entity_name)
        
        teams_list = team_repo.get_teams_by_league(league_id, season)
        teams_dict = {t["name"]: t["team_id"] for t in teams_list}
        
        if selected_team_id:
            players = player_repo.get_players_by_team(selected_team_id, season)
        else:
            players = player_repo.get_players_by_league(league_id, season)
            
        return teams_dict, players, last_updated

    @staticmethod
    def sync_players_data(db_manager: DatabaseManager, league_id: int, season: int) -> bool:
        """Orquesta la sincronización de jugadores preservando estadísticas acumuladas."""
        api_service = APIFootballService()
        player_repo = PlayerRepository(db_manager)
        
        current_time = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        
        teams = api_service.get_teams_by_league(league_id, season)
        logger.info(f"Total equipos obtenidos para liga {league_id}: {len(teams)}")
        
        all_player_records = []
        
        for team_entry in teams:
            team_info = team_entry.get("team", {})
            team_id = team_info.get("id")
            team_name = team_info.get("name", "Desconocido")
            if not team_id:
                continue
                
            try:
                players_data = api_service.get_players_by_team(team_id, season)
                if not players_data:
                    continue
                
                for p_entry in players_data:
                    player_id = p_entry.get("id")
                    player_name = p_entry.get("name")
                    
                    if player_id and player_name:
                        all_player_records.append({
                            "player_id": player_id,
                            "team_id": team_id,
                            "player_name": player_name,
                            "league_id": league_id,
                            "season": season,
                            "minutes_played": 0,
                            "fouls_committed": 0,
                            "fouls_drawn": 0,
                            "yellow_cards": 0,
                            "red_cards": 0,
                            "fouls_per_90": 0.0,
                            "updated_at": current_time
                        })
                
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"Error en equipo {team_name}: {e}")

        if all_player_records:
            player_repo.save_players(all_player_records)
            logger.info(f"{len(all_player_records)} jugadores registrados/actualizados en base de datos.")

        entity_name = f"players_league_{league_id}_{season}"
        player_repo.update_sync_timestamp(entity_name, current_time)
            
        return True