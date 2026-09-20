"""Integradores numéricos: avanzan el estado de la palanca un paso en el tiempo.

Diseño:
  - Integrador es el contrato: recibe un estado, una función de aceleración y
    un paso dt, y devuelve un estado NUEVO.
  - IntegradorRungeKutta4 es el integrador principal (precisión de 4.º orden).
  - IntegradorEulerSemiimplicito es una alternativa simple (1.er orden). Existe
    para demostrar que el simulador acepta cualquier integrador que cumpla el
    contrato, y para comparar precisión en la exposición.

El integrador NO conoce la física: recibe la aceleración como una función
(por ejemplo ModeloDinamico.aceleracion_angular). Tampoco aplica el tope de
±30°, que es una restricción del movimiento y le corresponde al simulador.

Sistema que se integra (dos ecuaciones de primer orden):
    dθ/dt = ω
    dω/dt = aceleracion(θ, ω)
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import replace

from backend.dominio.excepciones import SimulacionInestableError
from backend.dominio.modelos import EstadoSimulacion
from backend.dominio.validadores import convertir_a_numero_finito, exigir_positivo

# Función que recibe (ángulo en rad, velocidad angular en rad/s) y devuelve
# la aceleración angular en rad/s².
FuncionAceleracion = Callable[[float, float], float]


class Integrador(ABC):
    """Contrato de un integrador numérico.

    El método público paso() valida el dt, delega la fórmula numérica a las
    subclases y comprueba que el resultado sea finito. Así esas tres tareas
    se escriben una sola vez (DRY) y cada subclase solo aporta su fórmula.
    """

    def paso(
        self, estado: EstadoSimulacion, aceleracion: FuncionAceleracion, paso_s: float
    ) -> EstadoSimulacion:
        """Avanza el estado un intervalo paso_s y devuelve un estado nuevo.

        Solo cambian el ángulo, la velocidad y el tiempo. Los demás campos
        (por ejemplo en_tope) se copian tal cual.

        Lanza ParametroInvalidoError si paso_s no es un número finito positivo
        y SimulacionInestableError si el resultado no es finito.
        """
        paso_s = self._validar_paso(paso_s)
        angulo_rad, velocidad_rad_s = self._avanzar(
            estado.angulo_rad, estado.velocidad_angular_rad_s, aceleracion, paso_s
        )
        if not (math.isfinite(angulo_rad) and math.isfinite(velocidad_rad_s)):
            raise SimulacionInestableError()
        return replace(
            estado,
            angulo_rad=angulo_rad,
            velocidad_angular_rad_s=velocidad_rad_s,
            tiempo_s=estado.tiempo_s + paso_s,
        )

    @staticmethod
    def _validar_paso(paso_s: float) -> float:
        """Exige un paso de integración numérico, finito y mayor que cero."""
        numero = convertir_a_numero_finito("paso_integracion_s", paso_s)
        return exigir_positivo("paso_integracion_s", numero)

    @abstractmethod
    def _avanzar(
        self,
        angulo_rad: float,
        velocidad_rad_s: float,
        aceleracion: FuncionAceleracion,
        paso_s: float,
    ) -> tuple[float, float]:
        """Fórmula numérica: devuelve (ángulo nuevo, velocidad nueva)."""


class IntegradorRungeKutta4(Integrador):
    """Runge-Kutta clásico de 4.º orden (RK4).

    Evalúa la pendiente en 4 puntos del intervalo y promedia con pesos
    1-2-2-1. Error local del orden de dt⁵: mucho más preciso que Euler con
    el mismo dt.
    """

    def _avanzar(
        self,
        angulo_rad: float,
        velocidad_rad_s: float,
        aceleracion: FuncionAceleracion,
        paso_s: float,
    ) -> tuple[float, float]:
        mitad = paso_s / 2.0

        # Pendiente 1: al inicio del intervalo.
        k1_angulo = velocidad_rad_s
        k1_velocidad = aceleracion(angulo_rad, velocidad_rad_s)

        # Pendiente 2: a la mitad, usando la pendiente 1.
        k2_angulo = velocidad_rad_s + mitad * k1_velocidad
        k2_velocidad = aceleracion(
            angulo_rad + mitad * k1_angulo, velocidad_rad_s + mitad * k1_velocidad
        )

        # Pendiente 3: a la mitad, usando la pendiente 2.
        k3_angulo = velocidad_rad_s + mitad * k2_velocidad
        k3_velocidad = aceleracion(
            angulo_rad + mitad * k2_angulo, velocidad_rad_s + mitad * k2_velocidad
        )

        # Pendiente 4: al final del intervalo, usando la pendiente 3.
        k4_angulo = velocidad_rad_s + paso_s * k3_velocidad
        k4_velocidad = aceleracion(
            angulo_rad + paso_s * k3_angulo, velocidad_rad_s + paso_s * k3_velocidad
        )

        sexto = paso_s / 6.0
        angulo_nuevo = angulo_rad + sexto * (k1_angulo + 2.0 * k2_angulo + 2.0 * k3_angulo + k4_angulo)
        velocidad_nueva = velocidad_rad_s + sexto * (
            k1_velocidad + 2.0 * k2_velocidad + 2.0 * k3_velocidad + k4_velocidad
        )
        return angulo_nuevo, velocidad_nueva


class IntegradorEulerSemiimplicito(Integrador):
    """Euler semiimplícito (simpléctico): actualiza ω primero y luego θ con la ω nueva.

    Es de 1.er orden, pero más estable que el Euler explícito en sistemas
    que oscilan.
    """

    def _avanzar(
        self,
        angulo_rad: float,
        velocidad_rad_s: float,
        aceleracion: FuncionAceleracion,
        paso_s: float,
    ) -> tuple[float, float]:
        velocidad_nueva = velocidad_rad_s + aceleracion(angulo_rad, velocidad_rad_s) * paso_s
        angulo_nuevo = angulo_rad + velocidad_nueva * paso_s
        return angulo_nuevo, velocidad_nueva