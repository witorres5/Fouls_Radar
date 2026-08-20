"""
main.py
Pipeline principal de extracción y almacenamiento de métricas disciplinarias.
Procesa las ligas configuradas a través de múltiples temporadas
de forma ultrarrápida usando concurrencia y persiste los datos en SQLite/Turso y CSV.
"""

import os
import csv
import time
import logging
import libsql
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Tuple, Dict, Any
from datetime import datetime, timezone

from config.constants import TARGET_LEAGUES
from core.api_client import APIFootballClient
from core.foul_extractor import parse_player_fouls
from models.foul_stats import PlayerFoulStats

# Configuración de Logs
logger = logging.getLogger("FoulsTracker.Main")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


# --- GESTOR DE BASE DE DATOS (TURSO / LIBSQL) ---
class DatabaseManager:
    def __init__(self):
        try:
            import streamlit as st
            self.turso_url = st.secrets.get("TURSO_DATABASE_URL") or os.getenv("TURSO_DATABASE_URL")
            self.turso_token = st.secrets.get("TURSO_AUTH_TOKEN") or os.getenv("TURSO_AUTH_TOKEN")
        except Exception:
            self.turso_url = os.getenv("TURSO_DATABASE_URL")
            self.turso_token = os.getenv("TURSO_AUTH_TOKEN")

        self._init_db()

    def _get_connection(self):
        if self.turso_url and self.turso_token:
            conn = libsql.connect(database=self.turso_url, auth_token=self.turso_token)
        else:
            conn = libsql.connect("fouls_tracker.db")
            
        # Optimización de transacciones masivas
        try:
            conn.execute("PRAGMA synchronous = OFF;")
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            pass
                
        return conn

    def _init_db(self):
        """Crea las tablas e índices optimizados si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Tabla: Estadísticas de Jugadores
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_foul_stats (
                    id TEXT PRIMARY KEY,
                    player_id INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    team_id INTEGER NOT NULL,
                    team_name TEXT NOT NULL,
                    league_id INTEGER NOT NULL,
                    league_name TEXT NOT NULL,
                    season INTEGER NOT NULL,
                    minutes_played INTEGER DEFAULT 0,
                    fouls_committed INTEGER DEFAULT 0,
                    fouls_drawn INTEGER DEFAULT 0,
                    yellow_cards INTEGER DEFAULT 0,
                    red_cards INTEGER DEFAULT 0,
                    fouls_per_90 REAL DEFAULT 0.0,
                    updated_at TEXT
                )
            """)
            
            # 2. Tabla: Historial de Partidos / Árbitros
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS match_fixtures (
                    fixture_id INTEGER PRIMARY KEY,
                    season INTEGER,
                    league_id INTEGER,
                    match_date TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    referee_name TEXT,
                    status TEXT DEFAULT 'FT',
                    total_fouls INTEGER DEFAULT 0,
                    total_yellow_cards INTEGER DEFAULT 0
                )
            """)

            # 3. Tabla: Historial de Árbitros (Acumulado)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referee_stats (
                    referee_name TEXT PRIMARY KEY,
                    matches_count INTEGER DEFAULT 0,
                    total_fouls INTEGER DEFAULT 0,
                    total_yellows INTEGER DEFAULT 0,
                    total_reds INTEGER DEFAULT 0,
                    avg_fouls REAL DEFAULT 0.0,
                    updated_at TEXT
                )
            """)

            # 4. Tabla: Simulador de Apuestas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER,
                    match_date TEXT,
                    league_id INTEGER,
                    home_team TEXT,
                    away_team TEXT,
                    referee_name TEXT,
                    predicted_fouls REAL,
                    bet_line REAL,
                    bet_type TEXT,
                    edge REAL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(fixture_id, bet_type, bet_line)
                )
            """)

            # Índices de alto rendimiento para eliminar latencia en Turso
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_fixtures_league_season ON match_fixtures(league_id, season, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_fixtures_referee ON match_fixtures(referee_name)")

            conn.commit()

    def get_completed_fixture_ids(self, league_id: int, season: int) -> set:
        """Obtiene los IDs de partidos que ya están procesados en BD."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT fixture_id FROM match_fixtures WHERE league_id = ? AND season = ? AND status = 'FT'",
                    (league_id, season)
                )
                rows = cursor.fetchall()
                return {row[0] for row in rows}
        except Exception as e:
            logger.error(f"Error consultando partidos procesados: {e}")
            return set()

    def save_completed_fixtures(self, fixtures: list) -> int:
        """Guarda o actualiza el historial de partidos finalizados y sus árbitros."""
        if not fixtures:
            return 0

        data_to_insert = []
        for f in fixtures:
            ref = f.get("referee_name")
            if not ref or str(ref).strip() in ["", "Por definir", "None", "null"]:
                clean_ref = "Sin Árbitro Registrado"
            else:
                clean_ref = ref

            data_to_insert.append((
                f.get("fixture_id"),
                f.get("season"),
                f.get("league_id"),
                clean_ref,
                f.get("total_fouls", 0),
                f.get("total_yellow_cards", 0),
                'FT'
            ))

        query = """
            INSERT INTO match_fixtures (fixture_id, season, league_id, referee_name, total_fouls, total_yellow_cards, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                referee_name = excluded.referee_name,
                total_fouls = excluded.total_fouls,
                total_yellow_cards = excluded.total_yellow_cards,
                status = excluded.status
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, data_to_insert)
                conn.commit()
            return len(fixtures)
        except Exception as e:
            logger.error(f"Error guardando partidos finalizados en BD: {e}")
            return 0

    def save_foul_records(self, records: List[PlayerFoulStats], league_name: str, batch_size: int = 100):
        """Inserta registros de jugadores divididos en micro-lotes para evitar freeze con Turso."""
        if not records:
            return

        now = datetime.now(timezone.utc).isoformat()
        
        query = """
            INSERT INTO player_foul_stats (
                id, player_id, player_name, team_id, team_name, league_id, league_name,
                season, minutes_played, fouls_committed, fouls_drawn, yellow_cards,
                red_cards, fouls_per_90, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                player_name=excluded.player_name,
                team_id=excluded.team_id,
                team_name=excluded.team_name,
                minutes_played=excluded.minutes_played,
                fouls_committed=excluded.fouls_committed,
                fouls_drawn=excluded.fouls_drawn,
                yellow_cards=excluded.yellow_cards,
                red_cards=excluded.red_cards,
                fouls_per_90=excluded.fouls_per_90,
                updated_at=excluded.updated_at
        """

        data_to_insert = [
            (
                f"{rec.player_id}_{rec.league_id}_{rec.season}",
                rec.player_id,
                rec.player_name,
                rec.team_id,
                rec.team_name,
                rec.league_id,
                league_name,
                rec.season,
                rec.minutes_played,
                rec.fouls_committed,
                rec.fouls_drawn,
                rec.yellow_cards,
                rec.red_cards,
                rec.fouls_per_90,
                now
            )
            for rec in records
        ]

        total_records = len(data_to_insert)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for i in range(0, total_records, batch_size):
                    chunk = data_to_insert[i:i + batch_size]
                    cursor.executemany(query, chunk)
                    conn.commit()
            logger.info(f"[{league_name}] Guardados exitosamente {total_records} registros en BD.")
        except Exception as e:
            logger.error(f"Error guardando registros de faltas en BD ({league_name}): {e}")

    def update_referee_stats(self):
        """Agrega los partidos por árbitro y actualiza la tabla referee_stats sin descarte rígido."""
        query = """
            INSERT INTO referee_stats (
                referee_name, 
                matches_count, 
                total_fouls, 
                total_yellows, 
                avg_fouls, 
                updated_at
            )
            SELECT 
                referee_name,
                COUNT(*) as matches_count,
                SUM(total_fouls) as total_fouls,
                SUM(total_yellow_cards) as total_yellows,
                ROUND(AVG(total_fouls), 2) as avg_fouls,
                datetime('now') as updated_at
            FROM match_fixtures
            WHERE referee_name IS NOT NULL 
              AND referee_name NOT IN ('', 'Sin Árbitro Registrado', 'Por definir')
            GROUP BY referee_name
            ON CONFLICT(referee_name) DO UPDATE SET
                matches_count = excluded.matches_count,
                total_fouls = excluded.total_fouls,
                total_yellows = excluded.total_yellows,
                avg_fouls = excluded.avg_fouls,
                updated_at = excluded.updated_at
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                conn.commit()
            logger.info("Tabla referee_stats actualizada correctamente.")
        except Exception as e:
            logger.error(f"Error actualizando estadísticas de árbitros: {e}")


# --- EXPORTADOR A CSV ---
def export_to_csv(records: List[PlayerFoulStats], league_name: str, season: int, output_dir: str = "exports"):
    """Exporta los registros procesados a un archivo CSV."""
    if not records:
        return
    os.makedirs(output_dir, exist_ok=True)
    league_slug = league_name.lower().replace(' ', '_')
    filename = os.path.join(output_dir, f"fouls_{league_slug}_{season}.csv")
    
    headers = [
        "player_id", "player_name", "team_id", "team_name", "league_id",
        "season", "minutes_played", "fouls_committed", "fouls_drawn",
        "yellow_cards", "red_cards", "fouls_per_90"
    ]
    
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in records:
            writer.writerow([
                r.player_id, r.player_name, r.team_id, r.team_name, r.league_id,
                r.season, r.minutes_played, r.fouls_committed, r.fouls_drawn,
                r.yellow_cards, r.red_cards, r.fouls_per_90
            ])


# --- EXTRACTOR DE LIGA (SOLO EXTRACCIÓN Y PARSEO, SIN I/O A BD) ---
def fetch_league_data(league_id: int, info: dict, season: int, existing_fixture_ids: set, incremental: bool = True) -> Tuple[List[PlayerFoulStats], List[dict], str]:
    """Realiza la llamada HTTP y parseo de datos. No interactúa con la BD para ser 100% thread-safe."""
    client = APIFootballClient()
    league_name = info["name"]

    # 1. Jugadores (Estadísticas acumuladas de la temporada)
    raw_data = client.get_player_season_fouls(league_id=league_id, season=season)
    foul_records = parse_player_fouls(raw_data, league_id=league_id, season=season) or []
    logger.info(f"[{league_name}] Parseados {len(foul_records)} jugadores. Consultando partidos...")

    # 2. Partidos Finalizados
    if incremental and existing_fixture_ids:
        completed_fixtures = client.get_completed_fixtures_delta(league_id=league_id, season=season, days_back=7)
    else:
        completed_fixtures = client.get_completed_fixtures(league_id=league_id, season=season) or []

    # Filtrar partidos no procesados
    new_fixtures = [f for f in completed_fixtures if f.get("fixture", {}).get("id") not in existing_fixture_ids]
    
    fixture_records = []
    for f in new_fixtures:
        try:
            fixture_data = f.get("fixture", {})
            referee_raw = fixture_data.get("referee")
            
            if referee_raw and str(referee_raw).strip() not in ["None", "null", "", "Por definir"]:
                clean_referee = referee_raw.split(",")[0].split("-")[0].strip()
            else:
                clean_referee = "Sin Árbitro Registrado"

            teams_events = f.get("events", []) or []
            yellows_count = sum(1 for e in teams_events if e.get("type") == "Card" and "Yellow" in str(e.get("detail", "")))
            
            stats = f.get("statistics", []) or []
            total_fouls = 0
            if stats:
                for team_stat in stats:
                    for stat_item in team_stat.get("statistics", []) or []:
                        if stat_item.get("type") == "Fouls" and stat_item.get("value"):
                            total_fouls += int(stat_item.get("value"))

            fixture_records.append({
                "fixture_id": fixture_data.get("id"),
                "season": season,
                "league_id": league_id,
                "referee_name": clean_referee,
                "total_fouls": total_fouls,
                "total_yellow_cards": yellows_count
            })
        except Exception as err:
            logger.error(f"Error procesando fixture individual en {league_name}: {err}")
            continue

    logger.info(f"[{league_name}] Extracción finalizada con éxito.")
    return foul_records, fixture_records, league_name


# --- FUNCIÓN DE SINCRONIZACIÓN INDIVIDUAL (COMPATIBILIDAD CON APP.PY) ---
def sync_league_data(league_id: int, league_name: str, season: int) -> int:
    """Sincroniza una sola liga de forma síncrona."""
    db = DatabaseManager()
    existing_ids = db.get_completed_fixture_ids(league_id, season)
    info = TARGET_LEAGUES.get(league_id, {"name": league_name})
    
    foul_records, fixture_records, _ = fetch_league_data(league_id, info, season, existing_ids)

    if foul_records:
        db.save_foul_records(foul_records, league_name)
        export_to_csv(foul_records, league_name, season)

    if fixture_records:
        db.save_completed_fixtures(fixture_records)
        db.update_referee_stats()

    return len(foul_records)


# --- PIPELINE PRINCIPAL MULTITHREADED ---
def run_pipeline(seasons: Union[int, List[int]] = 2026, max_workers: int = 5, export_csv: bool = True):
    """Ejecuta la extracción multihilo optimizada y persiste por lotes en BD."""
    if isinstance(seasons, int):
        seasons = [seasons]

    db = DatabaseManager()
    start_time = time.time()
    logger.info(f"=== INICIANDO PIPELINE OPTIMIZADO ({max_workers} WORKERS) PARA TEMPORADAS: {seasons} ===")

    total_processed_global = 0

    for season in seasons:
        logger.info(f"\n==================================================")
        logger.info(f"    PROCESANDO TEMPORADA: {season}")
        logger.info(f"==================================================")

        all_fouls_season = []
        all_fixtures_season = []

        # Consulta secuencial de IDs para no saturar la conexión a Turso
        logger.info("Obteniendo historial de partidos previamente procesados...")
        existing_ids_map = {}
        for league_id in TARGET_LEAGUES.keys():
            existing_ids_map[league_id] = db.get_completed_fixture_ids(league_id, season)

        # Extracción en paralelo (solo llamadas HTTP de API)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_league = {
                executor.submit(
                    fetch_league_data, 
                    league_id, 
                    info, 
                    season, 
                    existing_ids_map.get(league_id, set())
                ): info["name"]
                for league_id, info in TARGET_LEAGUES.items()
            }

            for future in as_completed(future_to_league):
                league_name = future_to_league[future]
                try:
                    foul_records, fixture_records, _ = future.result()
                    
                    if foul_records:
                        logger.info(f"Procesando inserción de {len(foul_records)} jugadores para {league_name}...")
                        db.save_foul_records(foul_records, league_name)
                        if export_csv:
                            export_to_csv(foul_records, league_name, season)
                        all_fouls_season.extend(foul_records)

                    if fixture_records:
                        all_fixtures_season.extend(fixture_records)

                    logger.info(f"✔ {league_name}: {len(foul_records)} jugadores / {len(fixture_records)} partidos procesados.")

                except PermissionError:
                    logger.error("Se ha alcanzado el límite de la cuota de la API.")
                    return
                except Exception as e:
                    logger.error(f"✖ Error procesando {league_name} ({season}): {e}")

        if all_fixtures_season:
            logger.info(f"Guardando {len(all_fixtures_season)} partidos acumulados en BD...")
            db.save_completed_fixtures(all_fixtures_season)

        total_processed_global += len(all_fouls_season)

    db.update_referee_stats()

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"\n=== PIPELINE COMPLETO FINALIZADO EN {elapsed}s: {total_processed_global} registros procesados ===")
    
if __name__ == "__main__":
    HISTORICAL_SEASONS = [2026]
    run_pipeline(seasons=HISTORICAL_SEASONS, max_workers=5, export_csv=True)