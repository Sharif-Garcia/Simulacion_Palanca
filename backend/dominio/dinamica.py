"""Dinámica de la palanca: del equilibrio al movimiento de segundo orden.

Modelo (una sola ecuación diferencial):

    I·θ'' + c·θ' + k·θ = τ        =>        θ'' = (τ - c·θ' - k·θ) / I

  - I: momento de inercia de la barra más la carga, respecto al fulcro.
  - c: amortiguamiento (fricción en el fulcro), constante fija.
  - k: rigidez restauradora, constante fija. Una palanca real no tiene resorte;
       este término es una simplificación del modelo para que el sistema sea
       de segundo orden y se estabilice en θ_eq = τ / k.
  - τ: torque neto, calculado con estatica.py (no se repite la fórmula).

Supuestos del modelo:
  - La barra es uniforme y su peso propio está compensado (por ejemplo, con
    un contrapeso): solo aporta INERCIA, no torque. Así el equilibrio coincide
    con la ecuación del taller F·d_e = W·d_r.
  - Los brazos de palanca no cambian con el ángulo (modelo lineal).
  - El tope de ±30° NO se aplica aquí: lo aplica el simulador, porque es una
    restricción del movimiento y no de la ecuación.

Convención de signos: torque positivo => θ positivo (el esfuerzo baja).
"""

import math
from dataclasses import dataclass

from backend import configuracion
from backend.dominio.estatica import (
    PRIMER_GENERO,
    GeneroPalanca,
    calcular_peso_n,
    calcular_torque_neto_n_m,
)
from backend.dominio.modelos import (
    EstadoPalanca,
    ParametrosPalanca,
    ResultadosDinamicos,
    TipoRespuesta,
)
from backend.dominio.validadores import exigir_positivo

# Criterio del 2 %: la respuesta queda dentro del 2 % del valor final.
FACTOR_TIEMPO_ESTABLECIMIENTO = 4.0  # ts ≈ 4 / (ζ·ωn) si ζ < 1
FACTOR_TIEMPO_ESTABLECIMIENTO_CRITICO = 5.83  # ts ≈ 5.83 / ωn si ζ = 1
# Margen alrededor de ζ = 1 para clasificar la respuesta como crítica.
TOLERANCIA_AMORTIGUAMIENTO_CRITICO = 1e-3


def calcular_inercia_kg_m2(
    masa_kg: float,
    distancia_carga_m: float,
    distancia_esfuerzo_m: float,
    masa_barra_kg: float = configuracion.MASA_BARRA_KG,
) -> float:
    """Momento de inercia respecto al fulcro: barra uniforme + carga puntual.

    La barra mide d_r + d_e y el fulcro está a d_r de un extremo, así que su
    centro queda a (d_e - d_r) / 2 del fulcro. Teorema de los ejes paralelos:
        I_barra = M·L²/12 + M·desplazamiento²
        I_carga = m·d_r²
    """
    exigir_positivo("masa_kg", masa_kg)
    exigir_positivo("distancia_carga_m", distancia_carga_m)
    exigir_positivo("distancia_esfuerzo_m", distancia_esfuerzo_m)
    exigir_positivo("masa_barra_kg", masa_barra_kg)

    longitud_barra_m = distancia_carga_m + distancia_esfuerzo_m
    desplazamiento_centro_m = (distancia_esfuerzo_m - distancia_carga_m) / 2.0
    inercia_barra = masa_barra_kg * longitud_barra_m**2 / 12.0 + masa_barra_kg * desplazamiento_centro_m**2
    inercia_carga = masa_kg * distancia_carga_m**2
    return inercia_barra + inercia_carga


def calcular_frecuencia_natural_rad_s(rigidez_n_m_rad: float, inercia_kg_m2: float) -> float:
    """Frecuencia natural no amortiguada: ωn = √(k / I)."""
    exigir_positivo("rigidez_n_m_rad", rigidez_n_m_rad)
    exigir_positivo("inercia_kg_m2", inercia_kg_m2)
    return math.sqrt(rigidez_n_m_rad / inercia_kg_m2)


def calcular_factor_amortiguamiento(
    amortiguamiento_n_m_s_rad: float, rigidez_n_m_rad: float, inercia_kg_m2: float
) -> float:
    """Factor de amortiguamiento: ζ = c / (2·√(k·I))."""
    exigir_positivo("amortiguamiento_n_m_s_rad", amortiguamiento_n_m_s_rad)
    exigir_positivo("rigidez_n_m_rad", rigidez_n_m_rad)
    exigir_positivo("inercia_kg_m2", inercia_kg_m2)
    return amortiguamiento_n_m_s_rad / (2.0 * math.sqrt(rigidez_n_m_rad * inercia_kg_m2))


def clasificar_respuesta(factor_amortiguamiento: float) -> TipoRespuesta:
    """Clasifica la respuesta según ζ: subamortiguada, crítica o sobreamortiguada."""
    if abs(factor_amortiguamiento - 1.0) <= TOLERANCIA_AMORTIGUAMIENTO_CRITICO:
        return TipoRespuesta.CRITICA
    if factor_amortiguamiento < 1.0:
        return TipoRespuesta.SUBAMORTIGUADA
    return TipoRespuesta.SOBREAMORTIGUADA


def calcular_sobreimpulso_porcentaje(factor_amortiguamiento: float) -> float:
    """Sobreimpulso máximo: Mp = 100·exp(-π·ζ / √(1 - ζ²)). Es 0 si no oscila."""
    if clasificar_respuesta(factor_amortiguamiento) is not TipoRespuesta.SUBAMORTIGUADA:
        return 0.0
    raiz = math.sqrt(1.0 - factor_amortiguamiento**2)
    return 100.0 * math.exp(-math.pi * factor_amortiguamiento / raiz)


def calcular_tiempo_establecimiento_s(
    factor_amortiguamiento: float, frecuencia_natural_rad_s: float
) -> float:
    """Tiempo aproximado para quedar dentro del 2 % del valor final.

    - ζ < 1:  ts = 4 / (ζ·ωn)
    - ζ ≈ 1:  ts = 5.83 / ωn
    - ζ > 1:  ts = 4 / σ, con σ = ωn·(ζ - √(ζ² - 1)) el polo dominante (lento).
              Se usa la forma equivalente 1 / (ζ + √(ζ² - 1)) para evitar
              restar números casi iguales cuando ζ es grande.
    """
    tipo = clasificar_respuesta(factor_amortiguamiento)
    if tipo is TipoRespuesta.SUBAMORTIGUADA:
        return FACTOR_TIEMPO_ESTABLECIMIENTO / (factor_amortiguamiento * frecuencia_natural_rad_s)
    if tipo is TipoRespuesta.CRITICA:
        return FACTOR_TIEMPO_ESTABLECIMIENTO_CRITICO / frecuencia_natural_rad_s
    raiz = math.sqrt(factor_amortiguamiento**2 - 1.0)
    return FACTOR_TIEMPO_ESTABLECIMIENTO * (factor_amortiguamiento + raiz) / frecuencia_natural_rad_s

def calcular_rapidez_maxima_rad_s(
    factor_amortiguamiento: float, frecuencia_natural_rad_s: float
) -> float:
    """Rapidez del modo más rápido del sistema, en rad/s (polo de mayor módulo).

    - ζ <= 1: los polos son complejos y su módulo es ωn.
    - ζ > 1: los polos son reales y el más rápido es ωn·(ζ + √(ζ² - 1)).
    """
    if factor_amortiguamiento <= 1.0:
        return frecuencia_natural_rad_s
    return frecuencia_natural_rad_s * (
        factor_amortiguamiento + math.sqrt(factor_amortiguamiento**2 - 1.0)
    )

def clasificar_estado(
    torque_neto_n_m: float, tolerancia_n_m: float = configuracion.TOLERANCIA_EQUILIBRIO_N_M
) -> EstadoPalanca:
    """Indica si la palanca está en equilibrio o hacia dónde tiende a moverse."""
    if abs(torque_neto_n_m) <= tolerancia_n_m:
        return EstadoPalanca.EQUILIBRIO
    if torque_neto_n_m > 0:
        return EstadoPalanca.CARGA_SUBE
    return EstadoPalanca.CARGA_BAJA


@dataclass(frozen=True, slots=True)
class ModeloDinamico:
    """Ecuación de movimiento ya armada para unos parámetros dados.

    Precalcula la inercia y el torque una sola vez, para que el integrador
    pueda evaluar la aceleración cientos de veces por segundo sin repetir
    esos cálculos. Es inmutable: si el usuario cambia un parámetro, el
    simulador crea un modelo nuevo.
    """

    inercia_kg_m2: float
    torque_neto_n_m: float
    rigidez_n_m_rad: float
    amortiguamiento_n_m_s_rad: float

    @classmethod
    def desde_parametros(
        cls,
        parametros: ParametrosPalanca,
        genero: GeneroPalanca = PRIMER_GENERO,
        rigidez_n_m_rad: float = configuracion.RIGIDEZ_RESTAURADORA_N_M_RAD,
        amortiguamiento_n_m_s_rad: float = configuracion.AMORTIGUAMIENTO_N_M_S_RAD,
    ) -> "ModeloDinamico":
        """Arma el modelo a partir de los parámetros del usuario y las constantes fijas."""
        exigir_positivo("rigidez_n_m_rad", rigidez_n_m_rad)
        exigir_positivo("amortiguamiento_n_m_s_rad", amortiguamiento_n_m_s_rad)

        peso_n = calcular_peso_n(parametros.masa_kg, parametros.gravedad_m_s2)
        return cls(
            inercia_kg_m2=calcular_inercia_kg_m2(
                parametros.masa_kg, parametros.distancia_carga_m, parametros.distancia_esfuerzo_m
            ),
            torque_neto_n_m=calcular_torque_neto_n_m(
                peso_n,
                parametros.fuerza_n,
                parametros.distancia_carga_m,
                parametros.distancia_esfuerzo_m,
                genero,
            ),
            rigidez_n_m_rad=rigidez_n_m_rad,
            amortiguamiento_n_m_s_rad=amortiguamiento_n_m_s_rad,
        )

    @property
    def frecuencia_natural_rad_s(self) -> float:
        """ωn del modelo."""
        return calcular_frecuencia_natural_rad_s(self.rigidez_n_m_rad, self.inercia_kg_m2)

    @property
    def factor_amortiguamiento(self) -> float:
        """ζ del modelo."""
        return calcular_factor_amortiguamiento(
            self.amortiguamiento_n_m_s_rad, self.rigidez_n_m_rad, self.inercia_kg_m2
        )

    @property
    def rapidez_maxima_rad_s(self) -> float:
        """Rapidez del modo más rápido; limita el paso de integración estable."""
        return calcular_rapidez_maxima_rad_s(
            self.factor_amortiguamiento, self.frecuencia_natural_rad_s
        )

    @property
    def angulo_equilibrio_rad(self) -> float:
        """Ángulo donde el sistema se detendría sin tope: θ_eq = τ / k."""
        return self.torque_neto_n_m / self.rigidez_n_m_rad

    def aceleracion_angular(self, angulo_rad: float, velocidad_angular_rad_s: float) -> float:
        """Aceleración angular: θ'' = (τ - c·θ' - k·θ) / I."""
        torque_resultante = (
            self.torque_neto_n_m
            - self.amortiguamiento_n_m_s_rad * velocidad_angular_rad_s
            - self.rigidez_n_m_rad * angulo_rad
        )
        return torque_resultante / self.inercia_kg_m2


def resolver_dinamica(
    parametros: ParametrosPalanca, genero: GeneroPalanca = PRIMER_GENERO
) -> ResultadosDinamicos:
    """Resuelve el análisis dinámico completo para unos parámetros dados."""
    modelo = ModeloDinamico.desde_parametros(parametros, genero)
    frecuencia_natural = modelo.frecuencia_natural_rad_s
    factor = modelo.factor_amortiguamiento
    return ResultadosDinamicos(
        inercia_kg_m2=modelo.inercia_kg_m2,
        torque_neto_n_m=modelo.torque_neto_n_m,
        estado=clasificar_estado(modelo.torque_neto_n_m),
        frecuencia_natural_rad_s=frecuencia_natural,
        factor_amortiguamiento=factor,
        tipo_respuesta=clasificar_respuesta(factor),
        sobreimpulso_porcentaje=calcular_sobreimpulso_porcentaje(factor),
        tiempo_establecimiento_s=calcular_tiempo_establecimiento_s(factor, frecuencia_natural),
    )