# jobs/spark_pipeline.py
import sys
from pathlib import Path
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from databases.connection import DatabaseManager


def run_spark_feature_engineering():
    print("🚀 Conectando a Turso para Feature Store de Duelos...")
    db_manager = DatabaseManager()

    query = """
        SELECT 
            pfs.fixture_id, pfs.player_id, pfs.player_name, pfs.team_id,
            pfs.minutes_played, pfs.fouls_committed, pfs.fouls_drawn,
            mf.league_id, mf.season, mf.match_date, mf.referee_name
        FROM player_fixture_stats pfs
        JOIN match_fixtures mf ON pfs.fixture_id = mf.fixture_id
        WHERE pfs.minutes_played > 0
    """

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

    if not rows:
        print("⚠️ No hay datos suficientes en player_fixture_stats.")
        return

    cols = [
        "fixture_id", "player_id", "player_name", "team_id",
        "minutes_played", "fouls_committed", "fouls_drawn",
        "league_id", "season", "match_date", "referee_name"
    ]
    df_raw = pd.DataFrame(rows, columns=cols)

    spark = SparkSession.builder \
        .appName("FoulsRadarMatchupStore") \
        .config("spark.driver.memory", "2g") \
        .getOrCreate()

    sdf = spark.createDataFrame(df_raw)

    # Ventanas por Jugador: Faltas Cometidas (F90) y Provocadas (FD90)
    player_window_all = Window.partitionBy("player_id").orderBy("match_date")
    player_window_l5 = player_window_all.rowsBetween(-4, 0)

    sdf_features = sdf \
        .withColumn("f90_match", (F.col("fouls_committed") / F.col("minutes_played")) * 90.0) \
        .withColumn("fd90_match", (F.col("fouls_drawn") / F.col("minutes_played")) * 90.0) \
        .withColumn("rolling_f90_l5", F.avg("f90_match").over(player_window_l5)) \
        .withColumn("rolling_fd90_l5", F.avg("fd90_match").over(player_window_l5)) \
        .withColumn("total_matches_played", F.count("fixture_id").over(player_window_all))

    # Tomar la última foto del jugador por temporada
    latest_window = Window.partitionBy("player_id", "season").orderBy(F.col("match_date").desc())

    final_features = sdf_features \
        .withColumn("rn", F.row_number().over(latest_window)) \
        .filter(F.col("rn") == 1) \
        .select(
            "player_id", "player_name", "team_id", "league_id", "season",
            F.round("rolling_f90_l5", 2).alias("rolling_f90_l5"),
            F.round("rolling_fd90_l5", 2).alias("rolling_fd90_l5"),
            "total_matches_played"
        )

    df_result = final_features.toPandas()
    spark.stop()

    records = [
        (
            int(r["player_id"]), 
            str(r["player_name"]), 
            int(r["team_id"]),
            int(r["league_id"]), 
            int(r["season"]), 
            float(r["rolling_f90_l5"]),
            float(r["rolling_fd90_l5"]),
            int(r["total_matches_played"])
        )
        for r in df_result.to_dict(orient="records")
    ]

    BATCH_SIZE = 80

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_spark_features (
                player_id INTEGER,
                player_name TEXT,
                team_id INTEGER,
                league_id INTEGER,
                season INTEGER,
                rolling_f90_l5 REAL,
                rolling_fd90_l5 REAL,
                total_matches_played INTEGER,
                PRIMARY KEY (player_id, season)
            )
        """)
        
        # Migración defensiva por si la columna rolling_fd90_l5 no existía
        try:
            cursor.execute("ALTER TABLE player_spark_features ADD COLUMN rolling_fd90_l5 REAL DEFAULT 0.0")
        except Exception:
            pass

        conn.commit()

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            cursor.executemany("""
                INSERT INTO player_spark_features (
                    player_id, player_name, team_id, league_id, season,
                    rolling_f90_l5, rolling_fd90_l5, total_matches_played
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, season) DO UPDATE SET
                    rolling_f90_l5 = excluded.rolling_f90_l5,
                    rolling_fd90_l5 = excluded.rolling_fd90_l5,
                    total_matches_played = excluded.total_matches_played
            """, batch)
            conn.commit()

    print(f"✅ Feature Store de Duelos actualizada ({len(records)} jugadores procesados).")


if __name__ == "__main__":
    run_spark_feature_engineering()