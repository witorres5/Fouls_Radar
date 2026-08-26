from datetime import datetime
from databases.betting_repository import BettingRepository
from controllers.betting_controller import BettingController
from services.telegram_services import send_alert

def main():
    # 1. Inicializar directamente el repositorio de apuestas
    betting_repo = BettingRepository()
    
    # 2. Instanciar Controlador
    betting_controller = BettingController(betting_repo)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f">>> [{datetime.now()}] Ejecutando comprobación de apuestas para: {today_str}")

    # 3. Obtener el mensaje procesado desde el Controller
    message = betting_controller.get_today_high_prob_summary(today_str)

    # 4. Enviar mediante tu servicio de Telegram
    if message:
        send_alert(message)
        print(">>> ✅ Notificación enviada a Telegram con éxito.")
    else:
        print(">>> ℹ️ Sin apuestas pendientes de prob >= 90% para el día de hoy.")

if __name__ == "__main__":
    main()