# controllers/referee_controller.py
import streamlit as st
from databases.referee_repository import RefereeRepository

class RefereeController:

    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)
    def get_referees_stats(_db_manager, league_id: int, season: int):
        """Retorna estadísticas filtradas. El prefijo '_' en _db_manager ignora el hashing de caché."""
        repo = RefereeRepository(_db_manager)
        return repo.get_referees_summary_by_league(league_id, season)