"""
main.py
Pipeline principal de extracción y almacenamiento de métricas disciplinarias.
Procesa las ligas configuradas a través de múltiples temporadas (incluyendo 2026) 
y persiste los datos en SQLite/Turso y CSV.
"""

import os
import csv
import time
import logging
import libsql
from typing import List, Union
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker

from config.constants import TARGET_LEAGUES
from core.api_client import APIFootballClient
from core.foul_extractor import parse_player_fouls
from models.foul_stats import PlayerFoulStats

# Configuración de Logs
logger = logging.getLogger("FoulsTracker.Main")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# --- MODELO ORM DE SQLALCHEMY ---
Base = declarative_base()

class PlayerFoulRecord(Base):
    __tablename__ = "player_foul_stats"

    # Clave primaria compuesta por jugador, liga y temporada
    id = Column(String, primary_key=True)
    player_id = Column(Integer, nullable=False, index=True)
    player_name = Column(String, nullable=False)
    team_id = Column(Integer, nullable=False)
    team_name = Column(String, nullable=False)
    league_id = Column(Integer, nullable=False, index=True)
    league_name = Column(String, nullable=False)
    season = Column(Integer, nullable=False, index=True)
    minutes_played = Column(Integer, default=0)
    fouls_committed = Column(Integer, default=0)
    fouls_drawn = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    fouls_per_90 = Column(Float, default=0.0)
    updated_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


# --- GESTOR DE BASE DE DATOS (CONEXIÓN DIRECTA A TURSO/LIBSQL) ---
class DatabaseManager:
    def __init__(self):
        # Lee credenciales desde Streamlit Secrets si existen, o cae a variables de entorno
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
            return libsql.connect(database=self.turso_url, auth_token=self.turso_token)
        else:
            return libsql.connect("fouls_tracker.db")

    def _init_db(self):
        """Crea la tabla principal si no existe."""
        conn = self._get_connection()
        cursor = conn.cursor()
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
        
        # 2. Nueva Tabla: Historial de Árbitros
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

        # 3. Nueva Tabla: Simulador de Apuestas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulated_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                league_id INTEGER NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                referee_name TEXT,
                predicted_fouls REAL NOT NULL,
                bet_line REAL NOT NULL,
                bet_type TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                actual_fouls INTEGER,
                created_at TEXT
            )
        """)
        
        # Tabla para el simulador de apuestas
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
        conn.commit()
        conn.close()

    def get_referee(self, referee_name: str):
        """Consulta métricas de un árbitro registrado."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT matches_count, avg_fouls FROM referee_stats WHERE referee_name = ?",
            (referee_name,)
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def save_simulated_bet(self, bet_data: dict):
        """Guarda una apuesta simulada en la base de datos."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO simulated_bets (
                fixture_id, match_date, league_id, home_team, away_team, 
                referee_name, predicted_fouls, bet_line, bet_type, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', datetime('now'))
        """, (
            bet_data["fixture_id"], bet_data["match_date"], bet_data["league_id"],
            bet_data["home_team"], bet_data["away_team"], bet_data.get("referee_name"),
            bet_data["predicted_fouls"], bet_data["bet_line"], bet_data["bet_type"]
        ))
        conn.commit()
        conn.close()
        
    def save_foul_records(self, records: List[PlayerFoulStats], league_name: str):
        """Inserta o actualiza registros en lote (batch) de forma ultrarrápida."""
        if not records:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

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

        now = datetime.now(timezone.utc).isoformat()

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

        cursor.executemany(query, data_to_insert)
        conn.commit()
        conn.close()
        
        logger.info(f"Guardados/Actualizados {len(records)} registros en lote para {league_name}.")


# --- EXPORTADOR A CSV ---
def export_to_csv(records: List[PlayerFoulStats], league_name: str, season: int, output_dir: str = "exports"):
    """Exporta los registros procesados a un archivo CSV estructurado por liga y temporada."""
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
            
    logger.info(f"Archivo CSV exportado: {filename}")

def save_completed_fixtures(self, fixtures: list):
    """Guarda o actualiza el historial de partidos finalizados y sus árbitros."""
    if not fixtures:
        return
    conn = self._get_connection()
    cursor = conn.cursor()
    query = """
        INSERT INTO match_fixtures (fixture_id, season, league_id, referee_name, total_fouls, total_yellow_cards)
        VALUES (:fixture_id, :season, :league_id, :referee_name, :total_fouls, :total_yellow_cards)
        ON CONFLICT(fixture_id) DO UPDATE SET
            referee_name = excluded.referee_name,
            total_fouls = excluded.total_fouls,
            total_yellow_cards = excluded.total_yellow_cards
    """
    cursor.executemany(query, fixtures)
    conn.commit()
    conn.close()


# --- FUNCIÓN DE SINCRONIZACIÓN INDIVIDUAL (PARA APP.PY) ---
def sync_league_data(league_id: int, league_name: str, season: int) -> int:
    """Extrae y persiste los datos de jugadores Y partidos (con árbitros) de una liga/temporada."""
    client = APIFootballClient()
    db = DatabaseManager()

    # 1. Sincronizar Faltas de Jugadores
    raw_data = client.get_player_season_fouls(league_id=league_id, season=season)
    foul_records = parse_player_fouls(raw_data, league_id=league_id, season=season)

    if foul_records:
        db.save_foul_records(foul_records, league_name)
        export_to_csv(foul_records, league_name, season)

    # 2. Sincronizar Partidos Finalizados y Estadísticas de Árbitros
    # Obtenemos todos los partidos jugados hasta la fecha para esta liga/temporada
    completed_fixtures = client.get_completed_fixtures(league_id=league_id, season=season)

    if completed_fixtures:
        fixture_records = []
        for f in completed_fixtures:
            referee_raw = f.get("fixture", {}).get("referee")
            
            # Limpiar nombre del árbitro (ej: "R. Claus, Brazil" -> "R. Claus")
            clean_referee = referee_raw.split(",")[0].strip() if referee_raw else None

            # Extraer totales de faltas y tarjetas del partido desde la API
            # Ajusta según las llaves que te entregue tu cliente API (ej: f["statistics"])
            total_fouls = f.get("statistics", {}).get("total_fouls", 0)
            total_yellows = f.get("statistics", {}).get("total_yellow_cards", 0)

            fixture_records.append({
                "fixture_id": f["fixture"]["id"],
                "season": season,
                "league_id": league_id,
                "referee_name": clean_referee,
                "total_fouls": total_fouls,
                "total_yellow_cards": total_yellows
            })

        # Guardar o actualizar fixtures en la base de datos
        db.save_completed_fixtures(fixture_records)

    return len(foul_records)



# --- PIPELINE PRINCIPAL ---
def run_pipeline(seasons: Union[int, List[int]] = 2024, export_csv: bool = True):
    """Ejecuta el proceso de extracción para una o varias temporadas."""
    if isinstance(seasons, int):
        seasons = [seasons]

    client = APIFootballClient()
    db = DatabaseManager()

    logger.info(f"=== INICIANDO PIPELINE MULTITEMPORADA: {seasons} ===")
    total_processed_global = 0

    for season in seasons:
        logger.info(f"\n==================================================")
        logger.info(f"    PROCESANDO TEMPORADA: {season}")
        logger.info(f"==================================================")
        
        season_processed = 0

        for league_id, info in TARGET_LEAGUES.items():
            league_name = info["name"]
            logger.info(f"\nProcesando: {league_name} ({info['country']}) - ID: {league_id} | Año: {season}")

            try:
                # 1. Extracción desde la API
                raw_data = client.get_player_season_fouls(league_id=league_id, season=season)
                
                # 2. Transformación de datos
                foul_records = parse_player_fouls(raw_data, league_id=league_id, season=season)
                
                if not foul_records:
                    logger.warning(f"Sin registros disciplinarios para {league_name} en la temporada {season}.")
                    continue

                # 3. Persistencia (UPSERT automático por ID compuesto)
                db.save_foul_records(foul_records, league_name)

                # 4. Exportación a CSV
                if export_csv:
                    export_to_csv(foul_records, league_name, season)

                season_processed += len(foul_records)

            except PermissionError:
                logger.error("Se ha alcanzado el límite de la cuota diaria de la API. Interrumpiendo el pipeline.")
                return
            except Exception as e:
                logger.error(f"Error procesando {league_name} ({season}): {e}")
                continue

            # Pausa táctica de 300ms entre llamadas a la API
            time.sleep(0.3)

        total_processed_global += season_processed
        logger.info(f"Finalizada temporada {season}. Jugadores procesados: {season_processed}")

    logger.info(f"\n=== PIPELINE COMPLETO FINALIZADO: {total_processed_global} registros totales cargados ===")


if __name__ == "__main__":
    HISTORICAL_SEASONS = [2024, 2025, 2026]
    run_pipeline(seasons=HISTORICAL_SEASONS, export_csv=True)