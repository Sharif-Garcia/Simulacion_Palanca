"""Pruebas de la sesión: un simulador por cliente, sin red."""

import json

import pytest

from backend import configuracion
from backend.api.sesion import Sesion
from backend.dominio.modelos import ParametrosPalanca
from backend.simulacion.integradores import Integrador, IntegradorRungeKutta4
from backend.simulacion.simulador import Simulador

CUADROS_POR_SEGUNDO = configuracion.FRECUENCIA_CUADROS_HZ

PARAMETROS_JSON = {
    "masa_kg": 50,
    "distancia_carga_m": 0.5,
    "distancia_esfuerzo_m": 2,
    "fuerza_n": 122.6,
    "nombre_gravedad": "Tierra",
}


class IntegradorInestable(Integrador):
    """Integrador falso: siempre produce un valor no finito."""

    def _avanzar(self, angulo_rad, velocidad_rad_s, aceleracion, paso_s):
        return float("nan"), 0.0


@pytest.fixture
def simulador() -> Simulador:
    return Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto())


@pytest.fixture
def sesion(simulador) -> Sesion:
    return Sesion(simulador)


def _leer(respuestas: list[str]) -> list[dict]:
    """Convierte los textos JSON de la sesión en diccionarios."""
    return [json.loads(texto) for texto in respuestas]


def _mensaje_parametros(**cambios) -> str:
    """Texto JSON de un mensaje 'parametros' con los cambios indicados."""
    return json.dumps({"tipo": "parametros", "parametros": {**PARAMETROS_JSON, **cambios}})


# --- Al conectar -----------------------------------------------------------------
def test_mensajes_iniciales_son_resultados_y_estado(sesion):
    resultados, estado = _leer(sesion.mensajes_iniciales())
    assert resultados["tipo"] == "resultados"
    assert resultados["estaticos"]["peso_n"] == pytest.approx(490.5)
    assert estado["tipo"] == "estado"
    assert estado["tiempo_s"] == 0.0


# --- Mensaje 'parametros' ----------------------------------------------------------
def test_parametros_validos_actualizan_el_simulador_y_responden_resultados(sesion, simulador):
    respuestas = _leer(sesion.procesar_mensaje(_mensaje_parametros(masa_kg=80)))
    assert len(respuestas) == 1
    assert respuestas[0]["tipo"] == "resultados"
    assert respuestas[0]["estaticos"]["peso_n"] == pytest.approx(784.8)
    assert simulador.parametros.masa_kg == 80.0


def test_cambio_de_parametros_conserva_el_estado_de_la_simulacion(sesion):
    sesion.procesar_mensaje('{"tipo": "perturbar"}')
    for _ in range(10):
        sesion.avanzar_cuadro()
    (antes,) = _leer(sesion.avanzar_cuadro())

    sesion.procesar_mensaje(_mensaje_parametros(masa_kg=80))
    (despues,) = _leer(sesion.avanzar_cuadro())

    assert despues["tiempo_s"] > antes["tiempo_s"]


def test_parametros_fuera_de_rango_responden_error_y_no_cambian_nada(sesion, simulador):
    parametros_antes = simulador.parametros
    (error,) = _leer(sesion.procesar_mensaje(_mensaje_parametros(masa_kg=500)))
    assert error["tipo"] == "error"
    assert error["parametro"] == "masa_kg"
    assert simulador.parametros == parametros_antes


# --- Mensaje 'perturbar' -----------------------------------------------------------
def test_perturbar_responde_el_estado_con_velocidad(sesion):
    (estado,) = _leer(sesion.procesar_mensaje('{"tipo": "perturbar"}'))
    assert estado["tipo"] == "estado"
    assert estado["velocidad_angular_rad_s"] == pytest.approx(
        configuracion.IMPULSO_PERTURBACION_RAD_S
    )


def test_perturbar_con_sentido_invalido_responde_error(sesion, simulador):
    (error,) = _leer(sesion.procesar_mensaje('{"tipo": "perturbar", "sentido": 2}'))
    assert error["tipo"] == "error"
    assert error["parametro"] == "sentido"
    assert simulador.estado.velocidad_angular_rad_s == 0.0


# --- Mensaje 'reiniciar' -----------------------------------------------------------
def test_reiniciar_vuelve_al_estado_inicial(sesion):
    sesion.procesar_mensaje('{"tipo": "perturbar"}')
    for _ in range(30):
        sesion.avanzar_cuadro()

    (estado,) = _leer(sesion.procesar_mensaje('{"tipo": "reiniciar"}'))

    assert estado["tiempo_s"] == 0.0
    assert estado["angulo_rad"] == 0.0
    assert estado["velocidad_angular_rad_s"] == 0.0


# --- Mensajes malformados ------------------------------------------------------------
@pytest.mark.parametrize("mensaje", ["esto no es json", '{"tipo": "desconocido"}', "[]"])
def test_mensaje_malformado_responde_error_sin_parametro(sesion, mensaje):
    (error,) = _leer(sesion.procesar_mensaje(mensaje))
    assert error["tipo"] == "error"
    assert error["parametro"] is None


def test_la_sesion_sigue_funcionando_tras_un_error(sesion):
    sesion.procesar_mensaje("esto no es json")
    (estado,) = _leer(sesion.avanzar_cuadro())
    assert estado["tipo"] == "estado"
    assert estado["tiempo_s"] == pytest.approx(1.0 / CUADROS_POR_SEGUNDO)


# --- Avance de la simulación ------------------------------------------------------------
def test_avanzar_cuadro_responde_un_solo_estado(sesion):
    respuestas = _leer(sesion.avanzar_cuadro())
    assert len(respuestas) == 1
    assert respuestas[0]["tipo"] == "estado"


def test_inestabilidad_reinicia_la_simulacion_y_avisa():
    sesion = Sesion(Simulador(IntegradorInestable(), ParametrosPalanca.por_defecto()))
    error, estado = _leer(sesion.avanzar_cuadro())
    assert error["tipo"] == "error"
    assert error["parametro"] is None
    assert estado["tipo"] == "estado"
    assert estado["tiempo_s"] == 0.0


# --- Aislamiento entre clientes ------------------------------------------------------------
def test_dos_sesiones_son_independientes():
    sesion_a = Sesion(Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto()))
    sesion_b = Sesion(Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto()))

    sesion_a.procesar_mensaje('{"tipo": "perturbar"}')
    (estado_b,) = _leer(sesion_b.avanzar_cuadro())

    assert estado_b["velocidad_angular_rad_s"] == pytest.approx(0.0, abs=1e-3)