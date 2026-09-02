# services/ml_engine.py
"""
Motor de Machine Learning basado en sklearn.linear_model.PoissonRegressor.

Entrena un modelo multivariado para predecir la tasa esperada de faltas (lambda)
de un jugador en un partido dado, considerando:
  - fouls_per_90:          Tasa base del jugador (faltas cometidas por 90 min)
  - opp_drawn_per_90:      Tasa de faltas recibidas/provocadas por el equipo rival
  - referee_factor:        Factor Bayesiano de rigurosidad del arbitro
  - is_home:               Condicion de local (1) o visitante (0)
  - league_avg_fouls:      Intensidad media de faltas de la competicion
  - expected_minutes_ratio: Minutos esperados / 90
"""
import os
import math
import logging
import numpy as np
import joblib
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

logger = logging.getLogger("FoulsTracker.MLEngine")

_BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = _BASE_DIR / "models_ml"
MODEL_PATH = MODEL_DIR / "poisson_regressor.joblib"
MIN_SAMPLES_FOR_ML = 30

FEATURE_NAMES = [
    "fouls_per_90",
    "opp_drawn_per_90",
    "referee_factor",
    "is_home",
    "league_avg_fouls",
    "expected_minutes_ratio",
]


class MLEngine:
    _pipeline = None
    _feature_names: List[str] = FEATURE_NAMES
    _training_samples: int = 0
    _d2_score: float = 0.0
    _trained_at: str = "Nunca"

    @classmethod
    def build_training_data(cls, db_manager, min_minutes: int = 45) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        pfs.player_id,
                        pfs.team_id,
                        pfs.minutes_played,
                        pfs.fouls_committed,
                        mf.league_id,
                        mf.season,
                        mf.referee_name,
                        mf.total_fouls,
                        mf.home_team,
                        mf.away_team,
                        COALESCE(p.fouls_per_90, 0.0) AS player_f90
                    FROM player_fixture_stats pfs
                    JOIN match_fixtures mf ON pfs.fixture_id = mf.fixture_id
                    LEFT JOIN players p
                        ON p.player_id = pfs.player_id
                        AND p.league_id = mf.league_id
                        AND p.season = mf.season
                    WHERE mf.status IN ('FT', 'AET', 'PEN')
                      AND pfs.minutes_played >= ?
                      AND pfs.fouls_committed IS NOT NULL
                """, (min_minutes,))
                rows = cursor.fetchall()

            if not rows or len(rows) < MIN_SAMPLES_FOR_ML:
                logger.info(f"Dataset insuficiente para ML: {len(rows) if rows else 0} muestras (minimo {MIN_SAMPLES_FOR_ML}).")
                return None, None

            league_avgs_raw: Dict[Tuple, list] = {}
            for r in rows:
                key = (int(r[4]), int(r[5]))
                league_avgs_raw.setdefault(key, []).append(float(r[7]) if r[7] else 0.0)

            league_avgs_mean: Dict[Tuple, float] = {k: float(np.mean(v)) for k, v in league_avgs_raw.items()}

            X_list, y_list = [], []
            for r in rows:
                minutes     = int(r[2]) if r[2] else 0
                fouls_done  = int(r[3]) if r[3] else 0
                league_id   = int(r[4])
                season      = int(r[5])
                total_fouls = float(r[7]) if r[7] else 0.0
                player_f90  = float(r[10]) if r[10] else 0.0

                league_avg = league_avgs_mean.get((league_id, season), 22.5)
                ref_factor = max(0.5, min(2.5, (total_fouls / league_avg) if league_avg > 0 else 1.0))
                minutes_ratio = min(minutes, 90) / 90.0

                if player_f90 <= 0 and minutes > 0:
                    player_f90 = (fouls_done / minutes) * 90.0

                opp_drawn_per_90 = league_avg / 90.0

                X_list.append([player_f90, opp_drawn_per_90, ref_factor, 0.0, league_avg, minutes_ratio])
                y_list.append(fouls_done)

            X = np.array(X_list, dtype=np.float64)
            y = np.array(y_list, dtype=np.float64)
            valid_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
            X, y = X[valid_mask], y[valid_mask]
            logger.info(f"Dataset ML construido: {len(X)} muestras validas de {len(rows)} registros.")
            return X, y
        except Exception as e:
            logger.error(f"Error construyendo dataset ML: {e}")
            return None, None

    @classmethod
    def train(cls, db_manager, alpha: float = 1.0, max_iter: int = 500) -> Dict[str, Any]:
        from sklearn.linear_model import PoissonRegressor
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import d2_tweedie_score
        import datetime

        X, y = cls.build_training_data(db_manager)
        if X is None:
            return {"success": False, "message": f"Datos insuficientes (minimo {MIN_SAMPLES_FOR_ML} muestras).", "n_samples": 0}

        n_samples = len(X)
        if n_samples >= 60:
            X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
        else:
            X_train, X_val, y_train, y_val = X, X, y, y

        pipeline = make_pipeline(StandardScaler(), PoissonRegressor(alpha=alpha, max_iter=max_iter, verbose=0))
        pipeline.fit(X_train, y_train)

        y_pred_val = np.clip(pipeline.predict(X_val), 1e-8, None)
        d2 = float(d2_tweedie_score(y_val, y_pred_val, power=1))

        poisson_step = pipeline.named_steps["poissonregressor"]
        scaler_step  = pipeline.named_steps["standardscaler"]
        coefs_original = poisson_step.coef_ / scaler_step.scale_
        coefficients = dict(zip(cls._feature_names, coefs_original.tolist()))
        coefficients["intercept"] = float(poisson_step.intercept_)

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, MODEL_PATH)

        trained_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cls._pipeline = pipeline
        cls._training_samples = n_samples
        cls._d2_score = round(d2, 4)
        cls._trained_at = trained_at

        logger.info(f"Modelo ML entrenado: {n_samples} muestras | D2={d2:.4f} | Guardado en {MODEL_PATH}")
        return {
            "success": True,
            "n_samples": n_samples,
            "d2_score": round(d2, 4),
            "coefficients": coefficients,
            "feature_names": cls._feature_names,
            "model_path": str(MODEL_PATH),
            "trained_at": trained_at,
        }

    @classmethod
    def load(cls) -> bool:
        if not MODEL_PATH.exists():
            logger.debug("Modelo ML no encontrado en disco. Se usara el modelo analitico.")
            return False
        try:
            cls._pipeline = joblib.load(MODEL_PATH)
            logger.info(f"Modelo ML cargado desde {MODEL_PATH}.")
            return True
        except Exception as e:
            logger.warning(f"No se pudo cargar el modelo ML: {e}")
            cls._pipeline = None
            return False

    @classmethod
    def is_ready(cls) -> bool:
        if cls._pipeline is None:
            cls.load()
        return cls._pipeline is not None

    @classmethod
    def predict_lambda(
        cls,
        fouls_per_90: float,
        opp_drawn_per_90: float,
        referee_factor: float,
        is_home: int,
        league_avg_fouls: float,
        expected_minutes: int = 85,
    ) -> Optional[float]:
        if not cls.is_ready():
            return None

        minutes_ratio = min(expected_minutes, 90) / 90.0
        X_pred = np.array([[
            fouls_per_90,
            opp_drawn_per_90,
            referee_factor,
            float(is_home),
            league_avg_fouls,
            minutes_ratio,
        ]], dtype=np.float64)

        try:
            lam = float(cls._pipeline.predict(X_pred)[0])
            return round(max(0.0, lam), 4)
        except Exception as e:
            logger.error(f"Error en MLEngine.predict_lambda: {e}")
            return None

    @classmethod
    def get_model_info(cls) -> Dict[str, Any]:
        if not MODEL_PATH.exists():
            return {"available": False, "message": "Modelo no entrenado. Usa el boton 'Entrenar Modelo ML'."}

        import datetime
        stat = MODEL_PATH.stat()
        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        info = {
            "available": True,
            "model_path": str(MODEL_PATH),
            "last_modified": mod_time,
            "n_samples": cls._training_samples,
            "d2_score": cls._d2_score,
            "trained_at": cls._trained_at if cls._trained_at != "Nunca" else mod_time,
        }
        if cls.is_ready():
            try:
                poisson_step = cls._pipeline.named_steps["poissonregressor"]
                scaler_step  = cls._pipeline.named_steps["standardscaler"]
                coefs = poisson_step.coef_ / scaler_step.scale_
                info["coefficients"] = dict(zip(FEATURE_NAMES, coefs.tolist()))
                info["intercept"] = float(poisson_step.intercept_)
            except Exception:
                pass
        return info
