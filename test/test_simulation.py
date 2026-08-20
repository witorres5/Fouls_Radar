# test_simulation.py
from database.data_loader import get_db_client

def simulate_settled_bets():
    client = get_db_client()
    if not client:
        print("❌ No se pudo conectar a la base de datos.")
        return

    try:
        # Simulamos resultados para las apuestas ID 22, 23 y 24
        # ID 22: Ganada (2 faltas cometidas)
        client.execute("UPDATE auto_bets SET status = 'WON', actual_fouls = 2 WHERE id = 22")
        
        # ID 23: Ganada (1 falta cometida)
        client.execute("UPDATE auto_bets SET status = 'WON', actual_fouls = 1 WHERE id = 23")
        
        # ID 24: Perdida (1 falta cometida en linea +1.5)
        client.execute("UPDATE auto_bets SET status = 'LOST', actual_fouls = 1 WHERE id = 24")

        print("✅ Apuestas de prueba simuladas exitosamente (ID 22, 23, 24).")
    except Exception as e:
        print(f"❌ Error actualizando datos: {e}")

if __name__ == "__main__":
    simulate_settled_bets()