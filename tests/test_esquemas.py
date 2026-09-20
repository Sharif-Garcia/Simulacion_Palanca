"""Pruebas del protocolo de mensajes del WebSocket."""

import json

import pytest

from backend import configuracion
from backend.api.esquemas import (
    MensajeParametros,
    MensajePerturbar,
    MensajeReiniciar,
    a_json,
    construir_configuracion_cliente,
    interpretar_mensaje,
    serializar_error,
    serializar_estado,
    serializar_resultados,
)
from backend.dominio.dinamica import resolver_dinamica
from backend.dominio.estatica import resolver_estatica
from backend.dominio.excepciones import (
    MensajeMalformadoError,
    ParametroInvalidoError,
    SimulacionInestableError,
)
from backend.dominio.modelos import EstadoSimulacion, ParametrosPalanca

PARAMETROS_VALIDOS = {
    "masa_kg": 50,
    "distancia_carga_m": 0.5,
    "distancia_esfuerzo_m": 2,
    "fuerza_n": 122.6,
    "nombre_gravedad": "Tierra",
}


def _texto(**mensaje) -> str:
    """Arma el texto JSON de un mensaje del cliente."""
    return json.dumps(mensaje)


# --- Mensajes entrantes válidos ----------------------------------------------------
def test_interpreta_mensaje_de_parametros():
    mensaje = interpretar_mensaje(_texto(tipo="parametros", parametros=PARAMETROS_VALIDOS))
    assert isinstance(mensaje, MensajeParametros)
    assert mensaje.parametros == ParametrosPalanca(
        masa_kg=50.0,
        distancia_carga_m=0.5,
        distancia_esfuerzo_m=2.0,
        fuerza_n=122.6,
        nombre_gravedad="Tierra",
    )


def test_interpreta_perturbacion_con_sentido_por_defecto():
    assert interpretar_mensaje(_texto(tipo="perturbar")) == MensajePerturbar(sentido=1.0)


def test_interpreta_perturbacion_en_sentido_negativo():
    assert interpretar_mensaje(_texto(tipo="perturbar", sentido=-1)) == MensajePerturbar(sentido=-1.0)


def test_interpreta_reinicio():
    assert isinstance(interpretar_mensaje(_texto(tipo="reiniciar")), MensajeReiniciar)


def test_acepta_mensajes_en_bytes():
    assert isinstance(interpretar_mensaje(b'{"tipo": "reiniciar"}'), MensajeReiniciar)


# --- Mensajes con formato incorrecto -------------------------------------------------
@pytest.mark.parametrize(
    "mensaje",
    [
        "esto no es json",
        "[1, 2]",
        "42",
        "null",
        "{}",
        '{"tipo": 5}',
        '{"tipo": "desconocido"}',
        '{"tipo": "parametros"}',
        b"\xff\xfe",
        "[" * 3000,
    ],
)
def test_rechaza_mensajes_malformados(mensaje):
    with pytest.raises(MensajeMalformadoError):
        interpretar_mensaje(mensaje)


def test_rechaza_mensaje_demasiado_grande():
    with pytest.raises(MensajeMalformadoError, match="tamaño máximo"):
        interpretar_mensaje("x" * (configuracion.LONGITUD_MAXIMA_MENSAJE + 1))


# --- Valores inválidos dentro de un mensaje bien formado -------------------------------
def test_parametro_fuera_de_rango_indica_cual_fallo():
    texto = _texto(tipo="parametros", parametros={**PARAMETROS_VALIDOS, "masa_kg": 500})
    with pytest.raises(ParametroInvalidoError) as informacion:
        interpretar_mensaje(texto)
    assert informacion.value.nombre_parametro == "masa_kg"


def test_parametros_que_no_son_un_objeto_se_rechazan():
    with pytest.raises(ParametroInvalidoError):
        interpretar_mensaje(_texto(tipo="parametros", parametros=[1, 2, 3]))


def test_rechaza_nan_en_los_parametros():
    texto = _texto(tipo="parametros", parametros={**PARAMETROS_VALIDOS, "masa_kg": float("nan")})
    with pytest.raises(ParametroInvalidoError):
        interpretar_mensaje(texto)


@pytest.mark.parametrize(
    "texto",
    [
        '{"tipo": "perturbar", "sentido": "arriba"}',
        '{"tipo": "perturbar", "sentido": true}',
        '{"tipo": "perturbar", "sentido": null}',
    ],
)
def test_perturbacion_rechaza_sentido_no_numerico(texto):
    with pytest.raises(ParametroInvalidoError):
        interpretar_mensaje(texto)


# --- Serialización ------------------------------------------------------------------------
def test_serializar_estado():
    estado = EstadoSimulacion(
        angulo_rad=0.5, velocidad_angular_rad_s=1.0, tiempo_s=2.0, en_tope=True
    )
    mensaje = serializar_estado(estado)
    assert mensaje["tipo"] == "estado"
    assert mensaje["angulo_rad"] == 0.5
    assert mensaje["angulo_grados"] == pytest.approx(28.6479, abs=1e-4)
    assert mensaje["velocidad_angular_rad_s"] == 1.0
    assert mensaje["tiempo_s"] == 2.0
    assert mensaje["en_tope"] is True


def test_serializar_resultados_incluye_estaticos_y_dinamicos():
    parametros = ParametrosPalanca.por_defecto()
    mensaje = serializar_resultados(resolver_estatica(parametros), resolver_dinamica(parametros))
    assert mensaje["tipo"] == "resultados"
    assert mensaje["estaticos"]["peso_n"] == pytest.approx(490.5)
    assert mensaje["estaticos"]["ventaja_mecanica"] == pytest.approx(4.0)
    assert mensaje["dinamicos"]["estado"] == "equilibrio"
    assert mensaje["dinamicos"]["tipo_respuesta"] == "subamortiguada"


def test_serializar_error_de_parametro_indica_cual_fallo():
    error = ParametroInvalidoError("masa_kg", -5, "debe estar entre 1 y 200")
    assert serializar_error(error) == {
        "tipo": "error",
        "detalle": error.detalle,
        "parametro": "masa_kg",
    }


def test_serializar_error_generico_no_indica_parametro():
    error = MensajeMalformadoError("no es JSON válido")
    mensaje = serializar_error(error)
    assert mensaje["tipo"] == "error"
    assert mensaje["parametro"] is None


def test_a_json_es_compacto():
    assert a_json({"tipo": "x", "valor": 1}) == '{"tipo":"x","valor":1}'


def test_a_json_rechaza_valores_no_finitos():
    with pytest.raises(SimulacionInestableError):
        a_json({"tipo": "estado", "angulo_rad": float("nan")})


# --- Configuración para el navegador ---------------------------------------------------------
def test_configuracion_cliente_expone_lo_de_configuracion_py():
    resultado = construir_configuracion_cliente()
    assert set(resultado["rangos"]) == set(configuracion.RANGOS_PARAMETROS)
    masa = resultado["rangos"]["masa_kg"]
    assert masa["minimo"] == 1.0
    assert masa["maximo"] == 200.0
    assert masa["unidad"] == "kg"
    assert resultado["gravedades_m_s2"] == {"Tierra": 9.81, "Luna": 1.62, "Marte": 3.71}
    assert resultado["gravedad_inicial"] == "Tierra"
    assert resultado["limite_angulo_grados"] == 30.0


def test_configuracion_cliente_es_json_valido():
    configuracion_cliente = construir_configuracion_cliente()
    assert json.loads(a_json(configuracion_cliente)) == configuracion_cliente