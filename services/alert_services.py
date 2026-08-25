import math
import requests
from services.telegram_services import TelegramNotifier
from databases.betting_repository import BettingRepository


class AlertService:


    @staticmethod
    def calculate_player_over_fouls(fouls_per_90: float, referee_factor: float = 1.0, threshold: float = 0.5) -> float:
        if not fouls_per_90 or fouls_per_90 <= 0:
            return 0.0

        lam = fouls_per_90 * referee_factor
        k_floor = math.floor(threshold)
        prob_less_or_equal = sum(
            (math.exp(-lam) * (lam ** i)) / math.factorial(i) 
            for i in range(k_floor + 1)
        )
        return round((1.0 - prob_less_or_equal) * 100, 1)

    @staticmethod
    def exists_in_db(db_manager, league_id: int, season: int, match_name: str, market: str) -> bool:
        """Comprueba si la apuesta ya existe en la base de datos sin alterar BettingRepository."""
        query = """
            SELECT 1 FROM simulated_bets 
            WHERE league_id = ? 
              AND season = ? 
              AND UPPER(TRIM(match_name)) = UPPER(?) 
              AND UPPER(TRIM(market)) = UPPER(?)
            LIMIT 1;
        """
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (league_id, season, match_name.strip(), market.strip()))
                return cursor.fetchone() is not None
        except Exception:
            # Si la tabla aún no existe, retornamos False para permitir la creación inicial
            return False

    @classmethod
    def process_and_notify_fixtures(cls, upcoming_fixtures: list, top_foulers_map: dict, db_manager, league_id: int, season: int):
        """Evalúa las probabilidades, verifica existencia previa, envía a Telegram y persiste en BettingRepository."""
        for fix in upcoming_fixtures:
            fix_info = fix.get("fixture", {})
            teams = fix.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            referee = fix_info.get("referee") or "Árbitro no asignado"
            date_str = fix_info.get("date", "")

            referee_factor = 1.05 if referee != "Árbitro no asignado" else 1.00

            top_home = top_foulers_map.get(home.get("id"), {"name": "N/D", "fouls_per_90": 0.0})
            top_away = top_foulers_map.get(away.get("id"), {"name": "N/D", "fouls_per_90": 0.0})

            prob_home = cls.calculate_player_over_fouls(top_home.get("fouls_per_90", 0.0), referee_factor)
            prob_away = cls.calculate_player_over_fouls(top_away.get("fouls_per_90", 0.0), referee_factor)

            match_name = f"{home.get('name')} vs {away.get('name')}"

            candidates = [
                ("Local", top_home, prob_home),
                ("Visitante", top_away, prob_away)
            ]

            for side, player, prob in candidates:
                if prob >= 91.0:
                    p_name = player.get("name")
                    f90 = player.get("fouls_per_90", 0.0)
                    market_desc = f"{p_name} (+0.5 faltas)"

                    # 1. VALIDACIÓN ANTIDUPLICADOS PREVIA (sin tocar BettingRepository)
                    if cls.exists_in_db(db_manager, league_id, season, match_name, market_desc):
                        print(f">>> DEBUG: Apuesta para '{market_desc}' en '{match_name}' ya registrada. Omitiendo notificación.")
                        continue

                    # 2. Enviar notificación a Telegram
                    msg = (
                        f"🚨 **¡ALERTA DE APUESTA DE ALTA PROBABILIDAD!** 🚨\n\n"
                        f"⚽ **Partido:** {match_name}\n"
                        f"📅 **Fecha:** {date_str}\n"
                        f"👤 **Árbitro:** {referee} (Factor: x{referee_factor:.2f})\n\n"
                        f"🏃‍♂️ **Jugador ({side}):** {p_name}\n"
                        f"📊 **Promedio F/90:** {f90}\n"
                        f"🔥 **Probabilidad (+0.5 faltas):** `{prob}%`"
                    )
                    match_date = (date_str or "")[:10]
                    telegram_sent = TelegramNotifier.send_alert(msg)
                    betting_repo = BettingRepository(db_manager)
                    # 3. Guardar en el simulador usando tu método exactamente como está en BettingRepository
                    bet_data = {
                        "league_id": league_id,
                        "season": season,
                        "match_name": match_name,
                        "referee": referee,
                        "market": market_desc,
                        "probability": prob,
                        "simulated_odds": round(100 / prob, 2) if prob > 0 else 1.80,
                        "match_date": match_date
                    }
                    
                    saved = betting_repo.save_bet_unique(bet_data)
                    if saved and telegram_sent:
                        print(f">>> OK: Apuesta simulada guardada y notificada para {p_name}.")