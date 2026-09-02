# controllers/betting_controller.py
import re
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from databases.betting_repository import BettingRepository
from databases.fixture_repository import FixtureRepository
from controllers.fixture_controller import FixtureController
from utils.betting_engine import BettingEngine

logger = logging.getLogger("FoulsTracker.BettingController")

class BettingController:
    
    def __init__(self, repository: BettingRepository):
        self.repository = repository

    @staticmethod
    def get_high_probability_bets(db_manager, league_id: int, season: int) -> List[Dict[str, Any]]:
        """
        Algoritmo cuantitativo: Evalúa los próximos partidos aplicando Empirical Bayes
        al factor arbitral y calculando probabilidades de Poisson. Usa el modelo ML
        (PoissonRegressor) cuando está disponible, con fallback al modelo analítico.
        """
        upcoming_fixtures = FixtureController.get_upcoming_fixtures_cached(league_id, season, days=3)
        if not upcoming_fixtures:
            return []

        fixture_repo = FixtureRepository(db_manager)
        league_avg_fouls, league_avg_cards = fixture_repo.get_league_averages(league_id, season)
        
        high_prob_picks = []

        for fix in upcoming_fixtures:
            fix_info = fix.get("fixture", {})
            fixture_id = fix_info.get("id")
            teams = fix.get("teams", {})
            home_id = teams.get("home", {}).get("id")
            away_id = teams.get("away", {}).get("id")
            home_name = teams.get("home", {}).get("name", "Local")
            away_name = teams.get("away", {}).get("name", "Visitante")
            referee_raw = fix_info.get("referee")
            
            if not referee_raw or not isinstance(referee_raw, str) or not referee_raw.strip():
                continue

            referee = referee_raw.strip()
            match_date = (fix_info.get("date") or "")[:10]
            
            # Métricas históricas del árbitro
            matches_count, ref_avg_fouls, ref_avg_cards = fixture_repo.get_referee_historical_stats(referee)
            if matches_count == 0:
                continue

            # Factor Bayesiano del árbitro
            fouls_ref_factor = BettingEngine.calculate_referee_factor(
                ref_avg_fouls=ref_avg_fouls,
                league_avg_fouls=league_avg_fouls,
                ref_matches_count=matches_count,
                prior_weight=5.0
            )
            cards_ref_factor = BettingEngine.calculate_referee_factor(
                ref_avg_fouls=ref_avg_cards,
                league_avg_fouls=league_avg_cards,
                ref_matches_count=matches_count,
                prior_weight=5.0
            )

            # Feature: faltas recibidas por el equipo visitante (rival del equipo local)
            opp_drawn_per_90 = 0.25  # default conservador
            if away_id:
                opp_drawn_per_90 = fixture_repo.get_team_drawn_fouls_avg(away_id, season) or 0.25

            # Calcular probabilidades con ML + fallback analítico
            foul_line = round(league_avg_fouls) - 0.5
            card_line = round(league_avg_cards) - 0.5

            fouls_prob, used_ml_fouls = BettingEngine.calculate_ml_over_probability(
                fouls_per_90=league_avg_fouls,
                threshold=foul_line,
                opp_drawn_per_90=opp_drawn_per_90,
                referee_factor=fouls_ref_factor,
                is_home=1,
                league_avg_fouls=league_avg_fouls,
                expected_minutes=90,
            )
            cards_prob, used_ml_cards = BettingEngine.calculate_ml_over_probability(
                fouls_per_90=league_avg_cards,
                threshold=card_line,
                opp_drawn_per_90=opp_drawn_per_90,
                referee_factor=cards_ref_factor,
                is_home=1,
                league_avg_fouls=league_avg_cards,
                expected_minutes=90,
            )

            if fouls_prob >= 80.0 or cards_prob >= 80.0:
                if fouls_prob >= cards_prob:
                    market = f"Más de {foul_line} Faltas Totales"
                    prob = fouls_prob
                    used_ml = used_ml_fouls
                else:
                    market = f"Más de {card_line} Tarjetas Amarillas"
                    prob = cards_prob
                    used_ml = used_ml_cards
                
                simulated_odds = BettingEngine.calculate_fair_odds(prob, bookmaker_margin=0.06)

                high_prob_picks.append({
                    "fixture_id": fixture_id,
                    "match_name": f"{home_name} vs {away_name}",
                    "referee": referee,
                    "referee_matches": matches_count,
                    "ref_avg_fouls": round(ref_avg_fouls, 1),
                    "market": market,
                    "probability": prob,
                    "odds": simulated_odds,
                    "league_id": league_id,
                    "season": season,
                    "match_date": match_date,
                    "model_used": "🤖 ML (PoissonRegressor)" if used_ml else "📐 Analítico (Poisson+Bayes)",
                })

        return high_prob_picks


    @staticmethod
    def save_simulation(db_manager, bet_data: dict) -> bool:
        """Guarda la apuesta en la BD asegurando que no existan duplicados."""
        repo = BettingRepository(db_manager)
        return repo.save_bet_unique(bet_data)

    @staticmethod
    def save_bet_unique(db_manager, bet_data: dict) -> bool:
        """Alias compatible con scripts externos."""
        return BettingController.save_simulation(db_manager, bet_data)

    @staticmethod
    def get_history_df(db_manager, league_id: int, season: int) -> pd.DataFrame:
        repo = BettingRepository(db_manager)
        return repo.get_simulated_bets(league_id, season)

    @staticmethod
    def evaluate_pending_bets(db_manager, league_id: int, season: int, today_str: str):
        """Evalúa las apuestas pendientes con soporte exacto de fixture_id y parsing seguro."""
        pending_bets = BettingRepository.get_pending_bets_by_date(db_manager, league_id, season, today_str)
        if not pending_bets:
            logger.debug(f"No hay apuestas pendientes para evaluar en fecha {today_str}.")
            return

        for bet in pending_bets:
            bet_id = bet[0]
            match_name = bet[1]
            market = bet[2]
            fixture_id_db = bet[3] if len(bet) > 3 else None

            fixture = BettingRepository.get_fixture_result(
                db_manager, match_name, league_id, season, fixture_id=fixture_id_db
            )
            if not fixture:
                continue

            fixture_id, status, total_fouls, total_yellow_cards = fixture

            if status in ["FT", "Match Finished", "AET", "PEN"]:
                won = None
                market_lower = market.lower()
                
                # Extraer números de la línea evitando confundir con números del nombre
                # Busca patrones de línea como +0.5, -1.5, 22.5
                line_match = re.search(r"([+-]?\d+(?:\.\d+)?)", market)
                if not line_match:
                    logger.warning(f"No se encontró línea numérica en mercado '{market}' (Bet ID: {bet_id}).")
                    continue

                line_value = float(line_match.group(1))
                is_under = "menos" in market_lower or "under" in market_lower

                is_global_fouls = "faltas totales" in market_lower or "total fouls" in market_lower
                is_global_cards = "tarjetas amarillas" in market_lower or "yellow cards" in market_lower

                if is_global_fouls or is_global_cards:
                    if is_global_fouls:
                        actual_fouls = total_fouls or 0
                        won = actual_fouls < line_value if is_under else actual_fouls > line_value
                    elif is_global_cards:
                        actual_cards = total_yellow_cards or 0
                        won = actual_cards < line_value if is_under else actual_cards > line_value
                else:
                    # Extraer nombre del jugador
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
                        logger.debug(f"Sin estadísticas de fixture aún para jugador '{target_player}' en fixture {fixture_id}.")
                        continue

                if won is not None:
                    new_status = "GANADA" if won else "PERDIDA"
                    BettingRepository.update_bet_status(db_manager, bet_id, new_status)
                    logger.info(f"Apuesta ID {bet_id} ({market}) actualizada a {new_status}.")

    @staticmethod
    def get_performance_metrics(db_manager, league_id: int, season: int) -> dict:
        """Calcula las métricas de rendimiento financiero y backtesting."""
        df = BettingRepository.get_evaluated_bets(db_manager, league_id, season)

        if df.empty:
            return {"has_data": False}

        total_bets = len(df)
        wins = len(df[df["status"] == "GANADA"])
        win_rate = (wins / total_bets) * 100 if total_bets > 0 else 0.0

        # Cálculo de profit por apuesta respetando cuota
        df["profit"] = df.apply(
            lambda row: (float(row["odds"]) - 1.0) if row["status"] == "GANADA" else -1.0, 
            axis=1
        )
        df["cumulative_profit"] = df["profit"].cumsum()

        net_profit = df["profit"].sum()
        total_staked = total_bets * 1.0
        yield_pct = (net_profit / total_staked) * 100 if total_staked > 0 else 0.0

        market_stats = df.groupby("market").agg(
            Total=("status", "count"),
            Ganadas=("status", lambda x: (x == "GANADA").sum()),
            Yield=("profit", lambda x: (x.sum() / len(x)) * 100 if len(x) > 0 else 0.0)
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
    def get_today_high_prob_summary(db_manager, today_str: str) -> Optional[str]:
        """Construye el mensaje resumido de apuestas pendientes para el bot."""
        bets = BettingRepository.get_high_prob_pending_bets_today(db_manager, today_str)

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

    @staticmethod
    def train_ml_model(db_manager, alpha: float = 1.0, max_iter: int = 500) -> dict:
        """
        Entrena el modelo ML (PoissonRegressor) con los datos históricos de la BD.
        Retorna un diccionario con métricas: success, n_samples, d2_score, coefficients.
        """
        try:
            from services.ml_engine import MLEngine
            result = MLEngine.train(db_manager, alpha=alpha, max_iter=max_iter)
            return result
        except Exception as e:
            logger.error(f"Error entrenando modelo ML: {e}")
            return {"success": False, "message": str(e), "n_samples": 0}

    @staticmethod
    def get_ml_model_info() -> dict:
        """Retorna información del estado actual del modelo ML (si existe y su calidad)."""
        try:
            from services.ml_engine import MLEngine
            return MLEngine.get_model_info()
        except Exception as e:
            return {"available": False, "message": str(e)}
