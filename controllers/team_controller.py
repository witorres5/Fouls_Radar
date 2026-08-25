# controllers/team_controller.py
from datetime import datetime
from config.constants import COLOMBIA_TZ
from databases.connection import DatabaseManager
from databases.team_repository import TeamRepository
from services.api_service import APIFootballService

class TeamController:

    @staticmethod
    def get_team_view_data(db_manager: DatabaseManager, league_id: int, season: int):
        """Obtiene la metadata de sincronización y la lista de equipos desde el repositorio."""
        team_repo = TeamRepository(db_manager)
        entity_name = f"teams_league_{league_id}_{season}"
        
        last_updated = team_repo.get_last_sync(entity_name)
        teams = team_repo.get_teams_by_league(league_id, season)
        
        return teams, last_updated

    @staticmethod
    def sync_teams_data(db_manager: DatabaseManager, league_id: int, season: int):
        """Orquesta la descarga de equipos desde la API y su guardado masivo en la base de datos."""
        api_service = APIFootballService()
        team_repo = TeamRepository(db_manager)
        
        current_time = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Obtener equipos desde la API externa
        raw_teams = api_service.get_teams_by_league(league_id, season)
        team_records = []
        
        for entry in raw_teams:
            t = entry.get("team", {})
            team_id = t.get("id")
            if not team_id:
                continue
                
            team_records.append({
                "team_id": team_id,
                "league_id": league_id,
                "season": season,
                "name": t.get("name"),
                "code": t.get("code"),
                "country": t.get("country"),
                "founded": t.get("founded"),
                "logo": t.get("logo"),
                "updated_at": current_time
            })
            
        # 2. Guardar en la base de datos usando el repositorio
        if team_records:
            team_repo.save_teams(team_records)
            
        # 3. Actualizar la metadata de sincronización
        entity_name = f"teams_league_{league_id}_{season}"
        team_repo.update_sync_timestamp(entity_name, current_time)
        
        return True