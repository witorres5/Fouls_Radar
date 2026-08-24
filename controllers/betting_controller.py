# controllers/betting_controller.py
from databases.betting_repository import BettingRepository
from controllers.fixture_controller import FixtureController
import math

class BettingController:

    @staticmethod
    def get_high_probability_bets(db_manager, league_id: int, season: int):
        """
        Algoritmo analítico cuantitativo: Evalúa los próximos partidos ponderando
        el promedio histórico del árbitro asignado frente al promedio de la liga.
        """
        upcoming_fixtures = FixtureController.get_upcoming_fixtures_cached(league_id, season, days=3)
        high_prob_picks = []

        # 1. Obtener medias globales de la liga para la temporada actual (Líneas base)
        league_avg_fouls = 22.5
        league_avg_cards = 4.2
        
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Consulta opcional para dinamizar los promedios de la liga:
            cursor.execute("""
                SELECT 
                    AVG(total_fouls) as avg_fouls, 
                    AVG(total_yellow_cards) as avg_cards 
                FROM match_fixtures 
                WHERE league_id = ? AND season = ? AND status = 'FT'
            """, (league_id, season))
            league_stats = cursor.fetchone()
            
            if league_stats and league_stats[0] is not None:
                league_avg_fouls = league_stats[0] or 22.5
                league_avg_cards = league_stats[1] or 4.2

            # 2. Iterar cada próximo partido
            for fix in upcoming_fixtures:
                fix_info = fix.get("fixture", {})
                teams = fix.get("teams", {})
                home_name = teams.get("home", {}).get("name", "Local")
                away_name = teams.get("away", {}).get("name", "Visitante")
                referee_raw = fix_info.get("referee")
                
                referee = referee_raw.strip() if referee_raw and isinstance(referee_raw, str) else "Árbitro Estándar"
                match_date = (fix_info.get("date") or "")[:10]
                
                # 3. Consultar métricas históricas del árbitro en la BD
                cursor.execute("""
                    SELECT 
                        COUNT(fixture_id) as matches_count,
                        AVG(total_fouls) as avg_fouls,
                        AVG(total_yellow_cards) as avg_cards
                    FROM match_fixtures
                    WHERE referee_name = ? AND total_fouls > 0
                """, (referee,))
                ref_row = cursor.fetchone()

                matches_count = ref_row[0] if ref_row else 0
                ref_avg_fouls = ref_row[1] if (ref_row and ref_row[1] is not None) else league_avg_fouls
                ref_avg_cards = ref_row[2] if (ref_row and ref_row[2] is not None) else league_avg_cards

                # 4. Calcular Factores de Ponderación (Árbitro vs Liga)
                # Si el árbitro tiene menos de 3 partidos registrados, le asignamos menor peso al factor (Shrinkage)
                confidence_weight = min(matches_count / 5.0, 1.0) if matches_count > 0 else 0.0
                
                fouls_ratio = ref_avg_fouls / league_avg_fouls if league_avg_fouls > 0 else 1.0
                cards_ratio = ref_avg_cards / league_avg_cards if league_avg_cards > 0 else 1.0

                # Ponderación combinada
                weighted_fouls_ratio = 1.0 + ((fouls_ratio - 1.0) * confidence_weight)
                weighted_cards_ratio = 1.0 + ((cards_ratio - 1.0) * confidence_weight)

                # Probabilidades estimadas basadas en la tendencia del árbitro
                # (Probabilidad base 70.0% * factor del árbitro)
                fouls_prob = min(round(70.0 * weighted_fouls_ratio, 1), 95.0)
                cards_prob = min(round(68.0 * weighted_cards_ratio, 1), 95.0)

                # 5. Selección del mercado con mayor probabilidad según la severidad del árbitro
                if fouls_prob >= 80.0 or cards_prob >= 80.0:
                    if fouls_prob >= cards_prob:
                        market = f"Más de {round(league_avg_fouls, 0) + 0.5} Faltas Totales"
                        prob = fouls_prob
                    else:
                        market = f"Más de {round(league_avg_cards, 0) + 0.5} Tarjetas Amarillas"
                        prob = cards_prob
                    
                    simulated_odds = round(max(1.40, 2.15 - ((prob - 80.0) * 0.03)), 2)

                    high_prob_picks.append({
                        "match_name": f"{home_name} vs {away_name}",
                        "referee": referee,
                        "referee_matches": matches_count,
                        "ref_avg_fouls": round(ref_avg_fouls, 1),
                        "market": market,
                        "probability": prob,
                        "odds": simulated_odds,
                        "league_id": league_id,
                        "season": season,
                        "match_date": match_date
                    })

        return high_prob_picks

    @staticmethod
    def save_simulation(db_manager, bet_data):
        """Guarda la apuesta en la BD asegurando que no existan duplicados."""
        repo = BettingRepository(db_manager)
        return repo.save_bet_unique(bet_data) # <-- Aquí conectas el método único
            
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

    @staticmethod
    def calculate_player_over_fouls(fouls_per_90: float, threshold: float = 0.5, expected_minutes: int = 90) -> float:
        """Saca la probabilidad de que un jugador cometa > N faltas usando distribución de Poisson."""
        if fouls_per_90 <= 0:
            return 0.0
        
        lam = (fouls_per_90 * expected_minutes) / 90.0
        
        # P(X >= k) = 1 - Sum(P(X = i)) para i de 0 a floor(threshold)
        k_floor = math.floor(threshold)
        prob_less_or_equal = 0.0
        
        for i in range(k_floor + 1):
            prob_less_or_equal += (math.exp(-lam) * (lam ** i)) / math.factorial(i)
            
        return round((1.0 - prob_less_or_equal) * 100, 1)

    @staticmethod
    def get_match_value_bets(top_home: dict, top_away: dict):
        """Genera sugerencias de valor rápido para las tarjetas de la vista."""
        suggestions = []
        
        # Evaluar Top Local
        if top_home.get("fouls_per_90", 0) >= 1.5:
            prob = BettingController.calculate_player_over_fouls(top_home["fouls_per_90"], threshold=0.5)
            suggestions.append(f"🔥 {top_home['name']}: +0.5 faltas ({prob}%)")
            
        # Evaluar Top Visitante
        if top_away.get("fouls_per_90", 0) >= 1.5:
            prob = BettingController.calculate_player_over_fouls(top_away["fouls_per_90"], threshold=0.5)
            suggestions.append(f"🔥 {top_away['name']}: +0.5 faltas ({prob}%)")
            
        return suggestions