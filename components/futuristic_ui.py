# components/futuristic_ui.py
"""
Biblioteca de componentes y estilos visuales futuristas estilo Cyber-Quant / HUD
para Fouls Tracker Pro con soporte completo de alto contraste y legibilidad para
todos los widgets de Streamlit (selectboxes, menús flotantes, botones, tablas, radios, métricas, etc.).
"""
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from config.constants import COLOMBIA_TZ

CYBER_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --cyber-bg: #070B14;
    --cyber-surface: #0E172A;
    --cyber-card-bg: rgba(15, 23, 42, 0.88);
    --cyber-card-border: rgba(0, 245, 255, 0.28);
    --neon-cyan: #00F5FF;
    --neon-emerald: #00FFA3;
    --neon-purple: #A855F7;
    --neon-amber: #FFB800;
    --neon-red: #FF4B6E;
    --text-pure: #FFFFFF;
    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
}

/* Tipografía base y textos */
html, body, [class*="css"], .stMarkdown, p, label {
    font-family: 'Inter', -apple-system, sans-serif !important;
}

h1, h2, h3, h4, .cyber-title {
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
    color: var(--text-pure) !important;
}

.mono-text, code, .stMetric [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Fondo principal */
.stApp {
    background: radial-gradient(circle at 50% 0%, #0f1c38 0%, #070b14 80%) !important;
    background-attachment: fixed !important;
    color: var(--text-primary) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #090F1E !important;
    border-right: 1px solid rgba(0, 245, 255, 0.2) !important;
}

[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #00F5FF !important;
}

[data-testid="stSidebar"] label {
    color: #CBD5E1 !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
}

/* ==========================================================================
   MENÚ PRINCIPAL DE NAVEGACIÓN (SIDEBAR RADIO ITEMS - ALTO CONTRASTE)
   ========================================================================== */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    display: flex !important;
    flex-direction: column !important;
    gap: 8px !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background: #0E1A33 !important;
    border: 1.5px solid rgba(0, 245, 255, 0.3) !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    cursor: pointer !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35) !important;
    width: 100% !important;
    margin: 0 !important;
}

/* Todos los textos dentro de los items del menú */
[data-testid="stSidebar"] [data-testid="stRadio"] label,
[data-testid="stSidebar"] [data-testid="stRadio"] label * {
    color: #FFFFFF !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    letter-spacing: 0.01em !important;
}

/* Hover en items del menú */
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #132447 !important;
    border-color: #00FFA3 !important;
    box-shadow: 0 0 16px rgba(0, 255, 163, 0.35) !important;
    transform: translateX(4px);
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:hover * {
    color: #00FFA3 !important;
}

/* ITEM SELECCIONADO (ACTIVO) EN EL MENÚ */
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked),
[data-testid="stSidebar"] [data-testid="stRadio"] label:has([aria-checked="true"]) {
    background: linear-gradient(90deg, rgba(0, 245, 255, 0.3) 0%, rgba(168, 85, 247, 0.22) 100%) !important;
    border: 2px solid #00F5FF !important;
    box-shadow: 0 0 20px rgba(0, 245, 255, 0.4), inset 0 0 10px rgba(0, 245, 255, 0.15) !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) *,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has([aria-checked="true"]) * {
    color: #00F5FF !important;
    font-weight: 800 !important;
    font-size: 0.98rem !important;
}


/* ==========================================================================
   WIDGETS DE ENTRADA: SELECTBOX, MULTISELECT, INPUTS Y MENÚS FLOTANTES
   ========================================================================== */
/* Caja cerrada del Select */
div[data-baseweb="select"] > div {
    background-color: #0D1629 !important;
    border: 1.5px solid rgba(0, 245, 255, 0.4) !important;
    border-radius: 8px !important;
    color: #FFFFFF !important;
    min-height: 42px !important;
}

div[data-baseweb="select"]:hover > div {
    border-color: #00F5FF !important;
    box-shadow: 0 0 12px rgba(0, 245, 255, 0.3) !important;
}

/* Texto del valor seleccionado en el select */
div[data-baseweb="select"] * {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* MENÚ DESPLEGABLE FLOTANTE (POPOVER / LISTBOX) */
div[data-baseweb="popover"],
div[data-baseweb="popover"] > div,
ul[role="listbox"],
ul[data-baseweb="menu"] {
    background-color: #0A1224 !important;
    border: 1.5px solid #00F5FF !important;
    border-radius: 8px !important;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.9), 0 0 18px rgba(0, 245, 255, 0.3) !important;
    z-index: 999999 !important;
}

/* Elementos individuales de la lista (Opciones) */
li[role="option"],
li[data-baseweb="menu-item"],
div[data-baseweb="popover"] li {
    background-color: #0A1224 !important;
    color: #FFFFFF !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    cursor: pointer !important;
}

/* Forzar que todos los hijos de la opción sean legibles */
li[role="option"] *,
li[data-baseweb="menu-item"] *,
div[data-baseweb="popover"] li * {
    color: #FFFFFF !important;
    background-color: transparent !important;
    font-weight: 600 !important;
}

/* Hover y selección activa en la lista */
li[role="option"]:hover,
li[role="option"]:hover *,
li[data-baseweb="menu-item"]:hover,
li[data-baseweb="menu-item"]:hover *,
li[aria-selected="true"],
li[aria-selected="true"] * {
    background-color: #00F5FF !important;
    color: #060911 !important;
    font-weight: 800 !important;
}

/* Inputs de Texto */
div[data-baseweb="input"] > div {
    background-color: #0D1629 !important;
    border: 1.5px solid rgba(0, 245, 255, 0.35) !important;
    border-radius: 8px !important;
    color: #FFFFFF !important;
}

div[data-baseweb="input"] input {
    color: #FFFFFF !important;
    font-weight: 500 !important;
}

/* ==========================================================================
   BOTONES: ESTILO CYBERPUNK, ESTADOS DE CARGA Y DESHABILITACIÓN
   ========================================================================== */
.stButton > button {
    background: #0E223D !important;
    color: #00F5FF !important;
    border: 1.5px solid #00E5FF !important;
    border-radius: 8px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.02em !important;
    padding: 10px 18px !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4), 0 0 10px rgba(0, 245, 255, 0.15) !important;
}

.stButton > button:hover:not(:disabled) {
    background: #00F5FF !important;
    color: #060911 !important;
    border-color: #00FFA3 !important;
    box-shadow: 0 0 25px rgba(0, 245, 255, 0.6), 0 0 12px rgba(0, 255, 163, 0.4) !important;
    transform: translateY(-2px);
}

.stButton > button:active:not(:disabled) {
    transform: translateY(0);
}

/* Estado Deshabilitado / Loading (Previene clicks múltiples) */
.stButton > button:disabled,
.stButton > button[disabled],
.stButton > button[aria-disabled="true"] {
    background: #111A2E !important;
    color: #64748B !important;
    border: 1.5px solid #1E293B !important;
    cursor: not-allowed !important;
    pointer-events: none !important;
    opacity: 0.6 !important;
    box-shadow: none !important;
    transform: none !important;
}

/* Botón de Descarga */
.stDownloadButton > button {
    background: #142820 !important;
    color: #00FFA3 !important;
    border: 1.5px solid #00FFA3 !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    box-shadow: 0 0 12px rgba(0, 255, 163, 0.2) !important;
}

.stDownloadButton > button:hover {
    background: #00FFA3 !important;
    color: #060911 !important;
    box-shadow: 0 0 25px rgba(0, 255, 163, 0.5) !important;
}

/* Spinners y barras de carga */
[data-testid="stSpinner"] {
    background: rgba(0, 245, 255, 0.12) !important;
    border: 1.5px solid #00F5FF !important;
    border-radius: 8px !important;
    padding: 12px 18px !important;
    color: #00F5FF !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    box-shadow: 0 0 15px rgba(0, 245, 255, 0.2) !important;
}

[data-testid="stSpinner"] i {
    border-top-color: #00F5FF !important;
}

/* Status widget */
[data-testid="stStatusWidget"] {
    background: #0D172A !important;
    border: 1.5px solid rgba(0, 245, 255, 0.3) !important;
    border-radius: 8px !important;
    color: #FFFFFF !important;
}

/* ==========================================================================
   TABLAS Y DATAFRAMES: MÁXIMA CLARIDAD Y CONTRASTE
   ========================================================================== */
[data-testid="stDataFrame"] {
    background: #090F1E !important;
    border: 1.5px solid rgba(0, 245, 255, 0.25) !important;
    border-radius: 10px !important;
    padding: 2px !important;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5) !important;
}

table {
    width: 100% !important;
    border-collapse: collapse !important;
    background: #0A1224 !important;
    color: #F1F5F9 !important;
    border-radius: 8px !important;
}

th {
    background: #0F1C36 !important;
    color: #00F5FF !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    padding: 12px 14px !important;
    border-bottom: 2px solid rgba(0, 245, 255, 0.3) !important;
    text-align: left !important;
}

td {
    padding: 10px 14px !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    color: #E2E8F0 !important;
}

tr:hover td {
    background: rgba(0, 245, 255, 0.06) !important;
}

/* ==========================================================================
   TARJETAS KPI (METRIC CARDS)
   ========================================================================== */
div[data-testid="stMetric"] {
    background: #0D162B !important;
    border: 1.5px solid rgba(0, 245, 255, 0.25) !important;
    border-radius: 12px !important;
    padding: 18px 22px !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4) !important;
}

div[data-testid="stMetric"]:hover {
    border-color: #00F5FF !important;
    box-shadow: 0 0 25px rgba(0, 245, 255, 0.25) !important;
}

div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
    color: #94A3B8 !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-size: 1.8rem !important;
    font-weight: 800 !important;
}

/* ==========================================================================
   EXPANDERS & ALERTAS
   ========================================================================== */
details[data-testid="stExpander"] {
    background: #0A1224 !important;
    border: 1.5px solid rgba(0, 245, 255, 0.22) !important;
    border-radius: 10px !important;
    margin: 12px 0 !important;
}

details[data-testid="stExpander"] summary {
    color: #00F5FF !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
}

.stAlert {
    border-radius: 10px !important;
    border-left: 4px solid !important;
}

div[data-baseweb="notification"] {
    background: #0D172A !important;
    border: 1px solid rgba(0, 245, 255, 0.3) !important;
    color: #FFFFFF !important;
}

/* ==========================================================================
   BADGES & HUD
   ========================================================================== */
.hud-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.02em;
}

.badge-green {
    background: rgba(0, 255, 163, 0.15);
    color: #00FFA3;
    border: 1.5px solid #00FFA3;
}

.badge-cyan {
    background: rgba(0, 245, 255, 0.15);
    color: #00F5FF;
    border: 1.5px solid #00F5FF;
}

.badge-purple {
    background: rgba(168, 85, 247, 0.15);
    color: #C084FC;
    border: 1.5px solid #A855F7;
}

.badge-amber {
    background: rgba(255, 184, 0, 0.15);
    color: #FFB800;
    border: 1.5px solid #FFB800;
}

.badge-red {
    background: rgba(255, 75, 110, 0.15);
    color: #FF4B6E;
    border: 1.5px solid #FF4B6E;
}

/* Barra de progreso */
.glow-progress-bar {
    width: 100%;
    height: 10px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    overflow: hidden;
    position: relative;
    margin: 12px 0;
}

.glow-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #00F5FF 0%, #00FFA3 100%);
    border-radius: 6px;
    box-shadow: 0 0 12px rgba(0, 255, 163, 0.7);
}

/* Banner HUD */
.hud-container {
    background: #0A1326;
    border: 1.5px solid #00F5FF;
    border-radius: 12px;
    padding: 14px 22px;
    margin-bottom: 24px;
    box-shadow: 0 6px 30px rgba(0, 0, 0, 0.7), inset 0 0 20px rgba(0, 245, 255, 0.08);
}

.hud-grid {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
}

.hud-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
}

.hud-pulse {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #00FFA3;
    box-shadow: 0 0 10px #00FFA3;
    animation: pulse-glow 2s infinite;
}

@keyframes pulse-glow {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 163, 0.7); }
    70% { transform: scale(1.15); box-shadow: 0 0 0 8px rgba(0, 255, 163, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 163, 0); }
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 10px;
    background: #090F1E;
    padding: 6px;
    border-radius: 10px;
    border: 1px solid rgba(0, 245, 255, 0.2);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 6px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    color: #94A3B8 !important;
    padding: 8px 16px !important;
}

.stTabs [aria-selected="true"] {
    background: rgba(0, 245, 255, 0.2) !important;
    color: #00F5FF !important;
    border: 1.5px solid #00F5FF !important;
    box-shadow: 0 0 16px rgba(0, 245, 255, 0.25) !important;
}
</style>
"""

def inject_cyber_styles():
    """Inyecta los estilos globales Cyber-Quant en la aplicación Streamlit."""
    st.markdown(CYBER_CSS, unsafe_allow_html=True)


def render_hud_banner(db_manager, league_name: str, season: int):
    """
    Renderiza el Banner HUD Superior estilo 'Mission Control'
    con telemetría del sistema, estado de base de datos y motor ML.
    """
    from services.ml_engine import MLEngine
    ml_info = MLEngine.get_model_info()
    ml_status_text = "ML POISSON v1.0 [ONLINE]" if ml_info.get("available") else "ANALÍTICO [BAYES+POISSON]"
    ml_badge_class = "badge-purple" if ml_info.get("available") else "badge-cyan"
    
    current_time_str = datetime.now(COLOMBIA_TZ).strftime("%H:%M:%S COT")
    
    hud_html = f"""
    <div class="hud-container">
        <div class="hud-grid">
            <div class="hud-item">
                <div class="hud-pulse"></div>
                <span style="color: #94A3B8;">SISTEMA:</span>
                <span style="color: #00FFA3; font-weight: 700;">EN LÍNEA</span>
            </div>
            <div class="hud-item">
                <span style="color: #94A3B8;">MOTOR:</span>
                <span class="hud-badge {ml_badge_class}">{ml_status_text}</span>
            </div>
            <div class="hud-item">
                <span style="color: #94A3B8;">COMPETICIÓN:</span>
                <span style="color: #00F5FF; font-weight: 700;">{league_name} ({season})</span>
            </div>
            <div class="hud-item">
                <span style="color: #94A3B8;">HORA:</span>
                <span style="color: #FFFFFF; font-weight: 700;">{current_time_str}</span>
            </div>
        </div>
    </div>
    """
    st.markdown(hud_html, unsafe_allow_html=True)


def render_hologram_pick_card(
    match_name: str,
    referee: str,
    market: str,
    probability: float,
    odds: float,
    model_used: str = "🤖 ML (PoissonRegressor)"
):
    """
    Renderiza una tarjeta de pronóstico holográfica futurista con barra glow y textos de alto contraste.
    """
    prob_color = "#00FFA3" if probability >= 85 else "#00F5FF"
    badge_type = "badge-purple" if "ML" in model_used else "badge-cyan"
    
    card_html = f"""
    <div style="
        background: #0B1326;
        border: 1.5px solid rgba(0, 245, 255, 0.35);
        border-radius: 12px;
        padding: 18px 22px;
        margin-bottom: 16px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5), inset 0 0 15px rgba(0, 245, 255, 0.05);
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
            <div>
                <h4 style="margin: 0; color: #FFFFFF; font-size: 1.15rem; font-family: 'Space Grotesk', sans-serif; font-weight: 700;">
                    ⚽ {match_name}
                </h4>
                <div style="color: #94A3B8; font-size: 0.85rem; margin-top: 4px; font-family: 'JetBrains Mono', monospace;">
                    👨‍⚖️ Árbitro: <span style="color: #00F5FF; font-weight: 600;">{referee}</span>
                </div>
            </div>
            <div>
                <span class="hud-badge {badge_type}">{model_used}</span>
            </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin: 14px 0 6px 0;">
            <div style="font-size: 1.05rem; font-weight: 700; color: #FFFFFF;">
                🎯 <span style="color: #F8FAFC;">{market}</span>
            </div>
            <div style="display: flex; align-items: baseline; gap: 8px;">
                <span style="font-size: 0.82rem; color: #94A3B8; font-weight: 600;">PROBABILIDAD:</span>
                <span style="font-size: 1.35rem; font-weight: 800; color: {prob_color}; font-family: 'JetBrains Mono', monospace;">
                    {probability:.1f}%
                </span>
            </div>
        </div>

        <div class="glow-progress-bar">
            <div class="glow-progress-fill" style="width: {min(100, max(0, probability))}%;"></div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 14px;">
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.92rem; color: #94A3B8;">
                📈 Cuota Justa EV+: <span style="color: #FFB800; font-weight: 800; font-size: 1.1rem;">@{odds:.2f}</span>
            </div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def get_cyber_plotly_layout(title: str = ""):
    """Retorna un layout de Plotly configurado con tema Cyber-Dark y acentos Neón."""
    return go.Layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(family="Space Grotesk", size=16, color="#00F5FF")
        ),
        paper_bgcolor="#070B14",
        plot_bgcolor="#0A1224",
        font=dict(family="Inter, sans-serif", color="#CBD5E1"),
        xaxis=dict(
            gridcolor="rgba(0, 245, 255, 0.12)",
            zerolinecolor="rgba(0, 245, 255, 0.25)",
            showline=True,
            linecolor="rgba(0, 245, 255, 0.35)",
            tickfont=dict(family="JetBrains Mono", size=11, color="#94A3B8")
        ),
        yaxis=dict(
            gridcolor="rgba(0, 245, 255, 0.12)",
            zerolinecolor="rgba(0, 245, 255, 0.25)",
            showline=True,
            linecolor="rgba(0, 245, 255, 0.35)",
            tickfont=dict(family="JetBrains Mono", size=11, color="#94A3B8")
        ),
        margin=dict(l=45, r=45, t=60, b=45),
        legend=dict(
            bgcolor="#0A1224",
            bordercolor="rgba(0, 245, 255, 0.3)",
            borderwidth=1,
            font=dict(family="Space Grotesk", color="#F1F5F9")
        )
    )
