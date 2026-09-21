"""Configuración central del simulador de la palanca.

Este módulo es  fuente para constantes físicas, rangos de los controles y parámetros de la simulación.

Convención de ángulos: en este módulo los ángulos se expresan en GRADOS
porque son más legibles para las personas. Las capas de física los convierten
a radianes internamente.
"""

import os
from dataclasses import dataclass
from types import MappingProxyType

# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
# Railway (y despliegues similares) inyectan PORT automáticamente; HOST se
# puede fijar por variable de entorno para no romper el valor local por defecto.
HOST_SERVIDOR = os.environ.get("HOST", "127.0.0.1")
PUERTO_SERVIDOR = int(os.environ.get("PORT", 8000))
NIVEL_REGISTRO = "INFO"

# ---------------------------------------------------------------------------
# Física: entorno
# ---------------------------------------------------------------------------
# Solo lectura: MappingProxyType impide modificar el diccionario por accidente.
GRAVEDADES_M_S2 = MappingProxyType(
    {
        "Tierra": 9.81,
        "Luna": 1.62,
        "Marte": 3.71,
    }
)
GRAVEDAD_INICIAL = "Tierra"

# ---------------------------------------------------------------------------
# Física: género de la palanca
# ---------------------------------------------------------------------------
# Las claves coinciden con GENEROS_DISPONIBLES en backend/dominio/estatica.py.
GENERO_INICIAL = "primer_genero"

# ---------------------------------------------------------------------------
# Física: constantes internas del modelo 
# ---------------------------------------------------------------------------
ANGULO_INICIAL_GRADOS = 0.0
LIMITE_ANGULO_GRADOS = 30.0  # tope mecánico: la barra queda entre -30° y +30°
RIGIDEZ_RESTAURADORA_N_M_RAD = 1000.0  # k, torque restaurador por radian
AMORTIGUAMIENTO_N_M_S_RAD = 175.0  # c, fricción en el fulcro

MASA_BARRA_KG = 5.0  # masa de la barra, entra en el momento de inercia
IMPULSO_PERTURBACION_RAD_S = 1.0  # velocidad angular que agrega el "empujón"
TOLERANCIA_EQUILIBRIO_N_M = 0.5  # |torque neto| menor a esto se considera equilibrio

# ---------------------------------------------------------------------------
# Simulación en el tiempo
# ---------------------------------------------------------------------------
FRECUENCIA_CUADROS_HZ = 60  # cuántas veces por segundo se envía el estado al navegador
SUBPASOS_POR_CUADRO = 4  # pasos de integración por cada cuadro (más precisión)
PASO_INTEGRACION_S = 1.0 / (FRECUENCIA_CUADROS_HZ * SUBPASOS_POR_CUADRO)
FACTOR_ESTABILIDAD_PASO = 1.0
LONGITUD_MAXIMA_MENSAJE = 4096
# ---------------------------------------------------------------------------
# Rangos de los controles del usuario
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RangoParametro:
    """Describe un control numérico: límites, paso, valor inicial y textos."""

    etiqueta: str
    unidad: str
    minimo: float
    maximo: float
    paso: float
    valor_inicial: float

    def __post_init__(self) -> None:
        """Verifica que el rango sea coherente al crearlo."""
        if self.minimo >= self.maximo:
            raise ValueError(
                f"Rango inválido en '{self.etiqueta}': el mínimo debe ser menor que el máximo."
            )
        if self.paso <= 0:
            raise ValueError(f"Rango inválido en '{self.etiqueta}': el paso debe ser positivo.")
        if not self.contiene(self.valor_inicial):
            raise ValueError(
                f"Rango inválido en '{self.etiqueta}': el valor inicial está fuera del rango."
            )

    def contiene(self, valor: float) -> bool:
        """Indica si el valor está dentro del rango (extremos incluidos)."""
        return self.minimo <= valor <= self.maximo


RANGOS_PARAMETROS = MappingProxyType(
    {
        "masa_kg": RangoParametro(
            etiqueta="Masa de la carga", unidad="kg",
            minimo=1.0, maximo=200.0, paso=1.0, valor_inicial=50.0,
        ),
        "distancia_carga_m": RangoParametro(
            etiqueta="Distancia carga al fulcro", unidad="m",
            # Mismo máximo que distancia_esfuerzo_m: en segundo y tercer
            # género la carga y el esfuerzo comparten el mismo lado del
            # fulcro, así que la carga debe poder recorrer todo ese rango.
            minimo=0.1, maximo=5.0, paso=0.05, valor_inicial=0.5,
        ),
        "distancia_esfuerzo_m": RangoParametro(
            etiqueta="Distancia esfuerzo al fulcro", unidad="m",
            minimo=0.1, maximo=5.0, paso=0.05, valor_inicial=2.0,
        ),
        "fuerza_n": RangoParametro(
            etiqueta="Fuerza aplicada", unidad="N",
            minimo=0.0, maximo=1000.0, paso=0.1, valor_inicial=122.6,
        ),
    }
)