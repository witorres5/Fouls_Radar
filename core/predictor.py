"""
core/predictor.py
Motor de proyección de faltas e integración con la base de datos Turso.
"""

import logging
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
    Calcula la proyección de faltas ajustada por el factor árbitro.
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