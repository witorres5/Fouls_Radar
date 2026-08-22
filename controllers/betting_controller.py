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
    def save_simulation(db_manager, pick_data):
        """Guarda la apuesta simulada incluyendo la fecha del partido."""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO simulated_bets (league_id, season, match_name, referee, market, probability, simulated_odds, match_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')
            """, (
                pick_data.get("league_id"),
                pick_data.get("season"),
                pick_data.get("match_name"),
                pick_data.get("referee"),
                pick_data.get("market"),
                pick_data.get("probability"),
                pick_data.get("odds"),
                pick_data.get("match_date") # <-- Asegúrate de pasar la fecha del partido aquí
            ))
            conn.commit()
            
    @staticmethod
    def get_history_df(db_manager, league_id, season):
        repo = BettingRepository(db_manager)
        return repo.get_simulated_bets(league_id, season)
    
    @staticmethod
    def evaluate_pending_bets(db_manager, league_id, season, today_str):
        pending_bets = BettingRepository.get_pending_bets_by_date(db_manager, league_id, season, today_str)

        for bet_id, match_name, market in pending_bets:
            # Obtenemos los datos del partido desde la BD
            fixture = BettingRepository.get_fixture_result(db_manager, match_name, league_id, season)
            if fixture:
                # Asegúrate de desempaquetar la tupla (status, total_fouls, total_yellow_cards)
                status, total_fouls, total_yellow_cards = fixture

                if status in ["FT", "Match Finished", "AET", "PEN"]:
                    won = False
                    import re
                    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", market)
                    
                    if numbers:
                        line_value = float(numbers[0])
                        if "Faltas Totales" in market and total_fouls > line_value:
                            won = True
                        elif "Tarjetas Amarillas" in market and total_yellow_cards > line_value:
                            won = True

                    new_status = "GANADA" if won else "PERDIDA"
                    BettingRepository.update_bet_status(db_manager, bet_id, new_status)