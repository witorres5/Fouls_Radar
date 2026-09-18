# services/parlay_service.py
import logging
from typing import List, Dict, Optional
from utils.betting_engine import BettingEngine

logger = logging.getLogger("FoulsRadar.ParlayService")


class ParlayService:
    """Constructor único de parlay diario híbrido (Faltas + Over 2.5 Goles)."""

    MAX_LEGS = 3

    @staticmethod
    def build_daily_league_parlay(
        picks: List[dict],
        goals_picks: Optional[List[dict]] = None,
        target_market: str = "Over 0.5 Faltas",
        fouls_line: float = 0.5,
        min_prob_threshold: float = 52.0,
        max_legs: int = 3,
    ) -> Optional[dict]:
        """
        Construye una combinada 1-3 legs con piso flexible EV+.

        - `picks`: dicts con {match, player, fouls_per_90, referee?, referee_factor?,
          expected_minutes?}. Prob Over `fouls_line` vía Poisson (raw) + 1 sola calibración.
        - `goals_picks`: dicts con {match, home_xg, away_xg}. Prob Over 2.5 ya calibrada.
        - `min_prob_threshold`: piso dinámico 52-65%. Default 52.0 para garantizar
          generación en días con cuotas ajustadas.
        """
        if not picks and not goals_picks:
            return None

        legs: List[Dict] = []
        combined_prob = 1.0
        combined_odds = 1.0

        # 1. Picks de faltas (jugador Over X.5)
        for item in (picks or []):
            try:
                f90 = float(item.get("fouls_per_90", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if f90 <= 0:
                continue

            referee_factor = float(item.get("referee_factor", 1.0) or 1.0)
            expected_minutes = int(item.get("expected_minutes", 85) or 85)

            # Raw sin calibrar + UNA sola calibración (evita doble descuento).
            raw_prob = BettingEngine.calculate_over_probability(
                metric_rate_per_90=f90,
                threshold=fouls_line,
                expected_minutes=expected_minutes,
                adjustment_factor=referee_factor,
                apply_calibration=False,
            )
            calibrated_prob = BettingEngine.calibrate_probability(raw_prob)

            if calibrated_prob < min_prob_threshold:
                continue

            prob_dec = calibrated_prob / 100.0
            fair_odds = BettingEngine.calculate_fair_odds(calibrated_prob)
            combined_prob *= prob_dec
            combined_odds *= fair_odds

            legs.append({
                "match": item.get("match", "N/D"),
                "selection": f"{item.get('player', 'N/D')} - {target_market}",
                "individual_prob": round(calibrated_prob, 1),
                "fair_odds": fair_odds,
            })
            if len(legs) >= max_legs:
                break

        # 2. Picks de goles (partido Over 2.5, ya calibrado internamente)
        if goals_picks and len(legs) < max_legs:
            for g in goals_picks:
                try:
                    home_lambda = float(g.get("home_xg", 0.0) or 0.0)
                    away_lambda = float(g.get("away_xg", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                if home_lambda <= 0 or away_lambda <= 0:
                    continue

                prob = BettingEngine.calculate_over25_goals_probability(
                    home_lambda, away_lambda
                )
                if prob < min_prob_threshold:
                    continue

                prob_dec = prob / 100.0
                fair_odds = BettingEngine.calculate_fair_odds(prob)
                combined_prob *= prob_dec
                combined_odds *= fair_odds

                legs.append({
                    "match": g.get("match", "N/D"),
                    "selection": "Partido - Over 2.5 Goles",
                    "individual_prob": round(prob, 1),
                    "fair_odds": fair_odds,
                })
                if len(legs) >= max_legs:
                    break

        if not legs:
            return None

        legs = legs[:max_legs]
        return {
            "legs_count": len(legs),
            "legs": legs,
            "combined_probability_pct": round(combined_prob * 100.0, 2),
            "combined_fair_odds": round(combined_odds, 2),
            "expected_value_flag": "EV+" if combined_odds >= 1.50 else "NEUTRAL",
        }
