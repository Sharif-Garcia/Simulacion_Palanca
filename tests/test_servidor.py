"""Pruebas del servidor: rutas HTTP y WebSocket con el cliente de pruebas de Starlette."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import configuracion
from backend.api.servidor import (
    INTERVALO_CUADRO_S,
    crear_aplicacion,
    crear_sesion_por_defecto,
)
from backend.api.sesion import Sesion

# Con 60 cuadros por segundo, esto equivale a unos 5 segundos de simulación.
MAXIMO_MENSAJES_A_LEER = 300

PARAMETROS_JSON = {
    "masa_kg": 50,
    "distancia_carga_m": 0.5,
    "distancia_esfuerzo_m": 2,
    "fuerza_n": 122.6,
    "nombre_gravedad": "Tierra",
}


@pytest.fixture
def cliente(tmp_path: Path) -> Iterator[TestClient]:
    """Cliente de pruebas con un directorio de frontend temporal y vacío."""
    with TestClient(crear_aplicacion(directorio_frontend=tmp_path)) as cliente:
        yield cliente


def _leer(websocket) -> dict:
    """Recibe un mensaje del servidor ya convertido a diccionario."""
    return json.loads(websocket.receive_text())


def _leer_hasta(websocket, condicion: Callable[[dict], bool]) -> dict:
    """Lee mensajes (los cuadros de estado llegan intercalados) hasta que se cumpla la condición."""
    for _ in range(MAXIMO_MENSAJES_A_LEER):
        mensaje = _leer(websocket)
        if condicion(mensaje):
            return mensaje
    pytest.fail("No llegó el mensaje esperado dentro del límite de lectura")


def _conectar_y_consumir_iniciales(cliente: TestClient):
    """Abre el WebSocket y descarta los dos mensajes iniciales."""
    return cliente.websocket_connect("/ws")


# --- HTTP -------------------------------------------------------------------------
def test_ruta_de_configuracion_expone_los_rangos(cliente):
    respuesta = cliente.get("/api/configuracion")
    assert respuesta.status_code == 200
    contenido = respuesta.json()
    assert set(contenido["rangos"]) == set(configuracion.RANGOS_PARAMETROS)
    assert contenido["limite_angulo_grados"] == configuracion.LIMITE_ANGULO_GRADOS
    assert contenido["gravedad_inicial"] == configuracion.GRAVEDAD_INICIAL


def test_ruta_desconocida_devuelve_404(cliente):
    assert cliente.get("/api/no_existe").status_code == 404


def test_sirve_los_archivos_del_frontend(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Palanca</h1>", encoding="utf-8")
    with TestClient(crear_aplicacion(directorio_frontend=tmp_path)) as cliente:
        respuesta = cliente.get("/")
        assert respuesta.status_code == 200
        assert "Palanca" in respuesta.text


def test_sin_carpeta_de_frontend_la_api_sigue_funcionando(tmp_path):
    aplicacion = crear_aplicacion(directorio_frontend=tmp_path / "no_existe")
    with TestClient(aplicacion) as cliente:
        assert cliente.get("/api/configuracion").status_code == 200
        assert cliente.get("/").status_code == 404


def test_las_rutas_de_la_api_no_quedan_tapadas_por_el_frontend(tmp_path):
    (tmp_path / "index.html").write_text("frontend", encoding="utf-8")
    with TestClient(crear_aplicacion(directorio_frontend=tmp_path)) as cliente:
        assert "rangos" in cliente.get("/api/configuracion").json()


# --- WebSocket: conexión y cuadros ----------------------------------------------------
def test_al_conectar_envia_resultados_y_estado(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        resultados = _leer(websocket)
        estado = _leer(websocket)
    assert resultados["tipo"] == "resultados"
    assert resultados["estaticos"]["peso_n"] == pytest.approx(490.5)
    assert estado["tipo"] == "estado"
    assert estado["tiempo_s"] == 0.0


def test_emite_cuadros_de_estado_con_tiempo_creciente(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        _leer(websocket)  # resultados
        _leer(websocket)  # estado inicial
        cuadros = [_leer(websocket) for _ in range(5)]

    assert all(cuadro["tipo"] == "estado" for cuadro in cuadros)
    tiempos = [cuadro["tiempo_s"] for cuadro in cuadros]
    assert tiempos[0] == pytest.approx(INTERVALO_CUADRO_S)
    assert all(despues > antes for antes, despues in zip(tiempos, tiempos[1:]))


# --- WebSocket: mensajes del cliente ---------------------------------------------------
def test_parametros_validos_responden_resultados_nuevos(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        _leer(websocket)
        _leer(websocket)
        websocket.send_text(
            json.dumps({"tipo": "parametros", "parametros": {**PARAMETROS_JSON, "masa_kg": 80}})
        )
        resultados = _leer_hasta(
            websocket,
            lambda m: m["tipo"] == "resultados" and m["estaticos"]["peso_n"] > 700,
        )
    assert resultados["estaticos"]["peso_n"] == pytest.approx(784.8)


def test_parametro_fuera_de_rango_responde_error_indicando_cual(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        _leer(websocket)
        _leer(websocket)
        websocket.send_text(
            json.dumps({"tipo": "parametros", "parametros": {**PARAMETROS_JSON, "masa_kg": 500}})
        )
        error = _leer_hasta(websocket, lambda m: m["tipo"] == "error")
    assert error["parametro"] == "masa_kg"


def test_mensaje_malformado_responde_error_y_la_conexion_sigue(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        _leer(websocket)
        _leer(websocket)
        websocket.send_text("esto no es json")
        error = _leer_hasta(websocket, lambda m: m["tipo"] == "error")
        assert error["parametro"] is None
        # La conexión no se cerró: los cuadros siguen llegando.
        estado = _leer_hasta(websocket, lambda m: m["tipo"] == "estado")
    assert estado["tipo"] == "estado"


def test_perturbar_hace_que_la_barra_se_mueva(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        _leer(websocket)
        _leer(websocket)
        websocket.send_text('{"tipo": "perturbar"}')
        estado = _leer_hasta(
            websocket, lambda m: m["tipo"] == "estado" and abs(m["angulo_rad"]) > 1e-3
        )
    assert estado["angulo_rad"] > 0


def test_reiniciar_vuelve_el_tiempo_a_cero(cliente):
    with cliente.websocket_connect("/ws") as websocket:
        _leer(websocket)
        _leer(websocket)
        websocket.send_text('{"tipo": "perturbar"}')
        _leer_hasta(websocket, lambda m: m["tipo"] == "estado" and m["tiempo_s"] > 0.1)
        websocket.send_text('{"tipo": "reiniciar"}')
        estado = _leer_hasta(websocket, lambda m: m["tipo"] == "estado" and m["tiempo_s"] == 0.0)
    assert estado["angulo_rad"] == 0.0


# --- Aislamiento y fábrica de sesiones --------------------------------------------------
def test_dos_clientes_tienen_simulaciones_independientes(cliente):
    with cliente.websocket_connect("/ws") as cliente_a, cliente.websocket_connect("/ws") as cliente_b:
        for websocket in (cliente_a, cliente_b):
            _leer(websocket)
            _leer(websocket)

        cliente_a.send_text('{"tipo": "perturbar"}')
        _leer_hasta(cliente_a, lambda m: m["tipo"] == "estado" and m["angulo_rad"] > 1e-3)

        estado_b = _leer_hasta(cliente_b, lambda m: m["tipo"] == "estado")
    # El cliente B no fue perturbado: sigue prácticamente en equilibrio.
    assert abs(estado_b["angulo_rad"]) < 1e-3


def test_usa_la_fabrica_de_sesiones_inyectada(tmp_path):
    creadas: list[Sesion] = []

    def fabrica() -> Sesion:
        sesion = crear_sesion_por_defecto()
        creadas.append(sesion)
        return sesion

    aplicacion = crear_aplicacion(fabrica, directorio_frontend=tmp_path)
    with TestClient(aplicacion) as cliente:
        with cliente.websocket_connect("/ws") as websocket:
            _leer(websocket)
        with cliente.websocket_connect("/ws") as websocket:
            _leer(websocket)

    assert len(creadas) == 2
    assert creadas[0] is not creadas[1]


def test_la_sesion_por_defecto_es_una_sesion():
    assert isinstance(crear_sesion_por_defecto(), Sesion)