"""Pruebas del simulador y del tope mecánico.

Valores de referencia (ejemplo del taller: m = 50 kg, d_r = 0.5 m, d_e = 2 m,
g = 9.81 m/s², W = 490.5 N, I = 17.9167 kg·m², k = 1000 N·m/rad):
  - F = 200 N  => τ = 154.75 N·m  => θ_eq = 0.15475 rad
  - F = 100 N  => τ = -45.25 N·m  => θ_eq = -0.04525 rad
  - F = 1000 N => τ = 1754.75 N·m => θ_eq = 1.75 rad, mayor que el tope (0.5236 rad)
"""

import math
from dataclasses import replace

import pytest

from backend import configuracion
from backend.dominio.excepciones import ParametroInvalidoError, SimulacionInestableError
from backend.dominio.modelos import EstadoPalanca, EstadoSimulacion, ParametrosPalanca
from backend.simulacion.integradores import (
    Integrador,
    IntegradorEulerSemiimplicito,
    IntegradorRungeKutta4,
)
from backend.simulacion.simulador import LIMITE_ANGULO_RAD, Simulador, aplicar_tope_mecanico

CUADROS_POR_SEGUNDO = configuracion.FRECUENCIA_CUADROS_HZ


class IntegradorContador(Integrador):
    """Integrador falso: no mueve nada y cuenta cuántas veces lo llaman."""

    def __init__(self) -> None:
        self.llamadas = 0

    def _avanzar(self, angulo_rad, velocidad_rad_s, aceleracion, paso_s):
        self.llamadas += 1
        return angulo_rad, velocidad_rad_s


class IntegradorInestable(Integrador):
    """Integrador falso: siempre produce un valor no finito."""

    def _avanzar(self, angulo_rad, velocidad_rad_s, aceleracion, paso_s):
        return float("nan"), 0.0


@pytest.fixture
def parametros_base() -> ParametrosPalanca:
    """Ejemplo del taller con la fuerza justa de equilibrio."""
    return ParametrosPalanca(
        masa_kg=50.0,
        distancia_carga_m=0.5,
        distancia_esfuerzo_m=2.0,
        fuerza_n=122.625,
        nombre_gravedad="Tierra",
    )


def _simular_segundos(simulador: Simulador, segundos: float) -> EstadoSimulacion:
    """Avanza la simulación el tiempo indicado y devuelve el último estado."""
    estado = simulador.estado
    for _ in range(round(segundos * CUADROS_POR_SEGUNDO)):
        estado = simulador.avanzar_cuadro()
    return estado


# --- Tope mecánico (función pura) ---------------------------------------------
def test_tope_no_actua_dentro_del_rango():
    estado = EstadoSimulacion(angulo_rad=0.2, velocidad_angular_rad_s=1.5, tiempo_s=3.0)
    resultado = aplicar_tope_mecanico(estado, LIMITE_ANGULO_RAD)
    assert resultado.angulo_rad == 0.2
    assert resultado.velocidad_angular_rad_s == 1.5
    assert resultado.en_tope is False


def test_tope_superior_detiene_la_barra():
    estado = EstadoSimulacion(angulo_rad=0.6, velocidad_angular_rad_s=2.0, tiempo_s=0.0)
    resultado = aplicar_tope_mecanico(estado, LIMITE_ANGULO_RAD)
    assert resultado.angulo_rad == pytest.approx(LIMITE_ANGULO_RAD)
    assert resultado.velocidad_angular_rad_s == 0.0
    assert resultado.en_tope is True


def test_tope_inferior_detiene_la_barra():
    estado = EstadoSimulacion(angulo_rad=-0.6, velocidad_angular_rad_s=-2.0, tiempo_s=0.0)
    resultado = aplicar_tope_mecanico(estado, LIMITE_ANGULO_RAD)
    assert resultado.angulo_rad == pytest.approx(-LIMITE_ANGULO_RAD)
    assert resultado.velocidad_angular_rad_s == 0.0
    assert resultado.en_tope is True


def test_tope_conserva_la_velocidad_si_la_barra_se_aleja():
    estado = EstadoSimulacion(angulo_rad=0.6, velocidad_angular_rad_s=-1.0, tiempo_s=0.0)
    resultado = aplicar_tope_mecanico(estado, LIMITE_ANGULO_RAD)
    assert resultado.velocidad_angular_rad_s == -1.0
    assert resultado.en_tope is True


def test_tope_conserva_el_tiempo():
    estado = EstadoSimulacion(angulo_rad=0.6, velocidad_angular_rad_s=2.0, tiempo_s=7.5)
    assert aplicar_tope_mecanico(estado, LIMITE_ANGULO_RAD).tiempo_s == 7.5


def test_tope_apaga_la_marca_si_la_barra_ya_esta_dentro_del_rango():
    estado = EstadoSimulacion(
        angulo_rad=0.1, velocidad_angular_rad_s=0.0, tiempo_s=0.0, en_tope=True
    )
    assert aplicar_tope_mecanico(estado, LIMITE_ANGULO_RAD).en_tope is False


# --- Comportamiento básico ------------------------------------------------------
def test_estado_inicial(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)
    assert simulador.estado == EstadoSimulacion.inicial()
    assert simulador.parametros == parametros_base


def test_un_cuadro_avanza_un_sesentavo_de_segundo(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)
    assert simulador.avanzar_cuadro().tiempo_s == pytest.approx(1.0 / CUADROS_POR_SEGUNDO)


def test_equilibrio_se_mantiene_quieto():
    simulador = Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto())
    estado = _simular_segundos(simulador, 1.0)
    assert abs(estado.angulo_rad) < 1e-3
    assert abs(estado.velocidad_angular_rad_s) < 1e-3


def test_torque_positivo_se_estabiliza_en_tau_sobre_k(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), replace(parametros_base, fuerza_n=200.0))
    estado = _simular_segundos(simulador, 10.0)
    assert estado.angulo_rad == pytest.approx(0.15475, abs=1e-4)
    assert estado.en_tope is False


def test_torque_negativo_se_estabiliza_en_tau_sobre_k(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), replace(parametros_base, fuerza_n=100.0))
    estado = _simular_segundos(simulador, 10.0)
    assert estado.angulo_rad == pytest.approx(-0.04525, abs=1e-4)


# --- Tope dentro de la simulación -----------------------------------------------
def test_tope_superior_nunca_se_supera(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), replace(parametros_base, fuerza_n=1000.0))
    for _ in range(5 * CUADROS_POR_SEGUNDO):
        estado = simulador.avanzar_cuadro()
        assert abs(estado.angulo_rad) <= LIMITE_ANGULO_RAD + 1e-12
    assert estado.en_tope is True
    assert estado.angulo_rad == pytest.approx(LIMITE_ANGULO_RAD)
    assert estado.velocidad_angular_rad_s == 0.0


def test_tope_inferior_se_alcanza_con_carga_pesada():
    parametros = ParametrosPalanca(
        masa_kg=200.0,
        distancia_carga_m=3.0,
        distancia_esfuerzo_m=5.0,
        fuerza_n=0.0,
        nombre_gravedad="Tierra",
    )
    simulador = Simulador(IntegradorRungeKutta4(), parametros)
    estado = _simular_segundos(simulador, 5.0)
    assert estado.angulo_rad == pytest.approx(-LIMITE_ANGULO_RAD)
    assert estado.en_tope is True
    assert estado.velocidad_angular_rad_s == 0.0


def test_la_barra_se_despega_del_tope_al_invertirse_el_torque(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), replace(parametros_base, fuerza_n=1000.0))
    assert _simular_segundos(simulador, 2.0).en_tope is True

    simulador.actualizar_parametros(replace(parametros_base, fuerza_n=0.0))
    estado = simulador.avanzar_cuadro()

    assert estado.en_tope is False
    assert estado.angulo_rad < LIMITE_ANGULO_RAD


# --- Perturbación ------------------------------------------------------------------
def test_perturbacion_agrega_velocidad_angular():
    simulador = Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto())
    estado = simulador.perturbar()
    assert estado.velocidad_angular_rad_s == pytest.approx(configuracion.IMPULSO_PERTURBACION_RAD_S)
    assert simulador.estado == estado


def test_perturbacion_en_sentido_negativo():
    simulador = Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto())
    estado = simulador.perturbar(sentido=-1.0)
    assert estado.velocidad_angular_rad_s == pytest.approx(-configuracion.IMPULSO_PERTURBACION_RAD_S)


@pytest.mark.parametrize("sentido_invalido", [0.0, 2.0, float("nan")])
def test_perturbacion_rechaza_sentido_invalido(sentido_invalido):
    simulador = Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto())
    with pytest.raises(ParametroInvalidoError):
        simulador.perturbar(sentido=sentido_invalido)


def test_perturbacion_oscila_y_se_estabiliza():
    simulador = Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto())
    simulador.perturbar()

    angulo_maximo = 0.0
    for _ in range(CUADROS_POR_SEGUNDO):  # primer segundo
        angulo_maximo = max(angulo_maximo, simulador.avanzar_cuadro().angulo_rad)
    # Respuesta al impulso con ζ ≈ 0.30 y ωn ≈ 7.47: pico cercano a 0.09 rad.
    assert 0.05 < angulo_maximo < 0.15

    estado = _simular_segundos(simulador, 10.0)
    assert abs(estado.angulo_rad) < 1e-3


# --- Reinicio y cambio de parámetros ----------------------------------------------
def test_reiniciar_vuelve_al_estado_inicial_y_conserva_los_parametros(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)
    simulador.perturbar()
    _simular_segundos(simulador, 0.5)

    simulador.reiniciar()

    assert simulador.estado == EstadoSimulacion.inicial()
    assert simulador.parametros == parametros_base


def test_cambio_de_parametros_conserva_el_estado(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)
    simulador.perturbar()
    _simular_segundos(simulador, 0.3)
    estado_antes = simulador.estado

    simulador.actualizar_parametros(replace(parametros_base, masa_kg=80.0))

    assert simulador.estado == estado_antes


def test_cambio_de_parametros_actualiza_los_resultados(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)

    simulador.actualizar_parametros(replace(parametros_base, masa_kg=80.0))

    assert simulador.resultados_estaticos.peso_n == pytest.approx(784.8)
    assert simulador.resultados_dinamicos.estado is EstadoPalanca.CARGA_BAJA


def test_parametros_invalidos_no_alteran_el_simulador(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)
    subpasos_antes = simulador.subpasos_por_cuadro

    with pytest.raises(ParametroInvalidoError):
        simulador.actualizar_parametros(replace(parametros_base, masa_kg=0.0))

    assert simulador.parametros == parametros_base
    assert simulador.subpasos_por_cuadro == subpasos_antes


@pytest.mark.parametrize("duracion_invalida", [0.0, -1.0])
def test_constructor_rechaza_duracion_de_cuadro_invalida(parametros_base, duracion_invalida):
    with pytest.raises(ParametroInvalidoError):
        Simulador(IntegradorRungeKutta4(), parametros_base, duracion_cuadro_s=duracion_invalida)


# --- Estabilidad numérica: subpasos adaptativos ------------------------------------
def test_con_parametros_normales_se_usan_cuatro_subpasos(parametros_base):
    simulador = Simulador(IntegradorRungeKutta4(), parametros_base)
    assert simulador.subpasos_por_cuadro == configuracion.SUBPASOS_POR_CUADRO


def test_barra_ligera_usa_mas_subpasos_y_se_mantiene_estable():
    ligeros = ParametrosPalanca(
        masa_kg=1.0,
        distancia_carga_m=0.1,
        distancia_esfuerzo_m=0.1,
        fuerza_n=0.0,
        nombre_gravedad="Tierra",
    )
    simulador = Simulador(IntegradorRungeKutta4(), ligeros)
    assert simulador.subpasos_por_cuadro > configuracion.SUBPASOS_POR_CUADRO

    estado = _simular_segundos(simulador, 2.0)  # sin SimulacionInestableError
    # τ = -9.81·0.1 = -0.981 N·m  =>  θ_eq = -0.000981 rad
    assert estado.angulo_rad == pytest.approx(-9.81e-4, abs=1e-6)


def test_los_subpasos_vuelven_a_cuatro_al_cambiar_a_parametros_normales(parametros_base):
    ligeros = replace(parametros_base, masa_kg=1.0, distancia_carga_m=0.1, distancia_esfuerzo_m=0.1)
    simulador = Simulador(IntegradorRungeKutta4(), ligeros)
    assert simulador.subpasos_por_cuadro > configuracion.SUBPASOS_POR_CUADRO

    simulador.actualizar_parametros(parametros_base)

    assert simulador.subpasos_por_cuadro == configuracion.SUBPASOS_POR_CUADRO


# --- Inyección de dependencias ------------------------------------------------------
def test_acepta_cualquier_integrador_que_cumpla_el_contrato():
    simulador = Simulador(IntegradorEulerSemiimplicito(), ParametrosPalanca.por_defecto())
    assert simulador.avanzar_cuadro().tiempo_s == pytest.approx(1.0 / CUADROS_POR_SEGUNDO)


def test_llama_al_integrador_una_vez_por_subpaso(parametros_base):
    integrador = IntegradorContador()
    simulador = Simulador(integrador, parametros_base)
    simulador.avanzar_cuadro()
    assert integrador.llamadas == simulador.subpasos_por_cuadro


def test_un_error_de_inestabilidad_no_altera_el_estado(parametros_base):
    simulador = Simulador(IntegradorInestable(), parametros_base)
    estado_antes = simulador.estado

    with pytest.raises(SimulacionInestableError):
        simulador.avanzar_cuadro()

    assert simulador.estado == estado_antes