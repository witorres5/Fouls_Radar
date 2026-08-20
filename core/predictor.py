"""
core/predictor.py
Motor de proyección de faltas e integración con la base de datos Turso.
"""

import logging
import math
from typing import Dict, Any, Optional

logger = logging.getLogger("FoulsTracker.Predictor")


def get_referee_from_db(db_client, referee_name: str) -> Optional[Dict[str, Any]]:
    """Consulta las métricas guardadas de un árbitro en Turso."""
    if not referee_name:
        return None
    try:
        res = db_client.execute(
            "SELECT matches_count, avg_fouls FROM referee_stats WHERE referee_name = ?",
            [referee_name]
        )
        rows = res.rows
        if rows:
            return {"matches_count": rows[0][0], "avg_fouls": rows[0][1]}
    except Exception as e:
        logger.error(f"Error consultando árbitro {referee_name} en Turso: {e}")
    return None


def calculate_match_fouls_projection(
    home_fouls_avg: float,
    away_fouls_avg: float,
    league_fouls_avg: float,
    referee_fouls_avg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calcula la proyección de faltas del partido ajustada por el factor árbitro.
    """
    base_projection = home_fouls_avg + away_fouls_avg

    if not referee_fouls_avg or league_fouls_avg == 0:
        referee_ratio = 1.0
        referee_impact = "NEUTRAL"
    else:
        referee_ratio = referee_fouls_avg / league_fouls_avg
        if referee_ratio >= 1.10:
            referee_impact = "HIGH_FOULS"
        elif referee_ratio <= 0.90:
            referee_impact = "LOW_FOULS"
        else:
            referee_impact = "NEUTRAL"

    adjusted_projection = round(base_projection * referee_ratio, 1)

    return {
        "base_projection": round(base_projection, 1),
        "adjusted_projection": adjusted_projection,
        "referee_ratio": round(referee_ratio, 2),
        "referee_impact": referee_impact
    }


def calculate_player_adjusted_rate(
    fouls_per_90: float,
    referee_ratio: float = 1.0
) -> float:
    """
    Ajusta el promedio de faltas por 90 min de un jugador según la tendencia del árbitro asignado.
    """
    return round(fouls_per_90 * referee_ratio, 2)


def prob_at_least(k: int, lambd: float) -> float:
    """
    Calcula P(X >= k) usando la distribución de Poisson para un valor medio (lambda).
    Ejemplo: prob_at_least(1, 1.8) calcula la probabilidad de realizar 1 o más faltas.
    """
    if lambd <= 0:
        return 0.0
    
    # P(X < k) = sum_i=0^{k-1} (exp(-lambda) * lambda^i / i!)
    prob_less_than_k = 0.0
    for i in range(k):
        prob_less_than_k += (math.exp(-lambd) * (lambd ** i)) / math.factorial(i)
    
    # P(X >= k) = 1 - P(X < k)
    return max(0.0, min(1.0, 1.0 - prob_less_than_k))