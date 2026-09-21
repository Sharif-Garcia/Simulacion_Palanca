"""Pruebas de la dinámica de la palanca.

Se usan números redondos siempre que es posible: con k = 100 e I = 4,
ωn = √(100/4) = 5 y ζ = c / (2·√(k·I)) = c / 40.
"""

import dataclasses

import pytest

from backend import configuracion
from backend.dominio.dinamica import (
    ModeloDinamico,
    calcular_factor_amortiguamiento,
    calcular_frecuencia_natural_rad_s,
    calcular_inercia_kg_m2,
    calcular_masa_amortiguamiento_critico,
    calcular_rapidez_maxima_rad_s,
    calcular_sobreimpulso_porcentaje,
    calcular_tiempo_establecimiento_s,
    clasificar_estado,
    clasificar_respuesta,
    resolver_dinamica,
)
from backend.dominio.excepciones import ParametroInvalidoError
from backend.dominio.modelos import EstadoPalanca, ParametrosPalanca, TipoRespuesta

INERCIA_EJEMPLO_KG_M2 = 215.0 / 12.0  # barra de 5 kg + carga de 50 kg a 0.5 m


@pytest.fixture
def parametros_ejemplo() -> ParametrosPalanca:
    """Ejemplo del taller con la fuerza justa de equilibrio."""
    return ParametrosPalanca(
        masa_kg=50.0,
        distancia_carga_m=0.5,
        distancia_esfuerzo_m=2.0,
        fuerza_n=122.625,
        nombre_gravedad="Tierra",
        nombre_genero="primer_genero",
    )


@pytest.fixture
def modelo_simple() -> ModeloDinamico:
    """Modelo con números redondos: I = 4, τ = 50, k = 100, c = 20 (ζ = 0.5)."""
    return ModeloDinamico(
        inercia_kg_m2=4.0,
        torque_neto_n_m=50.0,
        rigidez_n_m_rad=100.0,
        amortiguamiento_n_m_s_rad=20.0,
    )


# --- Inercia ---------------------------------------------------------------
def test_inercia_de_barra_centrada():
    # Barra de 6 kg y 2 m centrada en el fulcro: 6·4/12 = 2. Carga: 2·1² = 2.
    assert calcular_inercia_kg_m2(2.0, 1.0, 1.0, masa_barra_kg=6.0) == pytest.approx(4.0)


def test_inercia_del_ejemplo():
    resultado = calcular_inercia_kg_m2(50.0, 0.5, 2.0, masa_barra_kg=5.0)
    assert resultado == pytest.approx(INERCIA_EJEMPLO_KG_M2)


def test_inercia_rechaza_masa_no_positiva():
    with pytest.raises(ParametroInvalidoError):
        calcular_inercia_kg_m2(0.0, 0.5, 2.0)


# --- ωn y ζ ----------------------------------------------------------------
def test_frecuencia_natural():
    assert calcular_frecuencia_natural_rad_s(100.0, 4.0) == pytest.approx(5.0)


def test_factor_amortiguamiento():
    assert calcular_factor_amortiguamiento(20.0, 100.0, 4.0) == pytest.approx(0.5)


# --- Masa que produce amortiguamiento crítico (ζ = 1) ------------------------
def test_masa_amortiguamiento_critico_da_zeta_uno():
    # Barra centrada (d_r = d_e = 1 m) de 3 kg: I_barra = 3·2²/12 = 1.
    # k = 100, c = 40 => I_crítica = c² / (4·k) = 1600/400 = 4 =>
    # masa = (I_crítica - I_barra) / d_r² = (4 - 1) / 1² = 3 kg.
    masa_kg = calcular_masa_amortiguamiento_critico(
        distancia_carga_m=1.0,
        distancia_esfuerzo_m=1.0,
        masa_barra_kg=3.0,
        rigidez_n_m_rad=100.0,
        amortiguamiento_n_m_s_rad=40.0,
    )
    assert masa_kg == pytest.approx(3.0)

    inercia = calcular_inercia_kg_m2(masa_kg, 1.0, 1.0, masa_barra_kg=3.0)
    assert calcular_factor_amortiguamiento(40.0, 100.0, inercia) == pytest.approx(1.0)


def test_masa_amortiguamiento_critico_con_constantes_por_defecto_cabe_en_el_rango():
    # Con las distancias iniciales y las constantes k, c de configuracion.py,
    # la masa crítica debe caer dentro del rango permitido del slider.
    rangos = configuracion.RANGOS_PARAMETROS
    masa_kg = calcular_masa_amortiguamiento_critico(
        rangos["distancia_carga_m"].valor_inicial,
        rangos["distancia_esfuerzo_m"].valor_inicial,
    )
    assert rangos["masa_kg"].contiene(masa_kg)


def test_masa_amortiguamiento_critico_rechaza_distancia_no_positiva():
    with pytest.raises(ParametroInvalidoError):
        calcular_masa_amortiguamiento_critico(0.0, 2.0)


# --- Clasificación de la respuesta ----------------------------------------
@pytest.mark.parametrize(
    ("factor", "esperado"),
    [
        (0.5, TipoRespuesta.SUBAMORTIGUADA),
        (0.99, TipoRespuesta.SUBAMORTIGUADA),
        (1.0, TipoRespuesta.CRITICA),
        (1.0005, TipoRespuesta.CRITICA),
        (1.5, TipoRespuesta.SOBREAMORTIGUADA),
        (2.0, TipoRespuesta.SOBREAMORTIGUADA),
    ],
)
def test_clasificar_respuesta(factor, esperado):
    assert clasificar_respuesta(factor) is esperado


# --- Sobreimpulso ------------------------------------------------------------
def test_sobreimpulso_con_zeta_medio():
    # Valor de referencia conocido: ζ = 0.5 da aproximadamente 16.3 %.
    assert calcular_sobreimpulso_porcentaje(0.5) == pytest.approx(16.303, abs=0.01)


@pytest.mark.parametrize("factor", [1.0, 2.0])
def test_sobreimpulso_es_cero_si_no_oscila(factor):
    assert calcular_sobreimpulso_porcentaje(factor) == 0.0


# --- Tiempo de establecimiento ----------------------------------------------
def test_tiempo_establecimiento_subamortiguada():
    # 4 / (0.5 · 5) = 1.6 s
    assert calcular_tiempo_establecimiento_s(0.5, 5.0) == pytest.approx(1.6)


def test_tiempo_establecimiento_critica():
    # 5.83 / 5 = 1.166 s
    assert calcular_tiempo_establecimiento_s(1.0, 5.0) == pytest.approx(1.166)


def test_tiempo_establecimiento_sobreamortiguada():
    # 4·(2 + √3) / 5 ≈ 2.9856 s
    assert calcular_tiempo_establecimiento_s(2.0, 5.0) == pytest.approx(2.98564, abs=1e-4)


# --- Estado de la palanca ----------------------------------------------------
@pytest.mark.parametrize(
    ("torque", "esperado"),
    [
        (0.0, EstadoPalanca.EQUILIBRIO),
        (0.4, EstadoPalanca.EQUILIBRIO),
        (-0.4, EstadoPalanca.EQUILIBRIO),
        (10.0, EstadoPalanca.CARGA_SUBE),
        (-10.0, EstadoPalanca.CARGA_BAJA),
    ],
)
def test_clasificar_estado(torque, esperado):
    assert clasificar_estado(torque) is esperado


# --- Modelo dinámico ----------------------------------------------------------
def test_aceleracion_desde_reposo(modelo_simple):
    # (50 - 0 - 0) / 4 = 12.5 rad/s²
    assert modelo_simple.aceleracion_angular(0.0, 0.0) == pytest.approx(12.5)


def test_aceleracion_nula_en_el_angulo_de_equilibrio(modelo_simple):
    # θ_eq = 50 / 100 = 0.5 rad: allí el resorte iguala al torque.
    assert modelo_simple.angulo_equilibrio_rad == pytest.approx(0.5)
    assert modelo_simple.aceleracion_angular(0.5, 0.0) == pytest.approx(0.0)


def test_aceleracion_descuenta_el_amortiguamiento(modelo_simple):
    # (50 - 20·2 - 0) / 4 = 2.5 rad/s²
    assert modelo_simple.aceleracion_angular(0.0, 2.0) == pytest.approx(2.5)


def test_modelo_desde_parametros_del_ejemplo(parametros_ejemplo):
    modelo = ModeloDinamico.desde_parametros(parametros_ejemplo)
    assert modelo.inercia_kg_m2 == pytest.approx(INERCIA_EJEMPLO_KG_M2)
    assert modelo.torque_neto_n_m == pytest.approx(0.0, abs=1e-9)
    assert modelo.rigidez_n_m_rad == configuracion.RIGIDEZ_RESTAURADORA_N_M_RAD
    assert modelo.amortiguamiento_n_m_s_rad == configuracion.AMORTIGUAMIENTO_N_M_S_RAD


def test_modelo_rechaza_rigidez_no_positiva(parametros_ejemplo):
    with pytest.raises(ParametroInvalidoError):
        ModeloDinamico.desde_parametros(parametros_ejemplo, rigidez_n_m_rad=0.0)


def test_modelo_es_inmutable(modelo_simple):
    with pytest.raises(dataclasses.FrozenInstanceError):
        modelo_simple.inercia_kg_m2 = 1.0


# --- Resolución completa -------------------------------------------------------
def test_resolver_dinamica_del_ejemplo(parametros_ejemplo):
    resultados = resolver_dinamica(parametros_ejemplo)
    assert resultados.inercia_kg_m2 == pytest.approx(INERCIA_EJEMPLO_KG_M2)
    assert resultados.estado is EstadoPalanca.EQUILIBRIO
    assert resultados.frecuencia_natural_rad_s == pytest.approx(7.4709, abs=1e-3)
    assert resultados.factor_amortiguamiento == pytest.approx(0.6537, abs=1e-3)
    assert resultados.tipo_respuesta is TipoRespuesta.SUBAMORTIGUADA
    assert 5.0 < resultados.sobreimpulso_porcentaje < 10.0


# --- Las constantes k y c de configuracion.py deben dar buen comportamiento ----
def test_parametros_por_defecto_dan_respuesta_subamortiguada():
    resultados = resolver_dinamica(ParametrosPalanca.por_defecto())
    assert resultados.tipo_respuesta is TipoRespuesta.SUBAMORTIGUADA


def test_extremo_ligero_es_sobreamortiguado():
    parametros = ParametrosPalanca(
        masa_kg=1.0,
        distancia_carga_m=0.1,
        distancia_esfuerzo_m=0.1,
        fuerza_n=0.0,
        nombre_gravedad="Tierra",
        nombre_genero="primer_genero",
    )
    assert resolver_dinamica(parametros).tipo_respuesta is TipoRespuesta.SOBREAMORTIGUADA


def test_extremo_pesado_es_subamortiguado():
    parametros = ParametrosPalanca(
        masa_kg=200.0,
        distancia_carga_m=3.0,
        distancia_esfuerzo_m=5.0,
        fuerza_n=1000.0,
        nombre_gravedad="Tierra",
        nombre_genero="primer_genero",
    )
    assert resolver_dinamica(parametros).tipo_respuesta is TipoRespuesta.SUBAMORTIGUADA

    # --- Rapidez máxima (base para elegir un paso de integración estable) ----------
def test_rapidez_maxima_subamortiguada_es_la_frecuencia_natural():
    assert calcular_rapidez_maxima_rad_s(0.5, 5.0) == pytest.approx(5.0)


def test_rapidez_maxima_sobreamortiguada():
    # 5·(2 + √3) = 18.6603
    assert calcular_rapidez_maxima_rad_s(2.0, 5.0) == pytest.approx(18.6603, abs=1e-3)


def test_rapidez_maxima_del_extremo_ligero():
    parametros = ParametrosPalanca(
        masa_kg=1.0,
        distancia_carga_m=0.1,
        distancia_esfuerzo_m=0.1,
        fuerza_n=0.0,
        nombre_gravedad="Tierra",
        nombre_genero="primer_genero",
    )
    modelo = ModeloDinamico.desde_parametros(parametros)
    # Polo rápido de s² + 6562.5·s + 37500 = 0: aproximadamente 6556.78 rad/s.
    assert modelo.rapidez_maxima_rad_s == pytest.approx(6556.78, abs=0.1)