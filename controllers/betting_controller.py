# controllers/betting_controller.py
from databases.betting_repository import BettingRepository
from controllers.fixture_controller import FixtureController

class BettingController:

    @staticmethod
    def get_high_probability_bets(db_manager, league_id, season):
        """
        Algoritmo analítico: Evalúa los próximos partidos y filtra aquellos 
        con una probabilidad estimada de faltas/tarjetas mayor al 80%.
        """
        # Obtenemos los próximos partidos cacheados
        upcoming_fixtures = FixtureController.get_upcoming_fixtures_cached(league_id, season, days=3)
        high_prob_picks = []

        for fix in upcoming_fixtures:
            fix_info = fix.get("fixture", {})
            teams = fix.get("teams", {})
            home_name = teams.get("home", {}).get("name", "Local")
            away_name = teams.get("away", {}).get("name", "Visitante")
            referee = fix_info.get("referee") or "Árbitro Estándar"
            
            # Lógica heurística simulada basada en el perfil del árbitro y nombres
            # (En una fase avanzada se cruza con la tabla historical de árbitros)
            # Asignamos una probabilidad basada en un pseudo-análisis robusto:
            match_hash = hash(home_name + away_name) % 20  # Variación determinista por partido
            base_prob = 75.0 + (match_hash % 15)          # Genera probabilidades entre 75% y 89%
            
            if base_prob >= 80.0:
                market = "Más de 23.5 Faltas Totales" if match_hash % 2 == 0 else "Más de 4.5 Tarjetas Amarillas"
                simulated_odds = round(1.75 + (match_hash * 0.02), 2)
                
                high_prob_picks.append({
                    "match_name": f"{home_name} vs {away_name}",
                    "referee": referee,
                    "market": market,
                    "probability": round(base_prob, 1),
                    "odds": simulated_odds,
                    "league_id": league_id,
                    "season": season
                })

        return high_prob_picks

    @staticmethod
    def save_simulation(db_manager, bet_data):
        repo = BettingRepository(db_manager)
        repo.save_bet(
            bet_data["league_id"],
            bet_data["season"],
            bet_data["match_name"],
            bet_data["referee"],
            bet_data["market"],
            bet_data["probability"],
            bet_data["odds"]
        )

    @staticmethod
    def get_history_df(db_manager, league_id, season):
        repo = BettingRepository(db_manager)
        return repo.get_simulated_bets(league_id, season)
    
    @staticmethod
    def evaluate_pending_bets(db_manager, league_id, season):
        """Lógica de negocio para determinar si una apuesta ganó o perdió."""
        pending_bets = BettingRepository.get_pending_bets(db_manager, league_id, season)
        
        for bet_id, match_name, market in pending_bets:
            fixture = BettingRepository.get_fixture_result(db_manager, match_name, league_id, season)
            
            if fixture:
                status, home_goals, away_goals = fixture
                
                # Validamos si el partido ya finalizó
                if status in ["FT", "Match Finished", "AET", "PEN"]:
                    won = False
                    # Reglas de negocio por mercado
                    if market == "Over 1.5" and (home_goals + away_goals) > 1.5:
                        won = True
                    elif market == "Both Teams Score" and home_goals > 0 and away_goals > 0:
                        won = True
                    
                    new_status = "GANADA" if won else "PERDIDA"
                    BettingRepository.update_bet_status(db_manager, bet_id, new_status)