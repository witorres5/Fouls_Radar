# scripts/train_platt_calibrator.py
"""
Script CLI para entrenamiento del calibrador Platt (Platt Scaling).

Entrena una LogisticRegression sobre logit(probabilidad publicada) vs resultado
real (GANADA/PERDIDA) de `simulated_bets` y guarda `models/platt_scaler.joblib`.

Uso:  py scripts/train_platt_calibrator.py [--c 1.0] [--max-iter 1000]
"""
import sys
import argparse
import logging

BASE_DIR = r"e:\Personal\proyectos\Predicciones"
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("train_platt_calibrator")

def main():
    parser = argparse.ArgumentParser(description="Entrenar calibrador Platt (LogisticRegression).")
    parser.add_argument("--c", type=float, default=1.0, help="Regularizacion C (default: 1.0)")
    parser.add_argument("--max-iter", type=int, default=1000, help="Max iteraciones LBFGS (default: 1000)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" ENTRENAMIENTO CALIBRADOR PLATT (Platt Scaling)")
    logger.info("=" * 60)

    try:
        from databases.connection import DatabaseManager
        from services.calibration_service import CalibrationService, MIN_SAMPLES

        db = DatabaseManager()
        logger.info("Conexion a base de datos establecida.")

        # Diagnosticar dataset disponible (sin entrenar)
        _, _, n_available = CalibrationService.build_training_data(db)
        logger.info(f"Muestras resueltas disponibles: {n_available} (minimo {MIN_SAMPLES})")

        if n_available < MIN_SAMPLES:
            logger.warning(
                f"Solo {n_available} apuestas evaluadas. Se necesitan al menos {MIN_SAMPLES}. "
                "Sincroniza partidos jugados o evalúa apuestas pendientes primero."
            )
            sys.exit(1)

        logger.info(f"Entrenando con C={args.c}, max_iter={args.max_iter}...")
        result = CalibrationService.train(db, C=args.c, max_iter=args.max_iter)

        if not result["success"]:
            logger.error(f"Entrenamiento fallido: {result.get('message', 'Error desconocido')}")
            sys.exit(1)

        logger.info("")
        logger.info("=== RESULTADOS ===")
        logger.info(f"  Muestras usadas:       {result['n_samples']}")
        logger.info(f"  Win Rate real:         {result['win_rate_real']:.2f}%")
        logger.info(f"  Prob. promedio antes:  {result['avg_pred_old']:.2f}%")
        logger.info(f"  Prob. promedio nueva:  {result['avg_pred_new']:.2f}%")
        logger.info(f"  Brier Score:           {result['brier']:.4f}")
        logger.info(f"  Modelo guardado en:    {result['model_path']}")
        logger.info(f"  Entrenado a:           {result['trained_at']}")
        logger.info("")
        logger.info("=== CALIBRACION POR QUINTIL (predicho vs real) ===")
        for d in result.get("deciles", []):
            logger.info(
                f"  p~{d['range_predicted']:>6.1f}%  ->  win rate real {d['actual_win_rate']:>5.1f}%  (n={d['samples']})"
            )
        logger.info("")
        logger.info("Calibrador listo. Las probabilidades publicadas usaran el modelo.")

    except Exception as e:
        logger.error(f"Error critico durante el entrenamiento: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()