from dataclasses import dataclass
from typing import Optional

@dataclass
class PlayerFoulStats:
    player_id: int
    player_name: str
    team_id: int
    team_name: str
    league_id: int
    season: int
    minutes_played: int
    fouls_committed: int
    fouls_drawn: int
    yellow_cards: int
    red_cards: int
    
    @property
    def fouls_per_90(self) -> float:
        """Calcula el promedio de faltas cometidas por cada 90 minutos jugados."""
        if self.minutes_played <= 0:
            return 0.0
        return round((self.fouls_committed / self.minutes_played) * 90, 2)