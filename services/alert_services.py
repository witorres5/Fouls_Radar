# services/alert_services.py
import logging
from typing import List, Dict, Any
from services.telegram_services import TelegramNotifier
from databases.betting_repository import BettingRepository
from databases.fixture_repository import FixtureRepository
from utils.betting_engine import BettingEngine

logger = logging.getLogger("FoulsTracker.AlertService")

class AlertService:

    @classmethod
    def process_and_notify_fixtures(
        cls, 
        upcoming_fixtures: list, 
        top_foulers_map: dict, 
        db_manager, 
        league_id: int, 
        season: int
    ):
        """Evalúa probabilidades con base bayesiana/Poisson, verifica duplicados y envía alertas."""
        if not upcoming_fixtures:
            return

        fixture_repo = FixtureRepository(db_manager)
        betting_repo = BettingRepository(db_manager)

        # 1. Obtener medias de la competición
        league_avg_fouls, _ = fixture_repo.get_league_averages(league_id, season)

        for fix in upcoming_fixtures:
            fix_info = fix.get("fixture", {})
            fixture_id = fix_info.get("id")
            teams = fix.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            referee = fix_info.get("referee") or "Árbitro no asignado"
            date_str = fix_info.get("date", "")
            match_date = date_str[:10] if date_str else ""

            # 2. Factor de árbitro con contracción Bayesiana sobre la base de datos
            ref_matches, ref_avg_fouls, _ = fixture_repo.get_referee_historical_stats(referee)
            referee_factor = BettingEngine.calculate_referee_factor(
                ref_avg_fouls=ref_avg_fouls,
                league_avg_fouls=league_avg_fouls,
                ref_matches_count=ref_matches,
                prior_weight=5.0
            )

            top_home = top_foulers_map.get(home.get("id"), {"name": "N/D", "fouls_per_90": 0.0})
            top_away = top_foulers_map.get(away.get("id"), {"name": "N/D", "fouls_per_90": 0.0})

            prob_home = BettingEngine.calculate_over_probability(
                metric_rate_per_90=top_home.get("fouls_per_90", 0.0),
                threshold=0.5,
                expected_minutes=85,
                adjustment_factor=referee_factor
            )
            prob_away = BettingEngine.calculate_over_probability(
                metric_rate_per_90=top_away.get("fouls_per_90", 0.0),
                threshold=0.5,
                expected_minutes=85,
                adjustment_factor=referee_factor
            )

            match_name = f"{home.get('name')} vs {away.get('name')}"

            candidates = [
                ("Local", top_home, prob_home),
                ("Visitante", top_away, prob_away)
            ]
            
            for side, player, prob in candidates:
                if prob >= 90.0:
                    p_name = player.get("name")
                    f90 = player.get("fouls_per_90", 0.0)
                    market_desc = f"{p_name} (+0.5 faltas)"

                    # 1. Validación antiduplicados delegada en el repositorio
                    if betting_repo.exists_bet(league_id, season, match_name, market_desc):
                        logger.debug(f"Apuesta '{market_desc}' en '{match_name}' ya registrada. Omitiendo.")
                        continue

                    # 2. Notificación Telegram
                    msg = (
                        f"🚨 **¡ALERTA DE APUESTA DE ALTA PROBABILIDAD!** 🚨\n\n"
                        f"⚽ **Partido:** {match_name}\n"
                        f"📅 **Fecha:** {date_str}\n"
                        f"👤 **Árbitro:** {referee} (Factor: x{referee_factor:.2f})\n\n"
                        f"🏃‍♂️ **Jugador ({side}):** {p_name}\n"
                        f"📊 **Promedio F/90:** {f90}\n"
                        f"🔥 **Probabilidad (+0.5 faltas):** `{prob}%`"
                    )
                    
                    telegram_sent = TelegramNotifier.send_alert(msg)
                    fair_odds = BettingEngine.calculate_fair_odds(prob, bookmaker_margin=0.06)

                    # 3. Guardado en repositorio
                    bet_data = {
                        "fixture_id": fixture_id,
                        "league_id": league_id,
                        "season": season,
                        "match_name": match_name,
                        "referee": referee,
                        "market": market_desc,
                        "probability": prob,
                        "simulated_odds": fair_odds,
                        "odds": fair_odds,
                        "stake": 10.0,
                        "match_date": match_date,
                        "notified_telegram": 1 if telegram_sent else 0
                    }
                    
                    saved = betting_repo.save_bet_unique(bet_data)
                    if saved:
                        logger.info(f"Apuesta simulada guardada para {p_name} ({match_name}).")
