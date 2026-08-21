# controllers/player_controller.py
from datetime import datetime
import time
from config.constants import COLOMBIA_TZ
from databases.connection import DatabaseManager
from databases.player_repository import PlayerRepository
from services.api_service import APIFootballService

class PlayerController:

    @staticmethod
    def get_player_view_data(db_manager: DatabaseManager, league_id: int, season: int, selected_team_id: int = None):
        """Obtiene la metadata, los equipos para los filtros y los jugadores a través del repositorio."""
        player_repo = PlayerRepository(db_manager)
        entity_name = f"players_league_{league_id}_{season}"
        
        # 1. Obtener última sincronización desde el repositorio
        last_updated = player_repo.get_last_sync(entity_name)
        
        # 2. Obtener equipos para el selectbox
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT team_id, name FROM teams WHERE league_id = ? ORDER BY name", (league_id,))
            teams_rows = cursor.fetchall()
            
        teams_dict = {row[1]: row[0] for row in teams_rows}
        
        # 3. Obtener jugadores según el filtro
        if selected_team_id:
            players = player_repo.get_players_by_team(selected_team_id)
        else:
            players = player_repo.get_players_by_league(league_id, season)
            
        return teams_dict, players, last_updated

    @staticmethod
    def sync_players_data(db_manager: DatabaseManager, league_id: int, season: int):
        """Orquesta la sincronización de jugadores conectando la API con el repositorio."""
        api_service = APIFootballService()
        player_repo = PlayerRepository(db_manager)
        
        current_time = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Obtener equipos de la liga
        teams = api_service.get_teams_by_league(league_id, season)
        print(f">>> DEBUG: Total equipos obtenidos para la liga {league_id}: {len(teams)}")
        
        all_player_records = []
        
        # 2. Iterar equipos para extraer sus plantillas de forma directa
        for team_entry in teams:
            team_info = team_entry.get("team", {})
            team_id = team_info.get("id")
            team_name = team_info.get("name", "Desconocido")
            if not team_id:
                continue
                
            try:
                # Obtenemos la plantilla completa mediante el endpoint de squads
                players_data = api_service.get_players_by_team(team_id, season)
                if not players_data:
                    print(f">>> AVISO: El equipo {team_name} (ID: {team_id}) no devolvió jugadores.")
                    continue
                
                print(f">>> DEBUG: Equipo {team_name} (ID: {team_id}) -> Jugadores obtenidos: {len(players_data)}")
                
                for p_entry in players_data:
                    player_id = p_entry.get("id")
                    player_name = p_entry.get("name")
                    
                    # Inicializamos las estadísticas base ya que el endpoint de escuadras provee la lista de jugadores
                    minutes = 0
                    committed = 0
                    drawn = 0
                    yellow = 0
                    red = 0
                    fouls_per_90 = 0.0
                    
                    if player_id and player_name:
                        all_player_records.append({
                            "player_id": player_id,
                            "team_id": team_id,
                            "player_name": player_name,
                            "league_id": league_id,
                            "season": season,
                            "minutes_played": minutes,
                            "fouls_committed": committed,
                            "fouls_drawn": drawn,
                            "yellow_cards": yellow,
                            "red_cards": red,
                            "fouls_per_90": fouls_per_90,
                            "updated_at": current_time
                        })
                
                time.sleep(0.3) # Pausa breve para cuidar el límite de peticiones
            except Exception as e:
                print(f">>> ERROR en equipo {team_name}: {e}")

        print(f">>> DEBUG: Total acumulados para guardar en BD: {len(all_player_records)}")

        # 3. Guardar masivamente usando el repositorio
        if all_player_records:
            player_repo.save_players(all_player_records)
            print(">>> DEBUG: Jugadores guardados exitosamente en la base de datos.")
        else:
            print(">>> ADVERTENCIA: No se recolectó ningún jugador de la API para guardar.")

        # 4. Actualizar metadata de sincronización en el repositorio
        entity_name = f"players_league_{league_id}_{season}"
        player_repo.update_sync_timestamp(entity_name, current_time)
            
        return True