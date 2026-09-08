# services/match_analysis_service.py
import scipy.stats as stats
from databases.feature_repository import FeatureRepository

class MatchAnalysisService:
    def __init__(self, feature_repo: FeatureRepository, referee_repo=None):
        self.feature_repo = feature_repo
        self.referee_repo = referee_repo

    def analyze_fixture(self, fixture_id: int, home_team_id: int, away_team_id: int, season: int, referee_name: str = None) -> dict:
        # 1. Recuperar promedios recientes proyectados con Spark
        home_proj = self.feature_repo.get_team_avg_fouls_l5(home_team_id, season)
        away_proj = self.feature_repo.get_team_avg_fouls_l5(away_team_id, season)
        
        # 2. Promedio base acumulado (Lambda de Poisson)
        total_lambda = home_proj + away_proj

        # 3. Ajuste por sesgo de árbitro usando get_referee_historical_stats
        referee_bias = 0.0
        if self.referee_repo and referee_name and referee_name != "Árbitro no asignado":
            try:
                _, ref_avg, _ = self.referee_repo.get_referee_historical_stats(referee_name)
                if ref_avg and ref_avg > 0:
                    referee_bias = (ref_avg - 24.0) / 24.0
                    total_lambda *= (1.0 + referee_bias)
            except Exception:
                pass

        # 4. Encontrar línea con probabilidad acumulada >= 85%
        safe_line = 10
        top_prob = 0.0
        for line in range(12, 35):
            prob_over = (1.0 - stats.poisson.cdf(line - 1, total_lambda)) * 100.0
            if prob_over >= 85.0:
                safe_line = line
                top_prob = prob_over
            else:
                break

        # 5. Obtener infractores clave (Top Duelos)
        home_top = self.feature_repo.get_team_top_foulers(home_team_id, season, limit=2)
        away_top = self.feature_repo.get_team_top_foulers(away_team_id, season, limit=2)

        return {
            "expected_fouls": round(total_lambda, 1),
            "referee_bias_pct": round(referee_bias * 100.0, 1),
            "safe_line": safe_line,
            "line_probability": round(top_prob, 1),
            "recommended_market": f"Más de {safe_line - 0.5} Faltas Totales",
            "min_odd": round(1.0 / (top_prob / 100.0), 2) if top_prob > 0 else 1.01,
            "home_top_foulers": home_top,
            "away_top_foulers": away_top
        }