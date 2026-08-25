import math
from services.telegram_services import TelegramNotifier

class BettingEngine:

    @staticmethod
    def calculate_adjusted_prob(fouls_per_90: float, referee_factor: float = 1.0, threshold: float = 0.5) -> float:
        """Calcula probabilidad de Poisson ajustada por el factor de rigurosidad del árbitro."""
        if not fouls_per_90 or fouls_per_90 <= 0:
            return 0.0

        # Lambda ajustado por el árbitro
        lam = (fouls_per_90 * referee_factor)

        # P(X >= 1) = 1 - e^(-lambda)
        prob = (1.0 - math.exp(-lam)) * 100
        return round(prob, 1)

    @classmethod
    def evaluate_and_notify_fixture(cls, match_name: str, date_str: str, referee_name: str, home_player: dict, away_player: dict, referee_factor: float = 1.0):
        """Evalúa jugadores de ambos equipos y notifica a Telegram si supera el 91%."""
        
        candidates = [
            ("Local", home_player),
            ("Visitante", away_player)
        ]

        for side, player in candidates:
            p_name = player.get("name", "Desconocido")
            f90 = player.get("fouls_per_90", 0.0)
            
            prob = cls.calculate_adjusted_prob(f90, referee_factor=referee_factor, threshold=0.5)
            print("-----------PROBABILIDAD----------------",prob)
            if prob >= 91.0:
                msg = (
                    f"🚨 **¡ALERTA DE APUESTA DE ALTA PROBABILIDAD!** 🚨\n\n"
                    f"⚽ **Partido:** {match_name}\n"
                    f"📅 **Fecha:** {date_str}\n"
                    f"👤 **Árbitro:** {referee_name} (Factor: x{referee_factor:.2f})\n\n"
                    f"🏃‍♂️ **Jugador ({side}):** {p_name}\n"
                    f"📊 **Promedio F/90:** {f90}\n"
                    f"🔥 **Probabilidad (+0.5 faltas):** `{prob}%`"
                )
                TelegramNotifier.send_alert(msg)
                
    def evaluate_and_notify_high_prob(match_name: str, date_str: str, referee_name: str, referee_factor: float, player_info: dict, side: str):
        """Evalúa a un jugador y notifica a Telegram si la probabilidad ajustada es >= 91%."""
        print(player_info)
        prob = player_info.get("prob", 0.0)
        p_name = player_info.get("name", "Desconocido")
        f90 = player_info.get("fouls_per_90", 0.0)
        print("-----------PROBABILIDAD----2222------------",prob)
        if prob >= 91.0:
            alert_msg = (
                f"🚨 **¡ALERTA DE APUESTA DE ALTA PROBABILIDAD!** 🚨\n\n"
                f"⚽ **Partido:** {match_name}\n"
                f"📅 **Fecha:** {date_str}\n"
                f"👤 **Árbitro:** {referee_name} (Factor: x{referee_factor:.2f})\n\n"
                f"🏃‍♂️ **Jugador ({side}):** {p_name}\n"
                f"📊 **Promedio F/90:** {f90}\n"
                f"🔥 **Probabilidad (+0.5 faltas):** `{prob}%`"
            )
            TelegramNotifier.send_alert(alert_msg)