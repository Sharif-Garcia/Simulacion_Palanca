"""Simulador: junta el modelo dinámico, el integrador y el tope mecánico.

Responsabilidades (y solo estas):
  - Guardar el estado actual (θ, ω, t) y los parámetros vigentes.
  - Avanzar el tiempo un cuadro (varios subpasos de integración).
  - Aplicar el tope mecánico de ±30°.
  - Aceptar cambios de parámetros en caliste, conservando el estado.
  - Aplicar la perturbación (un empujón) y reiniciar.


Estabilidad numérica: si el modelo es muy rígido (barra ligera y muy
amortiguada), un paso fijo haría divergir a RK4. Por eso el número de subpasos
por cuadro se calcula a partir del modo más rápido del modelo cada vez que
cambian los parámetros.

Un Simulador NO es seguro entre hilos: debe usarse uno por cliente conectado.
"""

import math
from dataclasses import dataclass, replace

from backend import configuracion
from backend.dominio.dinamica import ModeloDinamico, resolver_dinamica
from backend.dominio.estatica import PRIMER_GENERO, GeneroPalanca, resolver_estatica
from backend.dominio.excepciones import ParametroInvalidoError
from backend.dominio.modelos import (
    EstadoSimulacion,
    ParametrosPalanca,
    ResultadosDinamicos,
    ResultadosEstaticos,
)
from backend.dominio.validadores import exigir_positivo
from backend.simulacion.integradores import Integrador

DURACION_CUADRO_S = 1.0 / configuracion.FRECUENCIA_CUADROS_HZ
LIMITE_ANGULO_RAD = math.radians(configuracion.LIMITE_ANGULO_GRADOS)
# Evita que un cociente como 4.000000000000001 se redondee hacia arriba a 5.
TOLERANCIA_REDONDEO_SUBPASOS = 1e-9


def aplicar_tope_mecanico(estado: EstadoSimulacion, limite_rad: float) -> EstadoSimulacion:
    """Limita el ángulo a [-límite, +límite] y marca si la barra está en el tope.

    Choque inelástico: al llegar al tope la barra se detiene (ω = 0) y no
    rebota. Si la velocidad ya la aleja del tope, se conserva.
    Siempre devuelve un estado nuevo con en_tope actualizado (True o False).
    """
    angulo = estado.angulo_rad
    velocidad = estado.velocidad_angular_rad_s
    if angulo >= limite_rad:
        return replace(
            estado,
            angulo_rad=limite_rad,
            velocidad_angular_rad_s=min(velocidad, 0.0),
            en_tope=True,
        )
    if angulo <= -limite_rad:
        return replace(
            estado,
            angulo_rad=-limite_rad,
            velocidad_angular_rad_s=max(velocidad, 0.0),
            en_tope=True,
        )
    return replace(estado, en_tope=False)


@dataclass(frozen=True, slots=True)
class _Configuracion:
    """Todo lo que depende de los parámetros vigentes, calculado de una sola vez.

    Se crea completo o no se crea: así un cambio de parámetros inválido no
    deja al simulador a medio actualizar.
    """

    parametros: ParametrosPalanca
    modelo: ModeloDinamico
    resultados_estaticos: ResultadosEstaticos
    resultados_dinamicos: ResultadosDinamicos
    subpasos: int
    paso_s: float


class Simulador:
    """Simulación en el tiempo de una palanca de segundo orden con tope."""

    def __init__(
        self,
        integrador: Integrador,
        parametros: ParametrosPalanca,
        *,
        genero: GeneroPalanca = PRIMER_GENERO,
        duracion_cuadro_s: float = DURACION_CUADRO_S,
        limite_angulo_rad: float = LIMITE_ANGULO_RAD,
        impulso_perturbacion_rad_s: float = configuracion.IMPULSO_PERTURBACION_RAD_S,
    ) -> None:
        self._integrador = integrador
        self._genero = genero
        self._duracion_cuadro_s = exigir_positivo("duracion_cuadro_s", duracion_cuadro_s)
        self._limite_angulo_rad = exigir_positivo("limite_angulo_rad", limite_angulo_rad)
        self._impulso_rad_s = exigir_positivo("impulso_perturbacion_rad_s", impulso_perturbacion_rad_s)
        self._activa = self._construir_configuracion(parametros)
        self._estado = EstadoSimulacion.inicial()

    # --- Consulta ----------------------------------------------------------
    @property
    def estado(self) -> EstadoSimulacion:
        """Estado actual (inmutable)."""
        return self._estado

    @property
    def parametros(self) -> ParametrosPalanca:
        """Parámetros vigentes."""
        return self._activa.parametros

    @property
    def resultados_estaticos(self) -> ResultadosEstaticos:
        """W, F_eq, MA y R para los parámetros vigentes."""
        return self._activa.resultados_estaticos

    @property
    def resultados_dinamicos(self) -> ResultadosDinamicos:
        """I, τ, ωn, ζ, sobreimpulso y tiempo de establecimiento vigentes."""
        return self._activa.resultados_dinamicos

    @property
    def subpasos_por_cuadro(self) -> int:
        """Cuántos pasos de integración se hacen en cada cuadro."""
        return self._activa.subpasos

    @property
    def paso_integracion_s(self) -> float:
        """Duración de cada paso de integración."""
        return self._activa.paso_s

    # --- Acciones ----------------------------------------------------------
    def avanzar_cuadro(self) -> EstadoSimulacion:
        """Avanza un cuadro de animación y devuelve el estado resultante.

        Es atómico: si la integración falla, el estado anterior se conserva.
        """
        activa = self._activa
        estado = self._estado
        for _ in range(activa.subpasos):
            estado = self._integrador.paso(estado, activa.modelo.aceleracion_angular, activa.paso_s)
            estado = aplicar_tope_mecanico(estado, self._limite_angulo_rad)
        self._estado = estado
        return estado

    def actualizar_parametros(self, parametros: ParametrosPalanca) -> None:
        """Cambia los parámetros en caliente conservando θ, ω y el tiempo.

        Si los parámetros no son válidos se lanza ParametroInvalidoError y el
        simulador queda exactamente como estaba.
        """
        self._activa = self._construir_configuracion(parametros)

    def perturbar(self, sentido: float = 1.0) -> EstadoSimulacion:
        """Da un empujón: suma una velocidad angular al estado actual.

        sentido = 1 empuja hacia θ positivo y sentido = -1 hacia θ negativo.
        """
        if sentido not in (-1.0, 1.0):
            raise ParametroInvalidoError("sentido", sentido, "debe ser 1 o -1")
        velocidad = self._estado.velocidad_angular_rad_s + sentido * self._impulso_rad_s
        self._estado = replace(self._estado, velocidad_angular_rad_s=velocidad)
        return self._estado

    def reiniciar(self) -> EstadoSimulacion:
        """Vuelve al estado inicial (θ = 0, en reposo, t = 0). Conserva los parámetros."""
        self._estado = EstadoSimulacion.inicial()
        return self._estado

    # --- Internos ----------------------------------------------------------
    def _construir_configuracion(self, parametros: ParametrosPalanca) -> _Configuracion:
        """Calcula todo lo que depende de los parámetros (puede lanzar ParametroInvalidoError)."""
        resultados_estaticos = resolver_estatica(parametros, self._genero)
        modelo = ModeloDinamico.desde_parametros(parametros, self._genero)
        resultados_dinamicos = resolver_dinamica(parametros, self._genero)
        subpasos = self._calcular_subpasos(modelo)
        return _Configuracion(
            parametros=parametros,
            modelo=modelo,
            resultados_estaticos=resultados_estaticos,
            resultados_dinamicos=resultados_dinamicos,
            subpasos=subpasos,
            paso_s=self._duracion_cuadro_s / subpasos,
        )

    def _calcular_subpasos(self, modelo: ModeloDinamico) -> int:
        """Subpasos por cuadro: los nominales, o más si el modelo es muy rígido."""
        paso_estable_s = configuracion.FACTOR_ESTABILIDAD_PASO / modelo.rapidez_maxima_rad_s
        paso_maximo_s = min(configuracion.PASO_INTEGRACION_S, paso_estable_s)
        cociente = self._duracion_cuadro_s / paso_maximo_s
        return max(1, math.ceil(cociente - TOLERANCIA_REDONDEO_SUBPASOS))