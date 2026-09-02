# utils/betting_engine.py
import math
import logging
from typing import Optional

logger = logging.getLogger("FoulsTracker.BettingEngine")

class BettingEngine:

    @staticmethod
    def calculate_referee_factor(
        ref_avg_fouls: float, 
        league_avg_fouls: float, 
        ref_matches_count: int, 
        prior_weight: float = 5.0
    ) -> float:
        """
        Calcula el factor de rigurosidad del árbitro usando contracción Bayesiana (Empirical Bayes)
        para regularizar muestras pequeñas hacia el promedio de la liga.
        """
        if league_avg_fouls <= 0:
            return 1.0
        
        if ref_matches_count <= 0 or ref_avg_fouls <= 0:
            return 1.0

        # Media a posteriori contraída hacia la media de la liga
        shrunk_ref_avg = (
            (ref_matches_count * ref_avg_fouls) + (prior_weight * league_avg_fouls)
        ) / (ref_matches_count + prior_weight)

        return round(shrunk_ref_avg / league_avg_fouls, 3)

    @staticmethod
    def calculate_over_probability(
        metric_rate_per_90: float, 
        threshold: float = 0.5, 
        expected_minutes: int = 85,
        adjustment_factor: float = 1.0
    ) -> float:
        """
        Calcula la probabilidad acumulada P(X > threshold) para cualquier umbral
        usando un proceso de Poisson ajustado por minutos proyectados y factor de árbitro.
        """
        if metric_rate_per_90 <= 0 or expected_minutes <= 0:
            return 0.0

        lam = ((metric_rate_per_90 * expected_minutes) / 90.0) * adjustment_factor
        k_floor = math.floor(threshold)

        # Sumatoria P(X <= k)
        prob_less_or_equal = sum(
            (math.exp(-lam) * (lam ** i)) / math.factorial(i) 
            for i in range(k_floor + 1)
        )

        prob_over = max(0.0, min(1.0, 1.0 - prob_less_or_equal))
        return round(prob_over * 100.0, 1)

    @staticmethod
    def calculate_ml_over_probability(
        fouls_per_90: float,
        threshold: float = 0.5,
        opp_drawn_per_90: float = 0.25,
        referee_factor: float = 1.0,
        is_home: int = 0,
        league_avg_fouls: float = 22.5,
        expected_minutes: int = 85,
    ) -> tuple:
        """
        Calcula P(X > threshold) usando el modelo ML (PoissonRegressor) cuando está disponible.
        Si el modelo no está entrenado o falla, hace fallback automático al modelo analítico.

        Returns:
            (probability_pct: float, used_ml: bool)
            - probability_pct: Probabilidad en porcentaje [0-100].
            - used_ml: True si se usó el modelo de ML, False si se usó el modelo analítico.
        """
        # Intento con el motor de ML
        try:
            from services.ml_engine import MLEngine
            lam_ml = MLEngine.predict_lambda(
                fouls_per_90=fouls_per_90,
                opp_drawn_per_90=opp_drawn_per_90,
                referee_factor=referee_factor,
                is_home=is_home,
                league_avg_fouls=league_avg_fouls,
                expected_minutes=expected_minutes,
            )
            if lam_ml is not None and lam_ml > 0:
                k_floor = math.floor(threshold)
                prob_le = sum(
                    (math.exp(-lam_ml) * (lam_ml ** i)) / math.factorial(i)
                    for i in range(k_floor + 1)
                )
                prob_over = max(0.0, min(1.0, 1.0 - prob_le))
                return round(prob_over * 100.0, 1), True
        except Exception as e:
            logger.debug(f"MLEngine no disponible, usando modelo analítico: {e}")

        # Fallback: modelo analítico (Poisson univariado con factor de árbitro)
        prob_analytical = BettingEngine.calculate_over_probability(
            metric_rate_per_90=fouls_per_90,
            threshold=threshold,
            expected_minutes=expected_minutes,
            adjustment_factor=referee_factor,
        )
        return prob_analytical, False

    @staticmethod
    def calculate_player_over_fouls(
        fouls_per_90: float, 
        referee_factor: float = 1.0, 
        threshold: float = 0.5, 
        expected_minutes: int = 85
    ) -> float:
        """Alias para compatibilidad con código existente."""
        return BettingEngine.calculate_over_probability(
            metric_rate_per_90=fouls_per_90,
            threshold=threshold,
            expected_minutes=expected_minutes,
            adjustment_factor=referee_factor
        )

    @staticmethod
    def calculate_adjusted_prob(
        fouls_per_90: float, 
        referee_factor: float = 1.0, 
        threshold: float = 0.5
    ) -> float:
        """Calcula probabilidad Poisson ajustada por árbitro para Over {threshold}."""
        return BettingEngine.calculate_player_over_fouls(
            fouls_per_90=fouls_per_90,
            referee_factor=referee_factor,
            threshold=threshold,
            expected_minutes=85
        )

    @staticmethod
    def calculate_fair_odds(probability_pct: float, bookmaker_margin: float = 0.06) -> float:
        """Calcula cuotas simuladas realistas incorporando el margen comercial de la casa."""
        if probability_pct <= 0:
            return 1.85
        
        prob_decimal = probability_pct / 100.0
        adjusted_prob = prob_decimal * (1.0 + bookmaker_margin)
        fair_odd = 1.0 / adjusted_prob if adjusted_prob > 0 else 1.85
        return round(max(1.10, fair_odd), 2)
