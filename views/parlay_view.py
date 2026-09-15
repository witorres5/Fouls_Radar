# views/parlay_view.py
import streamlit as st
from datetime import datetime
from databases.fixture_repository import FixtureRepository
from services.parlay_service import ParlayService

def render_daily_parlay_tab(db_manager, selected_league_id: int):
    st.header("🎯 Combinada Diaria del Día (Max 3 Selecciones)")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if st.button("⚡ Generar Parlay de la Liga", use_container_width=True):
        repo = FixtureRepository(db_manager)
        picks = repo.get_top_daily_picks_by_league(selected_league_id, today_str, limit=3)
        
        parlay = ParlayService.build_daily_league_parlay(picks)
        
        if not parlay:
            st.warning("⚠️ No hay suficientes partidos hoy que superen el umbral mínimo de valor (65% calibrado).")
            return

        st.success(f" Parlay Generado — {parlay['legs_count']} Selecciones")
        
        for idx, leg in enumerate(parlay["legs"], 1):
            st.markdown(f"**Leg {idx}:** {leg['match']} | `{leg['selection']}` — Prob: **{leg['individual_prob']}%** (@{leg['fair_odds']})")
            
        st.divider()
        col1, col2, col3 = st.columns(3)
        col1.metric("Probabilidad Conjunta", f"{parlay['combined_probability_pct']}%")
        col2.metric("Cuota Total Sugerida", f"@{parlay['combined_fair_odds']}")
        col3.metric("Estado EV", parlay["expected_value_flag"])
