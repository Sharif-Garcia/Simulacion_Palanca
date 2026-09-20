"""Servidor FastAPI: rutas HTTP, WebSocket y archivos del frontend.

Rutas:
  - GET /api/configuracion : rangos, gravedades y tope que el navegador
                             necesita para armar sus controles.
  - WebSocket /ws          : una Sesion por cliente conectado.
  - GET /                  : archivos estáticos del frontend (se registran
                             al final para no tapar las rutas anteriores).

Cada conexión ejecuta dos tareas concurrentes:
  - receptor: espera mensajes del cliente y responde a cada uno.
  - emisor:   avanza la simulación y envía un cuadro unas 60 veces por segundo.
Cuando una termina (por ejemplo, el cliente se desconecta), la otra se cancela.

Este módulo solo une piezas: la lógica vive en Sesion, el protocolo en
esquemas.py y la física en dominio. La fábrica de sesiones se recibe desde
afuera (principio D de SOLID), así las pruebas pueden inyectar la suya.

Nota de rendimiento: cada cuadro avanza siempre 1/60 s de tiempo simulado. Si
el equipo se atrasa, el emisor intenta recuperarse enviando cuadros seguidos
hasta CUADROS_ATRASO_MAXIMO; si el atraso es mayor, se resincroniza y la
simulación se ve más lenta en vez de acelerarse de golpe.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

from backend import configuracion
from backend.api.esquemas import construir_configuracion_cliente
from backend.api.sesion import Sesion
from backend.dominio.modelos import ParametrosPalanca
from backend.simulacion.integradores import IntegradorRungeKutta4
from backend.simulacion.simulador import Simulador

registro = logging.getLogger(__name__)

RUTA_CONFIGURACION = "/api/configuracion"
RUTA_WEBSOCKET = "/ws"
# servidor.py está en <raíz>/backend/api/, así que la raíz es dos niveles arriba.
DIRECTORIO_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

INTERVALO_CUADRO_S = 1.0 / configuracion.FRECUENCIA_CUADROS_HZ
CUADROS_ATRASO_MAXIMO = 5
CODIGO_CIERRE_ERROR_INTERNO = 1011  # código estándar de WebSocket: error del servidor
BYTES_MAXIMOS_POR_CARACTER = 4  # UTF-8 usa como máximo 4 bytes por carácter

FabricaSesion = Callable[[], Sesion]


def crear_sesion_por_defecto() -> Sesion:
    """Crea la sesión de un cliente nuevo: RK4 y los parámetros iniciales."""
    return Sesion(Simulador(IntegradorRungeKutta4(), ParametrosPalanca.por_defecto()))


# ---------------------------------------------------------------------------
# Tareas de una conexión
# ---------------------------------------------------------------------------
async def _enviar(websocket: WebSocket, textos: list[str]) -> None:
    """Envía cada texto JSON al cliente, en orden."""
    for texto in textos:
        await websocket.send_text(texto)


async def _recibir_mensajes(websocket: WebSocket, sesion: Sesion) -> None:
    """Atiende los mensajes del cliente hasta que se desconecte."""
    while True:
        evento = await websocket.receive()
        if evento["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(evento.get("code", 1000))
        # Un mensaje llega como texto o como bytes; si no trae ninguno, "" es
        # rechazado por la sesión como mensaje malformado.
        contenido = evento.get("text")
        if contenido is None:
            contenido = evento.get("bytes") or ""
        await _enviar(websocket, sesion.procesar_mensaje(contenido))


async def _emitir_cuadros(websocket: WebSocket, sesion: Sesion) -> None:
    """Avanza la simulación y envía un cuadro cada INTERVALO_CUADRO_S.

    Usa un reloj de objetivos fijos (instante_objetivo) en vez de dormir un
    intervalo fijo: así el tiempo que tarda enviar y calcular no acumula
    deriva y la animación mantiene 60 cuadros por segundo.
    """
    reloj = asyncio.get_running_loop().time
    instante_objetivo = reloj()
    while True:
        await _enviar(websocket, sesion.avanzar_cuadro())
        instante_objetivo += INTERVALO_CUADRO_S
        espera_s = instante_objetivo - reloj()
        if espera_s < -CUADROS_ATRASO_MAXIMO * INTERVALO_CUADRO_S:
            instante_objetivo = reloj()
            espera_s = 0.0
        # sleep(0) también cede el control, para que el receptor pueda correr.
        await asyncio.sleep(max(0.0, espera_s))


def _es_desconexion(excepcion: BaseException, websocket: WebSocket) -> bool:
    """Indica si la excepción solo significa que el cliente se fue.

    Enviar por un socket ya cerrado lanza RuntimeError; solo se considera
    desconexión si el socket realmente ya no está conectado. Cualquier otro
    RuntimeError es un bug y debe propagarse.
    """
    if isinstance(excepcion, WebSocketDisconnect):
        return True
    return (
        isinstance(excepcion, RuntimeError)
        and websocket.application_state != WebSocketState.CONNECTED
    )


async def _atender_cliente(websocket: WebSocket, sesion: Sesion) -> None:
    """Acepta la conexión y ejecuta receptor y emisor hasta que uno termine."""
    await websocket.accept()
    registro.info("Cliente conectado: %s", websocket.client)
    await _enviar(websocket, sesion.mensajes_iniciales())

    tareas = {
        asyncio.create_task(_recibir_mensajes(websocket, sesion), name="receptor"),
        asyncio.create_task(_emitir_cuadros(websocket, sesion), name="emisor"),
    }
    try:
        terminadas, _ = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # Se cancela lo que siga vivo (también si el servidor se está apagando).
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)

    for tarea in terminadas:
        if tarea.cancelled():
            continue
        excepcion = tarea.exception()
        if excepcion is not None and not _es_desconexion(excepcion, websocket):
            raise excepcion
    registro.info("Cliente desconectado: %s", websocket.client)


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------
def crear_aplicacion(
    fabrica_sesion: FabricaSesion = crear_sesion_por_defecto,
    directorio_frontend: Path = DIRECTORIO_FRONTEND,
) -> FastAPI:
    """Arma la aplicación FastAPI con sus rutas y los archivos del frontend."""
    aplicacion = FastAPI(title="Simulador de la palanca")

    @aplicacion.get(RUTA_CONFIGURACION)
    def obtener_configuracion() -> dict[str, Any]:
        """Datos para que el navegador arme sus controles."""
        return construir_configuracion_cliente()

    @aplicacion.websocket(RUTA_WEBSOCKET)
    async def punto_websocket(websocket: WebSocket) -> None:
        """Una conexión = una sesión = un simulador independiente."""
        try:
            await _atender_cliente(websocket, fabrica_sesion())
        except Exception:
            # Un error esperado (PalancaError) ya lo maneja la Sesion. Llegar
            # aquí es un bug: se registra completo y se cierra con código 1011.
            registro.exception("Error inesperado en la conexión %s", websocket.client)
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close(code=CODIGO_CIERRE_ERROR_INTERNO)

    # Debe registrarse AL FINAL: un montaje en "/" captura todo lo que no
    # coincida con las rutas anteriores.
    if directorio_frontend.is_dir():
        aplicacion.mount(
            "/", StaticFiles(directory=directorio_frontend, html=True), name="frontend"
        )
    else:
        registro.warning("No existe la carpeta del frontend: %s", directorio_frontend)

    return aplicacion


aplicacion = crear_aplicacion()


def ejecutar() -> None:
    """Arranca el servidor con los valores de configuracion.py."""
    logging.basicConfig(
        level=configuracion.NIVEL_REGISTRO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        aplicacion,
        host=configuracion.HOST_SERVIDOR,
        port=configuracion.PUERTO_SERVIDOR,
        log_level=configuracion.NIVEL_REGISTRO.lower(),
        # Tope de tamaño de un mensaje entrante, coherente con esquemas.py.
        ws_max_size=configuracion.LONGITUD_MAXIMA_MENSAJE * BYTES_MAXIMOS_POR_CARACTER,
    )


if __name__ == "__main__":
    ejecutar()