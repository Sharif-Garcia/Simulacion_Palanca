"""Modelos de datos inmutables del dominio de la palanca.

Estos dataclasses son los "contenedores" que viajan entre las capas:
  - ParametrosPalanca: lo que el usuario controla.
  - ResultadosEstaticos: lo que resuelve la estática (W, F_eq, MA, R).
  - ResultadosDinamicos: lo que resuelve la dinámica (inercia, ωn, ζ, etc.).
  - EstadoSimulacion: el estado instantáneo (θ, ω, t) que avanza en el tiempo.

No contienen lógica de cálculo ni de validación: eso pertenece a
estatica.py, dinamica.py y validadores.py (principio de una sola responsabilidad).

Convención de unidades: los ángulos de los modelos están en RADIANES.
Solo se ofrecen propiedades de conveniencia en grados para mostrar al usuario.
"""

import math
from dataclasses import dataclass
from enum import Enum

from backend import configuracion
from backend.dominio.excepciones import ParametroInvalidoError


class EstadoPalanca(str, Enum):
    """Qué hace la palanca según el torque neto que actúa sobre ella."""

    EQUILIBRIO = "equilibrio"
    CARGA_SUBE = "carga_sube"
    CARGA_BAJA = "carga_baja"


class TipoRespuesta(str, Enum):
    """Clasificación de la respuesta de segundo orden según el factor ζ."""

    SUBAMORTIGUADA = "subamortiguada"  # ζ < 1: oscila y se estabiliza
    CRITICA = "critica"  # ζ = 1: se estabiliza sin oscilar, lo más rápido posible
    SOBREAMORTIGUADA = "sobreamortiguada"  # ζ > 1: se estabiliza lento, sin oscilar


@dataclass(frozen=True, slots=True)
class ParametrosPalanca:
    """Parámetros que el usuario controla desde la interfaz.

    Se guarda el NOMBRE de la gravedad ("Tierra", "Luna", "Marte") y no el
    número, para que la tabla de gravedades viva solo en configuracion.py.
    """

    masa_kg: float
    distancia_carga_m: float
    distancia_esfuerzo_m: float
    fuerza_n: float
    nombre_gravedad: str

    @property
    def gravedad_m_s2(self) -> float:
        """Traduce el nombre de la gravedad a su valor en m/s²."""
        try:
            return configuracion.GRAVEDADES_M_S2[self.nombre_gravedad]
        except KeyError:
            raise ParametroInvalidoError(
                "nombre_gravedad",
                self.nombre_gravedad,
                f"debe ser uno de {list(configuracion.GRAVEDADES_M_S2)}",
            ) from None

    @classmethod
    def por_defecto(cls) -> "ParametrosPalanca":
        """Crea los parámetros iniciales a partir de los valores de configuracion.py."""
        rangos = configuracion.RANGOS_PARAMETROS
        return cls(
            masa_kg=rangos["masa_kg"].valor_inicial,
            distancia_carga_m=rangos["distancia_carga_m"].valor_inicial,
            distancia_esfuerzo_m=rangos["distancia_esfuerzo_m"].valor_inicial,
            fuerza_n=rangos["fuerza_n"].valor_inicial,
            nombre_gravedad=configuracion.GRAVEDAD_INICIAL,
        )


@dataclass(frozen=True, slots=True)
class ResultadosEstaticos:
    """Resultados del análisis estático (equilibrio) de la palanca."""

    peso_n: float  # W = m·g
    fuerza_equilibrio_n: float  # F necesaria para que ΣM_O = 0
    ventaja_mecanica: float  # MA = d_e / d_r
    reaccion_fulcro_n: float  # R en el apoyo


@dataclass(frozen=True, slots=True)
class ResultadosDinamicos:
    """Resultados del análisis dinámico (respuesta de segundo orden)."""

    inercia_kg_m2: float  # I total: barra + carga
    torque_neto_n_m: float  # τ = F·d_e − W·d_r
    estado: EstadoPalanca
    frecuencia_natural_rad_s: float  # ωn = √(k / I)
    factor_amortiguamiento: float  # ζ = c / (2·√(k·I))
    tipo_respuesta: TipoRespuesta
    sobreimpulso_porcentaje: float  # 0 si la respuesta no oscila
    tiempo_establecimiento_s: float  # criterio del 2 %: aprox. 4 / (ζ·ωn)


@dataclass(frozen=True, slots=True)
class EstadoSimulacion:
    """Estado instantáneo de la simulación.

    Es inmutable: para avanzar en el tiempo se crea un estado NUEVO
    (con dataclasses.replace), nunca se modifica el anterior.
    """

    angulo_rad: float
    velocidad_angular_rad_s: float
    tiempo_s: float
    en_tope: bool = False  # True si la barra está apoyada contra un tope de ±30°

    @property
    def angulo_grados(self) -> float:
        """Ángulo en grados, para mostrar en la interfaz."""
        return math.degrees(self.angulo_rad)

    @classmethod
    def inicial(cls) -> "EstadoSimulacion":
        """Estado de arranque: ángulo inicial fijo de configuracion.py, en reposo."""
        return cls(
            angulo_rad=math.radians(configuracion.ANGULO_INICIAL_GRADOS),
            velocidad_angular_rad_s=0.0,
            tiempo_s=0.0,
        )