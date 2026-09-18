# utils/betting_engine.py
import math
import logging
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger("FoulsTracker.BettingEngine")

# Ruta única del calibrador Platt (entrenado en services/calibration_service.py).
# La ruta apunta a models/platt_scaler.joblib; el servicio hace mkdir si falta.
CALIBRATOR_PATH = Path(__file__).resolve().parent.parent / "models" / "platt_scaler.joblib"

class BettingEngine:

    MIN_ODDS: float = 1.50  # Piso de cuota estricto para proteger el EV+

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

        shrunk_ref_avg = (
            (ref_matches_count * ref_avg_fouls) + (prior_weight * league_avg_fouls)
        ) / (ref_matches_count + prior_weight)

        return round(shrunk_ref_avg / league_avg_fouls, 3)

    @staticmethod
    def calculate_over_probability(
        metric_rate_per_90: float, 
        threshold: float = 0.5, 
        expected_minutes: int = 85,
        adjustment_factor: float = 1.0,
        apply_calibration: bool = True
    ) -> float:
        """
        Calcula la probabilidad acumulada P(X > threshold) usando Poisson ajustado 
        y aplica la calibración empírica por defecto.
        """
        if metric_rate_per_90 <= 0 or expected_minutes <= 0:
            return 0.0

        lam = ((metric_rate_per_90 * expected_minutes) / 90.0) * adjustment_factor
        k_floor = math.floor(threshold)

        prob_less_or_equal = sum(
            (math.exp(-lam) * (lam ** i)) / math.factorial(i) 
            for i in range(k_floor + 1)
        )

        prob_over = max(0.0, min(1.0, 1.0 - prob_less_or_equal))
        raw_prob_pct = prob_over * 100.0

        if apply_calibration:
            return BettingEngine.calibrate_probability(raw_prob_pct)

        return round(raw_prob_pct, 1)

    @staticmethod
    def calculate_ml_over_probability(
        fouls_per_90: float,
        threshold: float = 0.5,
        opp_drawn_per_90: float = 0.25,
        referee_factor: float = 1.0,
        is_home: int = 0,
        league_avg_fouls: float = 22.5,
        expected_minutes: int = 85,
        apply_calibration: bool = True
    ) -> Tuple[float, bool]:
        """
        Calcula P(X > threshold) usando el modelo ML (PoissonRegressor) o fallback analítico,
        aplicando calibración empírica de probabilidades.
        """
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
                raw_prob_pct = prob_over * 100.0
                
                final_prob = (
                    BettingEngine.calibrate_probability(raw_prob_pct) 
                    if apply_calibration 
                    else round(raw_prob_pct, 1)
                )
                return final_prob, True
        except Exception as e:
            logger.debug(f"MLEngine no disponible, usando modelo analítico: {e}")

        prob_analytical = BettingEngine.calculate_over_probability(
            metric_rate_per_90=fouls_per_90,
            threshold=threshold,
            expected_minutes=expected_minutes,
            adjustment_factor=referee_factor,
            apply_calibration=apply_calibration
        )
        return prob_analytical, False

    @staticmethod
    def calculate_player_over_fouls(
        fouls_per_90: float, 
        referee_factor: float = 1.0, 
        threshold: float = 0.5, 
        expected_minutes: int = 85
    ) -> float:
        """Alias de compatibilidad."""
        return BettingEngine.calculate_over_probability(
            metric_rate_per_90=fouls_per_90,
            threshold=threshold,
            expected_minutes=expected_minutes,
            adjustment_factor=referee_factor,
            apply_calibration=True
        )

    @staticmethod
    def calculate_adjusted_prob(
        fouls_per_90: float, 
        referee_factor: float = 1.0, 
        threshold: float = 0.5
    ) -> float:
        """Calcula probabilidad Poisson calibrada para Over {threshold}."""
        return BettingEngine.calculate_player_over_fouls(
            fouls_per_90=fouls_per_90,
            referee_factor=referee_factor,
            threshold=threshold,
            expected_minutes=85
        )

    @staticmethod
    def calculate_fair_odds(probability_pct: float, bookmaker_margin: float = 0.06) -> float:
        """
        Calcula la cuota sugerida incorporando el margen de la casa 
        y garantizando un piso de cuota estricto (MIN_ODDS >= 1.50).
        """
        if probability_pct <= 0:
            return 1.85

        prob_decimal = probability_pct / 100.0
        adjusted_prob = prob_decimal * (1.0 + bookmaker_margin)
        fair_odd = 1.0 / adjusted_prob if adjusted_prob > 0 else 1.85
        
        # Aplicar piso estricto de cuotas a 1.50 para descartar apuestas de bajo valor
        return round(max(BettingEngine.MIN_ODDS, fair_odd), 2)
    
    @staticmethod
    def _empirical_calibration(prob_pct: float) -> float:
        """Calibración empírica de backtesting (espacio 'publicado' de la plataforma).

        - Probabilidades >= 95% -> x0.76 (Acierto real ~75.6%)
        - Probabilidades 90% a 95% -> x0.70 (Acierto real ~64.4%)
        - Probabilidades 85% a 90% -> x0.67 (Acierto real ~57.6%)
        - Probabilidades < 85% -> x0.50 (descartadas por valor esperativo)
        """
        if prob_pct <= 0:
            return 0.0
        if prob_pct >= 95.0:
            calibrated = prob_pct * 0.76
        elif prob_pct >= 90.0:
            calibrated = prob_pct * 0.70
        elif prob_pct >= 85.0:
            calibrated = prob_pct * 0.67
        else:
            calibrated = prob_pct * 0.50
        return round(max(0.0, min(100.0, calibrated)), 1)

    @staticmethod
    def calibrate_probability(prob_pct: float) -> float:
        """
        Calibración única en cadena, autoconsistente con el dataset de entrenamiento:

          1. `_empirical_calibration(prob_pct)` -> probabilidad 'publicada' (el mismo
             valor que quedó guardado en `simulated_bets.probability` históricamente).
          2. Si existe `models/platt_scaler.joblib`, se aplica LogisticRegression sobre
             logit(publicada) -> probabilidad calibrada con datos reales de resultados
             (GANADA/PERDIDA). Si no existe el archivo, se devuelve la empírica.

        NOTA: los motores (`calculate_over_probability`, `calculate_over25_goals_probability`)
        ya invocan esta función internamente. No recalibrar su salida (evita doble descuento).
        """
        if prob_pct <= 0:
            return 0.0

        published_pct = BettingEngine._empirical_calibration(prob_pct)
        if published_pct <= 0:
            return 0.0

        if CALIBRATOR_PATH.exists():
            try:
                import joblib
                import numpy as np
                calibrator = joblib.load(CALIBRATOR_PATH)
                p_dec = np.clip(published_pct / 100.0, 1e-4, 1.0 - 1e-4)
                logit = np.array([[np.log(p_dec / (1.0 - p_dec))]])
                calibrated_pct = calibrator.predict_proba(logit)[0, 1] * 100.0
                return round(max(0.0, min(100.0, calibrated_pct)), 1)
            except Exception as e:
                logger.debug(f"Error aplicando calibrador guardado: {e}")

        return published_pct

    @staticmethod
    def calculate_poisson_pmf(k: int, lambd: float) -> float:
        """Calcula la función de masa de probabilidad de Poisson para k eventos."""
        if lambd <= 0:
            return 0.0
        return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

    @classmethod
    def calculate_over25_goals_probability(cls, home_lambda: float, away_lambda: float) -> float:
        """
        Calcula la probabilidad exacta de que un partido tenga 3 o más goles (Over 2.5)
        dadas las tasas de xG / goles esperados de cada equipo.
        """
        if home_lambda <= 0 or away_lambda <= 0:
            return 0.0

        # Suma de probabilidades de los marcadores con <= 2 goles:
        # (0-0, 1-0, 0-1, 1-1, 2-0, 0-2)
        under_25_prob = 0.0
        for home_goals in range(3):
            for away_goals in range(3 - home_goals):
                p_home = cls.calculate_poisson_pmf(home_goals, home_lambda)
                p_away = cls.calculate_poisson_pmf(away_goals, away_lambda)
                under_25_prob += (p_home * p_away)

        raw_over_prob = (1.0 - under_25_prob) * 100.0

        # Calibración Platt Scaling para Goles
        calibrated_prob = cls.calibrate_probability(raw_over_prob)
        return round(calibrated_prob, 2)
