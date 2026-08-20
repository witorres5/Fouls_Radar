# test_simulation.py
from database.data_loader import get_db_client

def simulate_settled_bets():
    client = get_db_client()
    if not client:
        print("❌ No se pudo conectar a la base de datos.")
        return

    try:
        # Si client es una conexión nativa SQL/LibSQL
        cursor = client.cursor() if hasattr(client, 'cursor') else client
        
        client.execute("UPDATE auto_bets SET status = 'PENDING', actual_fouls = NULL WHERE id IN (22, 23, 24)")

        # Asegurar persistencia de cambios en la BD
        if hasattr(client, 'commit'):

            client.commit()

        print("✅ Apuestas de prueba simuladas y guardadas exitosamente (ID 22, 23, 24).")
    except Exception as e:
        print(f"❌ Error actualizando datos: {e}")

if __name__ == "__main__":
    simulate_settled_bets()