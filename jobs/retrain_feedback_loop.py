# jobs/retrain_feedback_loop.py
"""
Bucle de Retroalimentación: reentrena el calibrador Platt (Platt Scaling) con
los resultados reales de `simulated_bets` (GANADA/PERDIDA).

Delega toda la lógica en `services/calibration_service.CalibrationService`;
este archivo queda como punto de entrada para cron / tareas programadas.

Uso:  py jobs/retrain_feedback_loop.py [--c 1.0] [--min-samples 30]
"""
import sys
import argparse
import logging

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from databases.connection import DatabaseManager
from services.calibration_service import CalibrationService, MIN_SAMPLES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FoulsRadar.FeedbackLoop")


def run_feedback_calibration(C: float = 1.0, min_samples: int = MIN_SAMPLES):
    logger.info("🔄 Iniciando Bucle de Retroalimentación desde 'simulated_bets'...")
    db_manager = DatabaseManager()

    result = CalibrationService.train(db_manager, C=C)

    if not result["success"]:
        logger.warning(
            f"⚠️ {result.get('message', 'No se pudo reentrenar la calibración.')} "
            f"Se requieren mínimo {min_samples} apuestas resueltas."
        )
        return result

    logger.info("📊 Apuestas analizadas: %d", result["n_samples"])
    logger.info("🎯 Win Rate real histórico: %.2f%%", result["win_rate_real"])
    logger.info("📉 Prob. promedio anterior: %.2f%% -> Nueva calibrada: %.2f%%",
                result["avg_pred_old"], result["avg_pred_new"])
    logger.info("🎯 Brier Score: %.4f (más cercano a 0 = mejor)", result["brier"])
    logger.info("✅ Calibrador dinámico actualizado en '%s'.", result["model_path"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reentrenar calibrador Platt.")
    parser.add_argument("--c", type=float, default=1.0, help="Regularización C (default: 1.0)")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES, help="Muestras mínimas (default: 30)")
    args = parser.parse_args()
    run_feedback_calibration(C=args.c, min_samples=args.min_samples)