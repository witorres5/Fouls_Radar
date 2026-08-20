# core/auto_bettor.py
from core.math_utils import prob_at_least
from database.data_loader import save_auto_bet, get_team_top_foulers

def process_daily_auto_bets(league_id: int, season: int, fixtures: list, filtered_df):
    """
    Evalúa los partidos del día y genera 3 apuestas por partido:
    1 Principal (Mayor valor/probabilidad) y 2 Secundarias.
    """
    top_foulers = get_team_top_foulers(league_id, season)

    for m in fixtures:
        fixture_id = m["fixture"]["id"]
        match_date = m["fixture"]["date"].split("T")[0]
        home_team = m["teams"]["home"]["name"]
        away_team = m["teams"]["away"]["name"]

        # Recopilar candidatos de ambos equipos
        candidates = []
        for team in [home_team, away_team]:
            fouler = top_foulers.get(team)
            if fouler:
                rate_per_90 = fouler["fouls_per_90"]
                # Asumimos proyección a 90 minutos
                p_1 = prob_at_least(1, rate_per_90) * 100
                p_2 = prob_at_least(2, rate_per_90) * 100
                p_3 = prob_at_least(3, rate_per_90) * 100

                candidates.append({
                    "fixture_id": fixture_id,
                    "match_date": match_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "player_name": fouler["player"],
                    "bet_line": "+0.5 Faltas (1+)",
                    "probability": p_1
                })
                candidates.append({
                    "fixture_id": fixture_id,
                    "match_date": match_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "player_name": fouler["player"],
                    "bet_line": "+1.5 Faltas (2+)",
                    "probability": p_2
                })

        # Ordenar apuestas por mayor probabilidad estimada
        candidates.sort(key=lambda x: x["probability"], reverse=True)

        # Seleccionar la top 1 (Principal) y las 2 siguientes (Secundarias)
        if len(candidates) >= 3:
            candidates[0]["tier"] = "PRINCIPAL"
            candidates[1]["tier"] = "SECUNDARIA_1"
            candidates[2]["tier"] = "SECUNDARIA_2"

            for bet in candidates[:3]:
                save_auto_bet(bet)