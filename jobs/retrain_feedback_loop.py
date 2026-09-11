# jobs/retrain_feedback_loop.py
import sys
import logging
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import joblib

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from databases.connection import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FoulsRadar.FeedbackLoop")

MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)
CALIBRATOR_PATH = MODEL_DIR / "platt_scaler.joblib"


def run_feedback_calibration():
    logger.info("🔄 Iniciando Bucle de Retroalimentación desde 'simulated_bets'...")
    db_manager = DatabaseManager()

    query = """
        SELECT probability, status 
        FROM simulated_bets 
        WHERE status IN ('GANADA', 'PERDIDA')
    """

    with db_manager.get_connection() as conn:
        df = pd.read_sql_query(query, conn)

    if len(df) < 30:
        logger.warning(f"⚠️ Muestra insuficiente ({len(df)} apuestas resueltas). Se requieren mínimo 30 para reentrenar calibración.")
        return

    # Convertir a target binario (GANADA = 1, PERDIDA = 0)
    df["target"] = (df["status"] == "GANADA").astype(int)
    
    # Transformar probabilidad a Log-Odds (Logit) para el escalador Platt
    probs = np.clip(df["probability"].values / 100.0, 1e-4, 1.0 - 1e-4)
    logits = np.log(probs / (1.0 - probs)).reshape(-1, 1)
    y = df["target"].values

    # Entrenar modelo de calibración sobre los errores cometidos
    calibrator = LogisticRegression(C=1.0, solver="lbfgs")
    calibrator.fit(logits, y)

    # Evaluar desempeño del ajuste
    calibrated_probs = calibrator.predict_proba(logits)[:, 1] * 100.0
    win_rate_real = (y.sum() / len(y)) * 100.0
    avg_pred_old = df["probability"].mean()
    avg_pred_new = calibrated_probs.mean()

    logger.info(f"📊 Apuestas analizadas: {len(df)}")
    logger.info(f"🎯 Win Rate real histórico: {win_rate_real:.2f}%")
    logger.info(f"📉 Probabilidad promedio anterior: {avg_pred_old:.2f}% -> Nueva calibrada: {avg_pred_new:.2f}%")

    # Guardar el calibrador actualizado
    joblib.dump(calibrator, CALIBRATOR_PATH)
    logger.info(f"✅ Calibrador dinámico actualizado en '{CALIBRATOR_PATH}'.")


if __name__ == "__main__":
    run_feedback_calibration()