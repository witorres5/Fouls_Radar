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

            # Calcular probabilidades de Faltas Totales con ML + fallback analítico
            # (Mercado de Tarjetas Amarillas desactivado para optimizar ROI y reducir varianza)
            foul_line = round(league_avg_fouls) - 0.5

            fouls_prob, used_ml_fouls = BettingEngine.calculate_ml_over_probability(
                fouls_per_90=league_avg_fouls,
                threshold=foul_line,
                opp_drawn_per_90=opp_drawn_per_90,
                referee_factor=fouls_ref_factor,
                is_home=1,
                league_avg_fouls=league_avg_fouls,
                expected_minutes=90,
            )

            if fouls_prob >= 80.0:
                market = f"Más de {foul_line} Faltas Totales"
                prob = fouls_prob
                used_ml = used_ml_fouls
                
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
        """Obtiene el historial de apuestas evaluando primero cualquier pendiente con resultado disponible."""
        BettingController.evaluate_pending_bets(db_manager, league_id, season)
        repo = BettingRepository(db_manager)
        return repo.get_simulated_bets(league_id, season)

    @staticmethod
    def evaluate_pending_bets(
        db_manager, 
        league_id: Optional[int] = None, 
        season: Optional[int] = None, 
        today_str: Optional[str] = None
    ) -> dict:
        """
        Evalúa y liquida todas las apuestas pendientes para partidos que ya han finalizado.
        
        Mejoras estructurales:
          1. Sin restricción de fecha: evalúa todas las apuestas pendientes con resultados disponibles.
          2. Clasificación universal de mercados (Partido vs Jugador, Faltas vs Tarjetas, Over vs Under).
          3. Manejo de jugadores ausentes / suplentes (DNP): si el partido ya terminó y tiene estadísticas,
             el jugador registra 0 faltas y la apuesta se liquida justamente.
          4. Autocorrección de fixture_id si no estaba guardado en la apuesta.
          5. Liquidación de partidos cancelados/anulados como 'ANULADA'.
        """
        pending_bets = BettingRepository.get_all_pending_bets(db_manager, league_id, season)
        if not pending_bets:
            logger.debug("No hay apuestas pendientes para evaluar.")
            return {"evaluated": 0, "won": 0, "lost": 0, "void": 0}

        evaluated_count = 0
        won_count = 0
        lost_count = 0
        void_count = 0

        for bet in pending_bets:
            bet_id = bet[0]
            match_name = bet[1]
            market = bet[2]
            fixture_id_db = bet[3]
            b_league = bet[4] if len(bet) > 4 else league_id
            b_season = bet[5] if len(bet) > 5 else season

            # 1. Obtener resultado del partido
            fixture = BettingRepository.get_fixture_result(
                db_manager, match_name, b_league, b_season, fixture_id=fixture_id_db
            )
            if not fixture:
                continue

            fixture_id, status, total_fouls, total_yellow_cards = fixture

            # Backfill del fixture_id si estaba vacío
            if fixture_id and not fixture_id_db:
                try:
                    BettingRepository.update_bet_fixture_id(db_manager, bet_id, fixture_id)
                except Exception:
                    pass

            status_upper = (status or "").upper().strip()

            # 2. Manejo de partidos cancelados o abandonados
            if status_upper in ["CANC", "ABD", "AWD", "WO", "CANCELLED", "ABANDONED", "PST", "POSTPONED"]:
                if status_upper in ["CANC", "ABD", "AWD", "WO", "CANCELLED", "ABANDONED"]:
                    BettingRepository.update_bet_status(db_manager, bet_id, "ANULADA")
                    void_count += 1
                    evaluated_count += 1
                    logger.info(f"Apuesta ID {bet_id} ({match_name}) marcada como ANULADA por partido cancelado/abandonado.")
                continue

            # 3. Evaluación de partidos finalizados
            if status_upper in ["FT", "MATCH FINISHED", "AET", "PEN"]:
                market_clean = market.strip()
                market_lower = market_clean.lower()

                # Dirección: Under vs Over
                is_under = bool(re.search(r'\b(menos|under|<)\b', market_lower) or market_clean.startswith("-"))

                # Extraer línea numérica precisa (ej. +0.5, >22.5, 3.5)
                line_match = re.search(r'(?:más de|menos de|over|under|[><+-])\s*(\d+(?:\.\d+)?)', market_lower)
                if not line_match:
                    line_match = re.search(r'\b(\d+\.\d+)\b', market_lower) or re.search(r'\b(\d+)\b', market_lower)

                if not line_match:
                    logger.warning(f"No se encontró línea numérica en mercado '{market}' (Bet ID: {bet_id}).")
                    continue

                line_value = float(line_match.group(1))
                is_card_market = any(w in market_lower for w in ["tarjeta", "card", "amarilla", "yellow"])

                # Detectar si es mercado de JUGADOR o de PARTIDO
                target_player = None
                if "(" in market_clean and ")" in market_clean:
                    p1 = market_clean[:market_clean.find("(")].strip()
                    p2 = market_clean[market_clean.find("(")+1:market_clean.find(")")].strip()
                    if any(w in p2.lower() for w in ["falta", "foul", "tarjeta", "card", "+", "-", "over", "under", "más", "menos"]):
                        target_player = p1
                    elif any(w in p1.lower() for w in ["falta", "foul", "tarjeta", "card", "+", "-", "over", "under", "más", "menos"]):
                        target_player = p2
                elif " - " in market_clean:
                    parts = market_clean.split(" - ")
                    if any(w in parts[1].lower() for w in ["falta", "foul", "tarjeta", "card", "+", "-", "over", "under", "más", "menos"]):
                        target_player = parts[0].strip()
                    elif any(w in parts[0].lower() for w in ["falta", "foul", "tarjeta", "card", "+", "-", "over", "under", "más", "menos"]):
                        target_player = parts[1].strip()

                won = None

                if target_player:
                    # EVALUACIÓN DE JUGADOR
                    player_stats = BettingRepository.get_player_stats_by_fixture(
                        db_manager, fixture_id, target_player
                    )
                    
                    if player_stats is None:
                        # Si no hay stats en BD para este fixture, intentar sincronizarlas on-demand desde la API
                        has_stats = BettingRepository.fixture_has_player_stats(db_manager, fixture_id)
                        if not has_stats:
                            try:
                                from services.api_service import APIFootballService
                                api_service = APIFootballService()
                                player_stats_map = api_service.get_fixture_player_stats(fixture_id)
                                if player_stats_map:
                                    raw_stats = [
                                        (
                                            fixture_id, pid, str(p.get("player_name", "")).strip(), p.get("team_id"),
                                            int(p.get("minutes_played") or 0), int(p.get("fouls_committed") or 0),
                                            int(p.get("fouls_drawn") or 0), int(p.get("yellow_cards") or 0), int(p.get("red_cards") or 0)
                                        )
                                        for pid, p in player_stats_map.items() if isinstance(p, dict)
                                    ]
                                    BettingRepository.save_player_fixture_stats(db_manager, raw_stats)
                                    has_stats = True
                                    # Reintentar búsqueda de estadísticas con los datos frescos
                                    player_stats = BettingRepository.get_player_stats_by_fixture(
                                        db_manager, fixture_id, target_player
                                    )
                            except Exception as sync_err:
                                logger.debug(f"Error sincronizando stats on-demand para fixture {fixture_id}: {sync_err}")

                    if player_stats is not None:
                        actual_val = player_stats.get("yellow_cards", 0) if is_card_market else player_stats.get("fouls_committed", 0)
                        won = (actual_val < line_value) if is_under else (actual_val > line_value)
                    else:
                        # Si el partido está FT y ya se descargaron o verificaron las estadísticas del encuentro:
                        # El jugador no cometió faltas (jugó 0 min, suplente o 0 faltas registradas)
                        actual_val = 0
                        won = (actual_val < line_value) if is_under else (actual_val > line_value)
                else:
                    # EVALUACIÓN DE PARTIDO COMPLETO
                    actual_val = (total_yellow_cards or 0) if is_card_market else (total_fouls or 0)
                    won = (actual_val < line_value) if is_under else (actual_val > line_value)


                if won is not None:
                    new_status = "GANADA" if won else "PERDIDA"
                    BettingRepository.update_bet_status(db_manager, bet_id, new_status)
                    evaluated_count += 1
                    if won:
                        won_count += 1
                    else:
                        lost_count += 1
                    logger.info(f"Apuesta ID {bet_id} ({match_name} | {market}) actualizada a {new_status}.")

        return {"evaluated": evaluated_count, "won": won_count, "lost": lost_count, "void": void_count}

    @staticmethod
    def get_performance_metrics(db_manager, league_id: int, season: int) -> dict:
        """Calcula las métricas de rendimiento financiero y backtesting."""
        BettingController.evaluate_pending_bets(db_manager, league_id, season)
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

            id,  match_name, market, referee, prob, odds, _ = bet
            message += f"⚽ **{match_name}**\n"
            message += f"👨‍⚖️ Árbitro: {referee}\n"
            message += f"🎯 Mercado: {market}\n"
            message += f"🔥 Probabilidad: {prob}%\n"
            message += f"💰 Cuota: {odds}\n"
            message += f"-----------------------------------\n"
            BettingRepository.mark_as_notified(db_manager,id)
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
