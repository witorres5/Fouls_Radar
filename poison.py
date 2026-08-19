import numpy as np
from scipy.stats import poisson

def calcular_probabilidades_poisson(lambda_local, lambda_visitante, max_goles=5):
    """
    Calcula la matriz de probabilidades de goles usando la distribución de Poisson.
    """
    matriz_probabilidades = np.zeros((max_goles + 1, max_goles + 1))
    
    for i in range(max_goles + 1):
        for j in range(max_goles + 1):
            # Probabilidad de que el local meta i goles y el visitante j goles
            prob_local = poisson.pmf(i, lambda_local)
            prob_visitante = poisson.pmf(j, lambda_visitante)
            matriz_probabilidades[i, j] = prob_local * prob_visitante

    # Sumar probabilidades para Victoria Local, Empate y Victoria Visitante
    prob_victoria_local = np.sum(np.tril(matriz_probabilidades, -1)) # Inferior diagonal (goles local > goles visitante)
    # Nota: la matriz trues deben manejarse con cuidado, sumemos explícitamente:
    
    p_local = 0
    p_empate = 0
    p_visitante = 0
    
    for i in range(max_goles + 1):
        for j in range(max_goles + 1):
            p = matriz_probabilidades[i, j]
            if i > j:
                p_local += p
            elif i == j:
                p_empate += p
            else:
                p_visitante += p
                
    return p_local * 100, p_empate * 100, p_visitante * 100

# --- EJEMPLO DE PRUEBA ---
# Imaginemos un partido donde el modelo calcula que el Local meterá 1.65 goles 
# y el Visitante meterá 1.05 goles basándose en sus estadísticas.
lambda_l = 1.65
lambda_v = 1.05

p_loc, p_emp, p_vis = calcular_probabilidades_poisson(lambda_l, lambda_v)

print(f"--- ANÁLISIS DE PREDICCIÓN (Modelo Poisson) ---")
print(f"Goles esperados Local: {lambda_l} | Goles esperados Visitante: {lambda_v}")
print(f"Probabilidad Victoria Local: {p_loc:.2f}%")
print(f"Probabilidad de Empate: {p_emp:.2f}%")
print(f"Probabilidad Victoria Visitante: {p_vis:.2f}%")