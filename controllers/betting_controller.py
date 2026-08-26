# controllers/betting_controller.py
from databases.betting_repository import BettingRepository
from controllers.fixture_controller import FixtureController
import math
import re
import pandas as pd

class BettingController:
    
    def __init__(self, repository: BettingRepository):
        self.repository = repository

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
                
                # Validación 1: Verificar que el nombre del árbitro venga informado en la API
                if not referee_raw or not isinstance(referee_raw, str) or not referee_raw.strip():
                    continue

                referee = referee_raw.strip()
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

                # Validación 2: Si el árbitro no tiene partidos dirigidos registrados en BD, ignorar
                if matches_count == 0:
                    continue

                ref_avg_fouls = ref_row[1] if (ref_row and ref_row[1] is not None) else league_avg_fouls
                ref_avg_cards = ref_row[2] if (ref_row and ref_row[2] is not None) else league_avg_cards

                # 4. Calcular Factores de Ponderación (Árbitro vs Liga)
                confidence_weight = min(matches_count / 5.0, 1.0)
                
                fouls_ratio = ref_avg_fouls / league_avg_fouls if league_avg_fouls > 0 else 1.0
                cards_ratio = ref_avg_cards / league_avg_cards if league_avg_cards > 0 else 1.0

                weighted_fouls_ratio = 1.0 + ((fouls_ratio - 1.0) * confidence_weight)
                weighted_cards_ratio = 1.0 + ((cards_ratio - 1.0) * confidence_weight)

                fouls_prob = min(round(70.0 * weighted_fouls_ratio, 1), 95.0)
                cards_prob = min(round(68.0 * weighted_cards_ratio, 1), 95.0)

                # 5. Selección del mercado con mayor probabilidad según la severidad del árbitro
                if fouls_prob >= 90.0 or cards_prob >= 90.0:
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
        return repo.save_bet_unique(bet_data)

    @staticmethod
    def get_history_df(db_manager, league_id, season):
        repo = BettingRepository(db_manager)
        return repo.get_simulated_bets(league_id, season)

    @staticmethod
    def evaluate_pending_bets(db_manager, league_id, season, today_str):
        pending_bets = BettingRepository.get_pending_bets_by_date(db_manager, league_id, season, today_str)
        print("-----------------------------------PENDING---------------------",pending_bets)
        if not pending_bets:
            print(f">>> DEBUG: No hay apuestas pendientes por evaluar para la fecha {today_str}.")
            return

        for bet in pending_bets:
            bet_id = bet[0]
            match_name = bet[1]
            market = bet[2]
            player_name = bet[3] if len(bet) > 3 else None

            fixture = BettingRepository.get_fixture_result(db_manager, match_name, league_id, season)
            if not fixture:
                continue

            fixture_id, status, total_fouls, total_yellow_cards = fixture

            if status in ["FT", "Match Finished", "AET", "PEN"]:
                won = None  # Se inicializa en None para validar si realmente se pudo evaluar
                market_lower = market.lower()
                numbers = re.findall(r"[-+]?\d*\.\d+|\d+", market)

                if not numbers:
                    print(f">>> ADVERTENCIA: No se encontró valor numérico en el mercado '{market}' (Bet ID: {bet_id}).")
                    continue

                line_value = float(numbers[0])
                is_under = "menos" in market_lower or "under" in market_lower

                # Identificar si es un mercado GLOBAL del partido
                is_global_fouls = "faltas totales" in market_lower or "total fouls" in market_lower
                is_global_cards = "tarjetas amarillas" in market_lower or "yellow cards" in market_lower

                # CASO A: Apuestas GLOBALES DEL PARTIDO
                if is_global_fouls or is_global_cards:
                    if is_global_fouls:
                        actual_fouls = total_fouls or 0
                        won = actual_fouls < line_value if is_under else actual_fouls > line_value
                    elif is_global_cards:
                        actual_cards = total_yellow_cards or 0
                        won = actual_cards < line_value if is_under else actual_cards > line_value

                # CASO B: Apuesta por JUGADOR ESPECÍFICO
                else:
                    target_player = player_name
                    if not target_player:
                        # Extraer nombre si el formato es "H. Heggheim (+0.5 faltas)" o "H. Heggheim - 0.5 faltas"
                        if "(" in market:
                            target_player = market.split("(")[0].strip()
                        elif "-" in market:
                            target_player = market.split("-")[0].strip()
                        else:
                            target_player = market.strip()

                    player_stats = BettingRepository.get_player_stats_by_fixture(
                        db_manager, fixture_id, target_player
                    )

                    if player_stats:
                        player_fouls = player_stats.get("fouls_committed", 0)
                        player_cards = player_stats.get("yellow_cards", 0)

                        if "tarjeta" in market_lower or "card" in market_lower:
                            won = player_cards < line_value if is_under else player_cards > line_value
                        else:
                            won = player_fouls < line_value if is_under else player_fouls > line_value
                    else:
                        print(f">>> ADVERTENCIA: No se encontraron estadísticas para el jugador '{target_player}' en Fixture ID {fixture_id}.")
                        continue

                # Actualizar únicamente si la apuesta fue evaluada exitosamente
                if won is not None:
                    new_status = "GANADA" if won else "PERDIDA"
                    BettingRepository.update_bet_status(db_manager, bet_id, new_status)
                    print(f">>> DEBUG: Apuesta ID {bet_id} ({market}) actualizada a {new_status}.")

    @staticmethod
    def calculate_player_over_fouls(fouls_per_90: float, threshold: float = 0.5, expected_minutes: int = 90) -> float:
        """Saca la probabilidad de que un jugador cometa > N faltas usando distribución de Poisson."""
        if fouls_per_90 <= 0:
            return 0.0
        
        lam = (fouls_per_90 * expected_minutes) / 90.0
        k_floor = math.floor(threshold)
        prob_less_or_equal = 0.0
        
        for i in range(k_floor + 1):
            prob_less_or_equal += (math.exp(-lam) * (lam ** i)) / math.factorial(i)
            
        return round((1.0 - prob_less_or_equal) * 100, 1)

    @staticmethod
    def get_match_value_bets(top_home: dict, top_away: dict):
        """Genera sugerencias de valor rápido para las tarjetas de la vista."""
        suggestions = []
        
        if top_home.get("fouls_per_90", 0) >= 1.5:
            prob = BettingController.calculate_player_over_fouls(top_home["fouls_per_90"], threshold=0.5)
            suggestions.append(f"🔥 {top_home['name']}: +0.5 faltas ({prob}%)")
            
        if top_away.get("fouls_per_90", 0) >= 1.5:
            prob = BettingController.calculate_player_over_fouls(top_away["fouls_per_90"], threshold=0.5)
            suggestions.append(f"🔥 {top_away['name']}: +0.5 faltas ({prob}%)")
            
        return suggestions
    
    @staticmethod
    def get_performance_metrics(db_manager, league_id, season):
        """Calcula las métricas de rendimiento y backtesting."""
        # Invocación estática pasando db_manager al repositorio
        df = BettingRepository.get_evaluated_bets(db_manager, league_id, season)

        if df.empty:
            return {"has_data": False}

        # Cálculo de métricas
        total_bets = len(df)
        wins = len(df[df["status"] == "GANADA"])
        win_rate = (wins / total_bets) * 100 if total_bets > 0 else 0.0

        # Asumiendo apostar 1 unidad ($100) por apuesta o cálculo según cuotas/profit
        df["profit"] = df.apply(
            lambda row: (row["odds"] - 1) if row["status"] == "GANADA" else -1.0, 
            axis=1
        )
        df["cumulative_profit"] = df["profit"].cumsum()

        net_profit = df["profit"].sum()
        total_staked = total_bets * 1.0
        yield_pct = (net_profit / total_staked) * 100 if total_staked > 0 else 0.0

        # Resumen por mercado
        market_stats = df.groupby("market").agg(
            Total=("status", "count"),
            Ganadas=("status", lambda x: (x == "GANADA").sum()),
            Yield=("profit", lambda x: (x.sum() / len(x)) * 100)
        ).reset_index()

        return {
            "has_data": True,
            "df": df,
            "total_bets": total_bets,
            "win_rate": win_rate,
            "net_profit": net_profit,
            "yield_pct": yield_pct,
            "market_stats": market_stats
        }
        
    @staticmethod
    def get_today_high_prob_summary(db_manager, today_str: str) -> str:
        """Construye el mensaje resumido de apuestas pendientes para el bot."""
        bets = BettingRepository.get_high_prob_pending_bets_today(db_manager,today_str)

        if not bets:
            return None

        message = f"🚨 **APUESTAS PENDIENTES DEL DÍA (Probabilidad ≥ 90%)** 🚨\n"
        message += f"📅 Fecha: {today_str}\n"
        message += f"📊 Total encontradas: {len(bets)}\n\n"

        for bet in bets:
            _, match_name, market, referee, prob, odds, _ = bet
            message += f"⚽ **{match_name}**\n"
            message += f"👨‍⚖️ Árbitro: {referee}\n"
            message += f"🎯 Mercado: {market}\n"
            message += f"🔥 Probabilidad: {prob}%\n"
            message += f"💰 Cuota: {odds}\n"
            message += f"-----------------------------------\n"

        return message