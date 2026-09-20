"""Estática de la palanca: peso, fuerza de equilibrio, ventaja mecánica y reacción.

Convención de signos del torque (coincide con la del ángulo θ):
  - Torque neto positivo: gana el esfuerzo, el lado del esfuerzo baja y la carga sube.
  - Torque neto negativo: gana la carga.
  - Torque neto cero: equilibrio.

Este módulo solo calcula: no valida rangos de la interfaz (eso lo hace
validadores.py), pero se protege de divisiones por cero.
"""

from abc import ABC, abstractmethod
from types import MappingProxyType

from backend.dominio.validadores import exigir_positivo
from backend.dominio.modelos import ParametrosPalanca, ResultadosEstaticos


class GeneroPalanca(ABC):
    """Contrato que debe cumplir cualquier género de palanca."""

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Nombre legible del género, para mostrar en la interfaz."""

    @abstractmethod
    def momento_esfuerzo_n_m(self, fuerza_n: float, distancia_esfuerzo_m: float) -> float:
        """Momento que produce el esfuerzo respecto al fulcro (positivo)."""

    @abstractmethod
    def momento_carga_n_m(self, peso_n: float, distancia_carga_m: float) -> float:
        """Momento que produce la carga respecto al fulcro (opuesto al del esfuerzo)."""

    @abstractmethod
    def reaccion_fulcro_n(self, peso_n: float, fuerza_n: float) -> float:
        """Fuerza de reacción que ejerce el apoyo sobre la barra."""

    def torque_neto_n_m(
        self,
        peso_n: float,
        fuerza_n: float,
        distancia_carga_m: float,
        distancia_esfuerzo_m: float,
    ) -> float:
        """Suma de momentos respecto al fulcro (igual para todos los géneros)."""
        return self.momento_esfuerzo_n_m(fuerza_n, distancia_esfuerzo_m) + self.momento_carga_n_m(
            peso_n, distancia_carga_m
        )


class PrimerGenero(GeneroPalanca):
    """Fulcro entre el esfuerzo y la carga (balancín, tijeras).

    Ambas fuerzas actúan hacia abajo y en lados opuestos del fulcro:
        ΣM_O = F·d_e - W·d_r
        ΣF_y = 0  =>  R = F + W
    """

    @property
    def nombre(self) -> str:
        return "Primer género"

    def momento_esfuerzo_n_m(self, fuerza_n: float, distancia_esfuerzo_m: float) -> float:
        return fuerza_n * distancia_esfuerzo_m

    def momento_carga_n_m(self, peso_n: float, distancia_carga_m: float) -> float:
        return -peso_n * distancia_carga_m

    def reaccion_fulcro_n(self, peso_n: float, fuerza_n: float) -> float:
        return fuerza_n + peso_n


PRIMER_GENERO = PrimerGenero()

# Registro de géneros disponibles. Solo lectura, igual que las tablas de configuracion.py.
GENEROS_DISPONIBLES = MappingProxyType({"primer_genero": PRIMER_GENERO})




def calcular_peso_n(masa_kg: float, gravedad_m_s2: float) -> float:
    """Peso de la carga: W = m·g."""
    exigir_positivo("masa_kg", masa_kg)
    exigir_positivo("gravedad_m_s2", gravedad_m_s2)
    return masa_kg * gravedad_m_s2


def calcular_fuerza_equilibrio_n(
    peso_n: float,
    distancia_carga_m: float,
    distancia_esfuerzo_m: float,
    genero: GeneroPalanca = PRIMER_GENERO,
) -> float:
    """Fuerza mínima que anula el torque neto: F_eq = |momento de la carga| / d_e."""
    exigir_positivo("distancia_esfuerzo_m", distancia_esfuerzo_m)
    momento_carga = abs(genero.momento_carga_n_m(peso_n, distancia_carga_m))
    return momento_carga / distancia_esfuerzo_m


def calcular_ventaja_mecanica(distancia_carga_m: float, distancia_esfuerzo_m: float) -> float:
    """Ventaja mecánica ideal: MA = d_e / d_r (igual a W / F en equilibrio)."""
    exigir_positivo("distancia_carga_m", distancia_carga_m)
    exigir_positivo("distancia_esfuerzo_m", distancia_esfuerzo_m)
    return distancia_esfuerzo_m / distancia_carga_m


def calcular_torque_neto_n_m(
    peso_n: float,
    fuerza_n: float,
    distancia_carga_m: float,
    distancia_esfuerzo_m: float,
    genero: GeneroPalanca = PRIMER_GENERO,
) -> float:
    """Torque neto respecto al fulcro. dinamica.py reutiliza esta función (DRY)."""
    return genero.torque_neto_n_m(peso_n, fuerza_n, distancia_carga_m, distancia_esfuerzo_m)


def resolver_estatica(
    parametros: ParametrosPalanca,
    genero: GeneroPalanca = PRIMER_GENERO,
) -> ResultadosEstaticos:
    """Resuelve el equilibrio estático completo para unos parámetros dados."""
    peso_n = calcular_peso_n(parametros.masa_kg, parametros.gravedad_m_s2)
    return ResultadosEstaticos(
        peso_n=peso_n,
        fuerza_equilibrio_n=calcular_fuerza_equilibrio_n(
            peso_n, parametros.distancia_carga_m, parametros.distancia_esfuerzo_m, genero
        ),
        ventaja_mecanica=calcular_ventaja_mecanica(
            parametros.distancia_carga_m, parametros.distancia_esfuerzo_m
        ),
        reaccion_fulcro_n=genero.reaccion_fulcro_n(peso_n, parametros.fuerza_n),
    )