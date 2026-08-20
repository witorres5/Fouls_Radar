# core/reconciliation.py
import sqlite3
from core.api_client import APIFootballClient
from database.data_loader import init_bets_db

def reconcile_daily_bets(api_client: APIFootballClient):
    """
    Consulta las apuestas pendientes, busca el resultado real del partido en la API
    y valida si el jugador cumplió con la línea de faltas apostada.
    """

    init_bets_db()  # <- Asegura que la tabla 'auto_bets' exista antes de hacer la consulta

    conn = sqlite3.connect("database/bets_tracker.db")
    cursor = conn.cursor()


    # Traer apuestas en estado PENDING
    cursor.execute("SELECT id, fixture_id, player_name, bet_line FROM auto_bets WHERE status = 'PENDING'")
    pending_bets = cursor.fetchall()

    if not pending_bets:
        return "No hay apuestas pendientes por verificar."

    for bet_id, fixture_id, player_name, bet_line in pending_bets:
        # Consultar estadísticas detalladas del partido en la API
        fixture_stats = api_client.get_fixture_player_stats(fixture_id)

        if not fixture_stats:
            continue

        # Buscar al jugador en las estadísticas reales del partido
        actual_fouls = None
        for team_data in fixture_stats:
            for p in team_data.get("players", []):
                if player_name.lower() in p["player"]["name"].lower():
                    actual_fouls = p["statistics"][0]["fouls"]["committed"] or 0
                    break

        if actual_fouls is not None:
            # Determinar el umbral (ej. "+1.5 Faltas" necesita >= 2 faltas)
            threshold = 1 if "0.5" in bet_line else (2 if "1.5" in bet_line else 3)
            
            status = "WON" if actual_fouls >= threshold else "LOST"

            cursor.execute("""
                UPDATE auto_bets 
                SET status = ?, actual_fouls = ? 
                WHERE id = ?
            """, (status, actual_fouls, bet_id))

    conn.commit()
    conn.close()
    return "Reconciliación completada exitosamente."