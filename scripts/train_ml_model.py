# scripts/train_ml_model.py
"""
Script CLI para entrenamiento del modelo PoissonRegressor.
Uso:  py scripts/train_ml_model.py [--alpha 1.0] [--max-iter 500]
"""
import sys
import argparse
import logging

sys.path.insert(0, r"e:\Personal\proyectos\Predicciones")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("train_ml_model")

def main():
    parser = argparse.ArgumentParser(description="Entrenar PoissonRegressor para prediccion de faltas.")
    parser.add_argument("--alpha", type=float, default=1.0, help="Regularizacion L2 (default: 1.0)")
    parser.add_argument("--max-iter", type=int, default=500, help="Max iteraciones LBFGS (default: 500)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" ENTRENAMIENTO MODELO ML - PoissonRegressor (Scikit-Learn)")
    logger.info("=" * 60)

    try:
        from databases.connection import DatabaseManager
        from services.ml_engine import MLEngine

        db = DatabaseManager()
        logger.info("Conexion a base de datos establecida.")

        # Verificar cantidad de datos disponibles
        from databases.fixture_repository import FixtureRepository
        fixture_repo = FixtureRepository(db)
        n_available = fixture_repo.get_training_dataset_size(min_minutes=45)
        logger.info(f"Muestras disponibles (>=45 min): {n_available}")

        if n_available < 30:
            logger.warning(
                f"Solo {n_available} muestras disponibles. Se necesitan al menos 30. "
                "Sincroniza mas partidos de temporada completa primero."
            )
            sys.exit(1)

        # Entrenar
        logger.info(f"Entrenando con alpha={args.alpha}, max_iter={args.max_iter}...")
        result = MLEngine.train(db, alpha=args.alpha, max_iter=args.max_iter)

        if not result["success"]:
            logger.error(f"Entrenamiento fallido: {result.get('message', 'Error desconocido')}")
            sys.exit(1)

        logger.info("")
        logger.info("=== RESULTADOS ===")
        logger.info(f"  Muestras usadas:    {result['n_samples']}")
        logger.info(f"  D2 Score (Poisson): {result['d2_score']:.4f}  (1.0 = perfecto, >0.1 = util)")
        logger.info(f"  Modelo guardado en: {result['model_path']}")
        logger.info(f"  Entrenado a:        {result['trained_at']}")
        logger.info("")
        logger.info("=== COEFICIENTES DEL MODELO (escala original) ===")
        coefs = result.get("coefficients", {})
        for feat, coef in coefs.items():
            direction = "+" if coef >= 0 else "-"
            logger.info(f"  {feat:<30} {direction}{abs(coef):.4f}")
        logger.info("")
        logger.info("Modelo listo. Los picks del sistema usaran ML automaticamente.")

    except Exception as e:
        logger.error(f"Error critico durante el entrenamiento: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
