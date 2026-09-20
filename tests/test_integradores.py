"""Pruebas de los integradores numéricos.

Referencia analítica: el modelo I = 4, τ = 50, k = 100, c = 20 tiene
ωn = 5, ζ = 0.5 y θ_eq = 0.5 rad. Partiendo del reposo en θ = 0, la
respuesta exacta (subamortiguada) es:

    θ(t) = θ_eq · [1 - e^(-ζ·ωn·t) · (cos(ωd·t) + ζ/√(1-ζ²) · sin(ωd·t))]
    con ωd = ωn·√(1-ζ²)
"""

import math

import pytest

from backend.dominio.dinamica import ModeloDinamico
from backend.dominio.excepciones import ParametroInvalidoError, SimulacionInestableError
from backend.dominio.modelos import EstadoSimulacion
from backend.simulacion.integradores import (
    Integrador,
    IntegradorEulerSemiimplicito,
    IntegradorRungeKutta4,
)

FACTOR_AMORTIGUAMIENTO = 0.5
FRECUENCIA_NATURAL_RAD_S = 5.0
ANGULO_EQUILIBRIO_RAD = 0.5


@pytest.fixture(params=[IntegradorRungeKutta4, IntegradorEulerSemiimplicito], ids=["rk4", "euler"])
def integrador(request) -> Integrador:
    """Cada prueba que use este fixture se ejecuta con los dos integradores."""
    return request.param()


@pytest.fixture
def modelo_simple() -> ModeloDinamico:
    """Modelo con números redondos: ωn = 5 y ζ = 0.5."""
    return ModeloDinamico(
        inercia_kg_m2=4.0,
        torque_neto_n_m=50.0,
        rigidez_n_m_rad=100.0,
        amortiguamiento_n_m_s_rad=20.0,
    )


def _estado_en_reposo() -> EstadoSimulacion:
    return EstadoSimulacion(angulo_rad=0.0, velocidad_angular_rad_s=0.0, tiempo_s=0.0)


def _angulo_analitico_rad(tiempo_s: float) -> float:
    """Solución exacta del modelo simple partiendo del reposo."""
    zeta = FACTOR_AMORTIGUAMIENTO
    frecuencia_amortiguada = FRECUENCIA_NATURAL_RAD_S * math.sqrt(1.0 - zeta**2)
    decaimiento = math.exp(-zeta * FRECUENCIA_NATURAL_RAD_S * tiempo_s)
    oscilacion = math.cos(frecuencia_amortiguada * tiempo_s) + (
        zeta / math.sqrt(1.0 - zeta**2)
    ) * math.sin(frecuencia_amortiguada * tiempo_s)
    return ANGULO_EQUILIBRIO_RAD * (1.0 - decaimiento * oscilacion)


def _simular(
    integrador: Integrador, modelo: ModeloDinamico, paso_s: float, duracion_s: float
) -> EstadoSimulacion:
    """Avanza la simulación desde el reposo durante duracion_s segundos."""
    estado = _estado_en_reposo()
    for _ in range(round(duracion_s / paso_s)):
        estado = integrador.paso(estado, modelo.aceleracion_angular, paso_s)
    return estado


# --- Contrato común (se ejecuta con RK4 y con Euler) ---------------------------
def test_integrador_abstracto_no_se_puede_instanciar():
    with pytest.raises(TypeError):
        Integrador()


def test_el_tiempo_avanza_un_paso(integrador):
    estado = EstadoSimulacion(angulo_rad=0.0, velocidad_angular_rad_s=0.0, tiempo_s=1.0)
    resultado = integrador.paso(estado, lambda angulo, velocidad: 0.0, 0.25)
    assert resultado.tiempo_s == pytest.approx(1.25)


@pytest.mark.parametrize("paso_invalido", [0.0, -0.01, float("nan"), float("inf")])
def test_rechaza_paso_invalido(integrador, paso_invalido):
    with pytest.raises(ParametroInvalidoError):
        integrador.paso(_estado_en_reposo(), lambda angulo, velocidad: 0.0, paso_invalido)


def test_detecta_simulacion_inestable(integrador):
    with pytest.raises(SimulacionInestableError):
        integrador.paso(_estado_en_reposo(), lambda angulo, velocidad: float("nan"), 0.01)


def test_no_modifica_la_marca_de_tope(integrador):
    estado = EstadoSimulacion(
        angulo_rad=0.1, velocidad_angular_rad_s=0.0, tiempo_s=0.0, en_tope=True
    )
    resultado = integrador.paso(estado, lambda angulo, velocidad: 0.0, 0.01)
    assert resultado.en_tope is True


# --- Precisión numérica --------------------------------------------------------
def test_rk4_es_exacto_con_aceleracion_constante():
    # Con a = 2 constante: ω = a·t = 2 y θ = a·t²/2 = 1 después de 1 s.
    resultado = IntegradorRungeKutta4().paso(
        _estado_en_reposo(), lambda angulo, velocidad: 2.0, 1.0
    )
    assert resultado.velocidad_angular_rad_s == pytest.approx(2.0)
    assert resultado.angulo_rad == pytest.approx(1.0)


def test_rk4_coincide_con_la_solucion_analitica(modelo_simple):
    resultado = _simular(IntegradorRungeKutta4(), modelo_simple, paso_s=0.01, duracion_s=1.0)
    assert resultado.tiempo_s == pytest.approx(1.0)
    assert resultado.angulo_rad == pytest.approx(_angulo_analitico_rad(1.0), abs=1e-5)


def test_euler_converge_a_la_solucion_analitica(modelo_simple):
    resultado = _simular(IntegradorEulerSemiimplicito(), modelo_simple, paso_s=0.001, duracion_s=1.0)
    assert resultado.angulo_rad == pytest.approx(_angulo_analitico_rad(1.0), abs=2e-2)


def test_rk4_es_mas_preciso_que_euler_con_el_mismo_paso(modelo_simple):
    exacto = _angulo_analitico_rad(1.0)
    error_rk4 = abs(
        _simular(IntegradorRungeKutta4(), modelo_simple, 0.01, 1.0).angulo_rad - exacto
    )
    error_euler = abs(
        _simular(IntegradorEulerSemiimplicito(), modelo_simple, 0.01, 1.0).angulo_rad - exacto
    )
    assert error_rk4 < error_euler