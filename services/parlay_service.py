# services/parlay_service.py
import logging
import math
from typing import List, Dict, Optional
from utils.betting_engine import BettingEngine

logger = logging.getLogger("FoulsRadar.ParlayService")

class ParlayService:

    @staticmethod
    def build_daily_league_parlay(
        picks: List[dict], 
        target_market: str = "Over 1.5 Faltas"
    ) -> Optional[dict]:
        """
        Construye un parlay combinando entre 1 y 3 selecciones de una misma liga.
        Calcula la probabilidad acumulada y la cuota justa esperada.
        """
        if not picks:
            return None

        legs = []
        combined_prob = 1.0
        combined_odds = 1.0

        for item in picks:
            # 1. Probabilidad individual calibrada (usando Poisson / Platt Scaler)
            raw_prob = BettingEngine.calculate_over_probability(
                metric_rate_per_90=item["fouls_per_90"],
                target_line=1.5
            )
            calibrated_prob = BettingEngine.calibrate_probability(raw_prob)
            
            # Filtro de calidad (solo entra si pasa el floor ajustado)
            if calibrated_prob < 65.0:
                continue

            prob_decimal = calibrated_prob / 100.0
            fair_odds = round(1.0 / prob_decimal, 2) if prob_decimal > 0 else 1.0

            combined_prob *= prob_decimal
            combined_odds *= fair_odds

            legs.append({
                "match": item["match"],
                "selection": f"{item['player']} - {target_market}",
                "individual_prob": calibrated_prob,
                "fair_odds": fair_odds
            })

        if not legs:
            return None

        final_parlay_prob = round(combined_prob * 100.0, 2)
        final_parlay_odds = round(combined_odds, 2)

        return {
            "legs_count": len(legs),
            "legs": legs,
            "combined_probability_pct": final_parlay_prob,
            "combined_fair_odds": final_parlay_odds,
            "expected_value_flag": "EV+" if final_parlay_odds >= 1.50 else "NEUTRAL"
        }

    @staticmethod
    def build_daily_league_parlay(picks: list, goals_picks: list = None) -> dict:
        """
        Construye una combinada diaria integrando selecciones de Faltas 
        y Mercado Over 2.5 Goles si superan el umbral EV+ (65%).
        """
        legs = []
        combined_prob = 1.0
        combined_odds = 1.0

        # 1. Procesar Picks de Faltas
        for item in picks:
            raw_prob = BettingEngine.calculate_over_probability(
                metric_rate_per_90=item["fouls_per_90"], threshold=0.5
            )
            calibrated_prob = BettingEngine.calibrate_probability(raw_prob)

            if calibrated_prob >= 65.0:
                prob_dec = calibrated_prob / 100.0
                fair_odds = round(1.0 / prob_dec, 2)
                combined_prob *= prob_dec
                combined_odds *= fair_odds

                legs.append({
                    "match": item["match"],
                    "selection": f"{item['player']} - Over 1.5 Faltas",
                    "individual_prob": calibrated_prob,
                    "fair_odds": fair_odds
                })

        # 2. Procesar Picks de Goles (Over 2.5)
        if goals_picks:
            for g in goals_picks:
                prob = BettingEngine.calculate_over25_goals_probability(
                    home_lambda=g["home_xg"], away_lambda=g["away_xg"]
                )

                if prob >= 60.0:  # Umbral ajustado para Over 2.5
                    prob_dec = prob / 100.0
                    fair_odds = round(1.0 / prob_dec, 2)
                    combined_prob *= prob_dec
                    combined_odds *= fair_odds

                    legs.append({
                        "match": g["match"],
                        "selection": "Partido - Over 2.5 Goles",
                        "individual_prob": prob,
                        "fair_odds": fair_odds
                    })

        if not legs:
            return None

        return {
            "legs_count": len(legs),
            "legs": legs,
            "combined_probability_pct": round(combined_prob * 100.0, 2),
            "combined_fair_odds": round(combined_odds, 2),
            "expected_value_flag": "EV+" if combined_odds >= 1.50 else "NEUTRAL"
        }
