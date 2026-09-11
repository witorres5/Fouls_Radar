# services/alert_services.py
import logging
from typing import List, Dict, Any, Set
from services.telegram_services import TelegramNotifier
from databases.betting_repository import BettingRepository
from databases.fixture_repository import FixtureRepository
from utils.betting_engine import BettingEngine

logger = logging.getLogger("FoulsTracker.AlertService")

class AlertService:

    # Whitelist de ligas con rendimiento positivo verificado
    # 239: Liga BetPlay (Colombia), 140: LaLiga2 (España), 39: Premier League, 73: Copas / Ligas Secundarias, 88: Eredivisie, 135: Serie A
    ALLOWED_LEAGUES_FOR_ALERTS: Set[int] = {239, 140, 39, 73, 88, 135}

    @classmethod
    def process_and_notify_fixtures(
        cls, 
        upcoming_fixtures: list, 
        top_foulers_map: dict, 
        db_manager, 
        league_id: int, 
        season: int
    ):
        """
        Evalúa probabilidades calibradas con base bayesiana/Poisson, aplica filtro de ligas y cuota mínima (>=1.50),
        verifica duplicados y notifica/guarda alertas simuladas.
        """
        if not upcoming_fixtures:
            return

        # 1. Filtro de Liga: Omitir ligas con alta varianza o ROI negativo no incluidas en la whitelist
        if league_id not in cls.ALLOWED_LEAGUES_FOR_ALERTS:
            logger.debug(f"Liga {league_id} fuera de la lista de ligas autorizadas para alertas. Omitiendo.")
            return

        fixture_repo = FixtureRepository(db_manager)
        betting_repo = BettingRepository(db_manager)

        # 2. Obtener medias de la competición
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

            # Factor de árbitro con contracción Bayesiana sobre la base de datos
            ref_matches, ref_avg_fouls, _ = fixture_repo.get_referee_historical_stats(referee)
            referee_factor = BettingEngine.calculate_referee_factor(
                ref_avg_fouls=ref_avg_fouls,
                league_avg_fouls=league_avg_fouls,
                ref_matches_count=ref_matches,
                prior_weight=5.0
            )

            top_home = top_foulers_map.get(home.get("id"), {"name": "N/D", "fouls_per_90": 0.0})
            top_away = top_foulers_map.get(away.get("id"), {"name": "N/D", "fouls_per_90": 0.0})

            # Las probabilidades devueltas ya vienen calibradas empíricamente desde el BettingEngine
            prob_home = BettingEngine.calculate_over_probability(
                metric_rate_per_90=top_home.get("fouls_per_90", 0.0),
                threshold=0.5,
                expected_minutes=85,
                adjustment_factor=referee_factor,
                apply_calibration=True
            )
            prob_away = BettingEngine.calculate_over_probability(
                metric_rate_per_90=top_away.get("fouls_per_90", 0.0),
                threshold=0.5,
                expected_minutes=85,
                adjustment_factor=referee_factor,
                apply_calibration=True
            )

            match_name = f"{home.get('name')} vs {away.get('name')}"

            candidates = [
                ("Local", top_home, prob_home),
                ("Visitante", top_away, prob_away)
            ]
            
            for side, player, prob in candidates:
                # Al estar calibrada la probabilidad, una probabilidad >= 65.0% representa
                # un jugador top de alto valor (equivalente a >90% sin calibrar)
                if prob >= 65.0:
                    p_name = player.get("name")
                    f90 = player.get("fouls_per_90", 0.0)
                    market_desc = f"{p_name} (+0.5 faltas)"

                    # Calcular cuotas simuladas con el piso estricto (MIN_ODDS = 1.50)
                    fair_odds = BettingEngine.calculate_fair_odds(prob, bookmaker_margin=0.06)

                    # 3. Piso de Cuota: Descartar si no cumple la cuota mínima de valor (>= 1.50)
                    if fair_odds < BettingEngine.MIN_ODDS:
                        logger.debug(f"Cuota {fair_odds} para '{market_desc}' inferior a {BettingEngine.MIN_ODDS}. Omitiendo.")
                        continue

                    # 4. Validación antiduplicados delegada en el repositorio
                    if betting_repo.exists_bet(league_id, season, match_name, market_desc):
                        logger.debug(f"Apuesta '{market_desc}' en '{match_name}' ya registrada. Omitiendo.")
                        continue

                    # 5. Notificación Telegram
                    msg = (
                        f"🚨 **¡ALERTA DE APUESTA DE ALTA PROBABILIDAD!** 🚨\n\n"
                        f"⚽ **Partido:** {match_name}\n"
                        f"📅 **Fecha:** {date_str}\n"
                        f"👤 **Árbitro:** {referee} (Factor: x{referee_factor:.2f})\n\n"
                        f"🏃‍♂️ **Jugador ({side}):** {p_name}\n"
                        f"📊 **Promedio F/90:** {f90}\n"
                        f"🔥 **Probabilidad Calibrada (+0.5 faltas):** `{prob}%`\n"
                        f"💡 **Cuota Mínima Sugerida:** `@{fair_odds}`"
                    )
                    
                    telegram_sent = TelegramNotifier.send_alert(msg)

                    # 6. Guardado en repositorio
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
                        logger.info(f"Apuesta simulada guardada para {p_name} ({match_name}) | Odds @{fair_odds}.")