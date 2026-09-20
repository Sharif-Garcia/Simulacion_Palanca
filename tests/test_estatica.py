"""Pruebas de la estática de la palanca.

Los valores esperados salen del ejemplo numérico del taller:
m = 50 kg, g = 9.81 m/s², d_r = 0.5 m, d_e = 2 m
  W = 490.5 N, F_eq = 122.625 N, MA = 4, R = 613.125 N
"""

import pytest

from backend.dominio.estatica import (
    GENEROS_DISPONIBLES,
    PRIMER_GENERO,
    GeneroPalanca,
    PrimerGenero,
    calcular_fuerza_equilibrio_n,
    calcular_peso_n,
    calcular_torque_neto_n_m,
    calcular_ventaja_mecanica,
    resolver_estatica,
)
from backend.dominio.excepciones import ParametroInvalidoError
from backend.dominio.modelos import ParametrosPalanca

PESO_EJEMPLO_N = 490.5
FUERZA_EQUILIBRIO_EJEMPLO_N = 122.625


@pytest.fixture
def parametros_ejemplo() -> ParametrosPalanca:
    """Parámetros del ejemplo del taller, con la fuerza justa de equilibrio."""
    return ParametrosPalanca(
        masa_kg=50.0,
        distancia_carga_m=0.5,
        distancia_esfuerzo_m=2.0,
        fuerza_n=FUERZA_EQUILIBRIO_EJEMPLO_N,
        nombre_gravedad="Tierra",
    )


def test_peso_con_gravedad_terrestre():
    assert calcular_peso_n(50.0, 9.81) == pytest.approx(PESO_EJEMPLO_N)


def test_peso_con_gravedad_lunar():
    assert calcular_peso_n(50.0, 1.62) == pytest.approx(81.0)


def test_peso_rechaza_masa_no_positiva():
    with pytest.raises(ParametroInvalidoError):
        calcular_peso_n(0.0, 9.81)


def test_fuerza_equilibrio_del_ejemplo():
    resultado = calcular_fuerza_equilibrio_n(PESO_EJEMPLO_N, 0.5, 2.0)
    assert resultado == pytest.approx(FUERZA_EQUILIBRIO_EJEMPLO_N)


def test_fuerza_equilibrio_rechaza_distancia_esfuerzo_cero():
    with pytest.raises(ParametroInvalidoError):
        calcular_fuerza_equilibrio_n(PESO_EJEMPLO_N, 0.5, 0.0)


def test_ventaja_mecanica_del_ejemplo():
    assert calcular_ventaja_mecanica(0.5, 2.0) == pytest.approx(4.0)


def test_ventaja_mecanica_menor_que_uno_si_el_brazo_de_esfuerzo_es_corto():
    assert calcular_ventaja_mecanica(2.0, 0.5) == pytest.approx(0.25)


def test_ventaja_mecanica_rechaza_distancia_carga_cero():
    with pytest.raises(ParametroInvalidoError):
        calcular_ventaja_mecanica(0.0, 2.0)


def test_reaccion_primer_genero_es_esfuerzo_mas_peso():
    reaccion = PRIMER_GENERO.reaccion_fulcro_n(PESO_EJEMPLO_N, FUERZA_EQUILIBRIO_EJEMPLO_N)
    assert reaccion == pytest.approx(613.125)


def test_torque_nulo_en_equilibrio():
    torque = calcular_torque_neto_n_m(PESO_EJEMPLO_N, FUERZA_EQUILIBRIO_EJEMPLO_N, 0.5, 2.0)
    assert torque == pytest.approx(0.0, abs=1e-9)


def test_torque_positivo_si_el_esfuerzo_supera_al_equilibrio():
    # 200·2 - 490.5·0.5 = 154.75
    torque = calcular_torque_neto_n_m(PESO_EJEMPLO_N, 200.0, 0.5, 2.0)
    assert torque == pytest.approx(154.75)


def test_torque_negativo_si_el_esfuerzo_es_insuficiente():
    # 100·2 - 490.5·0.5 = -45.25
    torque = calcular_torque_neto_n_m(PESO_EJEMPLO_N, 100.0, 0.5, 2.0)
    assert torque == pytest.approx(-45.25)


def test_resolver_estatica_ejemplo_completo(parametros_ejemplo):
    resultados = resolver_estatica(parametros_ejemplo)
    assert resultados.peso_n == pytest.approx(PESO_EJEMPLO_N)
    assert resultados.fuerza_equilibrio_n == pytest.approx(FUERZA_EQUILIBRIO_EJEMPLO_N)
    assert resultados.ventaja_mecanica == pytest.approx(4.0)
    assert resultados.reaccion_fulcro_n == pytest.approx(613.125)


def test_genero_abstracto_no_se_puede_instanciar():
    with pytest.raises(TypeError):
        GeneroPalanca()


def test_registro_contiene_el_primer_genero():
    assert isinstance(GENEROS_DISPONIBLES["primer_genero"], PrimerGenero)