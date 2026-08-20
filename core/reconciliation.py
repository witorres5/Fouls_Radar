# core/reconciliation.py
from core.api_client import APIFootballClient
from database.data_loader import init_bets_db
from main import DatabaseManager
from core.notifications import send_telegram_alert

db = DatabaseManager()

def reconcile_daily_bets(api_client: APIFootballClient):
    """
    Consulta las apuestas pendientes en Turso, busca el resultado real del partido
    en la API y valida si el jugador cumplió con la línea de faltas apostada.
    """

    init_bets_db()  # Asegura que la tabla 'auto_bets' exista en Turso

    try:
        conn = db._get_connection()
        cursor = conn.cursor()

        # Traer apuestas en estado PENDING desde Turso
        cursor.execute("SELECT id, fixture_id, player_name, bet_line FROM auto_bets WHERE status = 'PENDING'")
        pending_bets = cursor.fetchall()

        if not pending_bets:
            conn.close()
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
                    if player_name.lower() in p.get("player", {}).get("name", "").lower():
                        stats = p.get("statistics", [{}])[0]
                        actual_fouls = stats.get("fouls", {}).get("committed") or 0
                        break
                if actual_fouls is not None:
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
        msg = f"⚽ *Reconciliación Diaria Completada*\nSe han verificado las apuestas pendientes en Turso."
        send_telegram_alert(msg)
        return "Reconciliación completada exitosamente."

    except Exception as e:
        print(f"Error en reconciliación de apuestas: {e}")
        return f"Error al reconciliar: {e}"