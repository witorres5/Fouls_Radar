# services/calibration_service.py
"""
Servicio de Calibración Platt Scaling basado en resultados reales.

Entrena una LogisticRegression sobre logit(probabilidad publicada) -> resultado real
(GANADA/PERDIDA) leído de `simulated_bets`. El artefacto guardado en
`models/platt_scaler.joblib` es consumido por `BettingEngine.calibrate_probability`.

Espacio autoconsistente:
  - Entrenamiento: X = logit(probability guardada en simulated_bets) -> y = 1 si GANADA.
  - Inferencia (betting_engine): raw -> _empirical_calibration(raw) -> logit -> scaler.
  Ambos operan sobre la probabilidad 'publicada', por lo que el ajuste es directo.
"""
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

logger = logging.getLogger("FoulsTracker.CalibrationService")

BASE_DIR = Path(__file__).resolve().parent.parent
CALIBRATOR_PATH = BASE_DIR / "models" / "platt_scaler.joblib"
META_PATH = BASE_DIR / "models" / "platt_scaler_meta.json"

MIN_SAMPLES = 30

# Persistencia cruzada de artefactos de modelo en Turso/SQLite.
# Necesaria porque los runners de GitHub Actions son efímeros: el joblib
# entrenado en una corrida se pierde en la siguiente, así que se guarda
# en la base y se re-hidrata al inicio de cada sincronización.
ARTIFACT_TABLE = "model_artifacts"
ARTIFACT_KEY = "platt_scaler"


class CalibrationService:
    _calibrator = None

    # ------------------------------------------------------------------ #
    # Construcción del dataset
    # ------------------------------------------------------------------ #
    @classmethod
    def build_training_data(cls, db_manager) -> Tuple[Optional[Any], Optional[Any], int]:
        """
        Devuelve (logits, targets, n) a partir de apuestas evaluadas GANADA/PERDIDA.
        Solo filas con probability > 0 para garantizar logit finito.
        Idempotente: solo lectura de simulated_bets.
        """
        query = """
            SELECT probability, status
            FROM simulated_bets
            WHERE status IN ('GANADA', 'PERDIDA')
              AND probability IS NOT NULL
              AND probability > 0.0
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            return None, None, 0

        import numpy as np

        probs = []
        targets = []
        for probability, status in rows:
            p = float(probability)
            if p <= 0.0 or p >= 100.0:
                continue
            probs.append(p)
            targets.append(1 if (status or "").upper() == "GANADA" else 0)

        if len(probs) < MIN_SAMPLES:
            logger.info(
                f"Dataset de calibración insuficiente: {len(probs)} muestras "
                f"(mínimo {MIN_SAMPLES})."
            )
            return None, None, len(probs)

        p_array = np.clip(np.asarray(probs, dtype=np.float64) / 100.0, 1e-4, 1.0 - 1e-4)
        logits = np.log(p_array / (1.0 - p_array)).reshape(-1, 1)
        y = np.asarray(targets, dtype=np.float64)

        valid = np.isfinite(logits).all(axis=1) & np.isfinite(y)
        logits, y = logits[valid], y[valid]

        if len(np.unique(y)) < 2:
            logger.warning("El dataset de calibración no tiene ambas clases (solo ganadas o solo perdidas).")
            return None, None, len(y)

        return logits, y, len(y)

    # ------------------------------------------------------------------ #
    # Entrenamiento
    # ------------------------------------------------------------------ #
    @classmethod
    def train(cls, db_manager, C: float = 1.0, max_iter: int = 1000) -> Dict[str, Any]:
        """
        Entrena el calibrador Platt sobre resultados evaluados y lo persiste
        en models/platt_scaler.joblib (con metadatos sidecar JSON). Idempotente.
        """
        import numpy as np
        import joblib
        import datetime

        X, y, n = cls.build_training_data(db_manager)
        if X is None:
            return {
                "success": False,
                "message": (
                    f"Datos insuficientes o sin ambas clases. "
                    f"Muestras resueltas: {n} (mínimo {MIN_SAMPLES})"
                ),
                "n_samples": n,
            }

        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import brier_score_loss

        calibrator = LogisticRegression(C=C, solver="lbfgs", max_iter=max_iter)
        calibrator.fit(X, y)

        # Métricas in-sample (diagnóstico de calibración)
        calibrated_probs = calibrator.predict_proba(X)[:, 1] * 100.0
        win_rate_real = float(y.mean() * 100.0)
        # Probabilidad original recuperada desde el logit (sigmoid)
        avg_pred_old = float(np.mean(1.0 / (1.0 + np.exp(-X[:, 0])) * 100.0))
        avg_pred_new = float(np.mean(calibrated_probs))
        brier = float(brier_score_loss(y, calibrated_probs / 100.0))

        deciles = cls._calibration_curve(X[:, 0], y, calibrator)

        MODEL_DIR = CALIBRATOR_PATH.parent
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(calibrator, CALIBRATOR_PATH)

        trained_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta = {
            "n_samples": n,
            "win_rate_real": round(win_rate_real, 2),
            "avg_pred_old": round(avg_pred_old, 2),
            "avg_pred_new": round(avg_pred_new, 2),
            "brier": round(brier, 4),
            "C": C,
            "trained_at": trained_at,
            "deciles": deciles,
        }
        try:
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"No se pudo escribir metadatos de calibrador: {e}")

        cls._calibrator = calibrator

        logger.info(
            f"Calibrador Platt entrenado: {n} muestras | WinRate={win_rate_real:.2f}% | "
            f"Brier={brier:.4f} | Guardado en {CALIBRATOR_PATH}"
        )
        return {
            "success": True,
            "n_samples": n,
            "win_rate_real": round(win_rate_real, 2),
            "avg_pred_old": round(avg_pred_old, 2),
            "avg_pred_new": round(avg_pred_new, 2),
            "brier": round(brier, 4),
            "model_path": str(CALIBRATOR_PATH),
            "trained_at": trained_at,
            "deciles": deciles,
        }

    # ------------------------------------------------------------------ #
    # Métricas auxiliares
    # ------------------------------------------------------------------ #
    @staticmethod
    def _calibration_curve(logits: Any, y: Any, calibrator: Any,
                           n_bins: int = 5) -> List[Dict[str, float]]:
        """Compara probabilidad predicha (calibrada) vs win rate real por quintil."""
        import numpy as np

        preds = calibrator.predict_proba(logits.reshape(-1, 1))[:, 1] * 100.0
        bins = np.percentile(logits, np.linspace(0, 100, n_bins + 1))
        bins[-1] += 1e-6
        deciles = []
        for i in range(n_bins):
            mask = (logits >= bins[i]) & (logits < bins[i + 1])
            if mask.sum() == 0:
                continue
            deciles.append({
                "range_predicted": round(float(np.mean(preds[mask])), 1),
                "actual_win_rate": round(float(y[mask].mean() * 100.0), 1),
                "samples": int(mask.sum()),
            })
        return deciles

    @staticmethod
    def _load_saved() -> Optional[Any]:
        """Carga el calibrador desde disco si existe (soporta objeto legacy o dict)."""
        if not CALIBRATOR_PATH.exists():
            return None
        try:
            import joblib
            obj = joblib.load(CALIBRATOR_PATH)
            if isinstance(obj, dict):
                return obj.get("calibrator")
            return obj
        except Exception as e:
            logger.warning(f"No se pudo cargar calibrador Platt: {e}")
            return None

    @classmethod
    def is_ready(cls) -> bool:
        if cls._calibrator is None:
            cls._calibrator = cls._load_saved()
        return cls._calibrator is not None

    @classmethod
    def get_model_info(cls) -> Dict[str, Any]:
        """Estado del calibrador: disponible, muestras, Brier, WinRate y metadatos."""
        if not CALIBRATOR_PATH.exists():
            return {
                "available": False,
                "message": (
                    f"Calibrador Platt no entrenado. Usa 'Reentrenar Calibrador' "
                    f"(mínimo {MIN_SAMPLES} apuestas evaluadas)."
                ),
                "n_samples": 0,
            }

        import datetime
        stat = CALIBRATOR_PATH.stat()
        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        info: Dict[str, Any] = {
            "available": True,
            "model_path": str(CALIBRATOR_PATH),
            "last_modified": mod_time,
        }
        if META_PATH.exists():
            try:
                with open(META_PATH, "r", encoding="utf-8") as f:
                    info.update(json.load(f))
            except Exception:
                pass
        info.setdefault("trained_at", mod_time)
        info.setdefault("n_samples", 0)
        return info

    # ------------------------------------------------------------------ #
    # Persistencia cruzada de runs (GitHub Actions ephemeral runner)
    # ------------------------------------------------------------------ #
    @classmethod
    def persist_to_db(cls, db_manager) -> bool:
        """Sube el artefacto local (joblib + meta JSON) a Turso/SQLite.

        Idempotente: usa INSERT OR REPLACE sobre (artifact) y crea la tabla
        si no existe. Compatible con sqlite3 y libsql.
        """
        if not CALIBRATOR_PATH.exists():
            return False

        import datetime

        try:
            payload = CALIBRATOR_PATH.read_bytes()
            meta = ""
            if META_PATH.exists():
                meta = META_PATH.read_text(encoding="utf-8")
            updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ARTIFACT_TABLE} (
                        artifact TEXT PRIMARY KEY,
                        payload BLOB,
                        meta TEXT,
                        updated_at TEXT
                    )
                """)
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ARTIFACT_TABLE}
                        (artifact, payload, meta, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (ARTIFACT_KEY, payload, meta, updated_at))
            logger.info("Calibrador Platt persistido en base de datos (model_artifacts).")
            return True
        except Exception as e:
            logger.warning(f"No se pudo persistir calibrador en DB: {e}")
            return False

    @classmethod
    def load_from_db(cls, db_manager, overwrite: bool = False) -> bool:
        """Descarga el calibrador desde DB hacia models/platt_scaler.joblib.

        No sobreescribe un archivo local existente salvo `overwrite=True`.
        Así, en runners efímeros se re-hidrata el último calibrador entrenado
        antes de generar apuestas.
        """
        if not overwrite and CALIBRATOR_PATH.exists():
            return True

        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {ARTIFACT_TABLE} (
                        artifact TEXT PRIMARY KEY,
                        payload BLOB,
                        meta TEXT,
                        updated_at TEXT
                    )
                """)
                cursor.execute(
                    f"SELECT payload, meta FROM {ARTIFACT_TABLE} WHERE artifact = ?",
                    (ARTIFACT_KEY,),
                )
                row = cursor.fetchone()
        except Exception as e:
            logger.warning(f"No se pudo leer calibrador desde DB: {e}")
            return False

        if not row or not row[0]:
            return False

        try:
            CALIBRATOR_PATH.parent.mkdir(parents=True, exist_ok=True)
            CALIBRATOR_PATH.write_bytes(row[0])
            if row[1]:
                META_PATH.write_text(row[1], encoding="utf-8")
            cls._calibrator = cls._load_saved()
            logger.info("Calibrador Platt re-hidratado desde base de datos.")
            return True
        except Exception as e:
            logger.warning(f"No se pudo materializar calibrador desde DB: {e}")
            return False

    @classmethod
    def ensure_available(cls, db_manager) -> None:
        """Garantiza calibrador local (cargándolo desde DB si hace falta)."""
        if not CALIBRATOR_PATH.exists():
            cls.load_from_db(db_manager)