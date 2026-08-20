import math

def poisson_prob(k: int, lambd: float) -> float:
    """Calcula la probabilidad de que ocurran exactamente k eventos con tasa lambd."""
    return (math.exp(-lambd) * (lambd ** k)) / math.factorial(k)

def prob_at_least(k: int, lambd: float) -> float:
    """Calcula la probabilidad acumulada de tener k o más eventos."""
    prob_less = sum(poisson_prob(i, lambd) for i in range(k))
    return max(0.0, 1.0 - prob_less)