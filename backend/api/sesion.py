"""Sesión: la simulación de UN cliente conectado, todavía sin red.

Une un Simulador con el protocolo de esquemas.py:
  - procesar_mensaje(): recibe el texto que envió el cliente, ejecuta la acción
    y devuelve las respuestas ya serializadas a JSON, listas para enviar.
  - avanzar_cuadro(): avanza la simulación un cuadro y devuelve el mensaje de estado.
  - mensajes_iniciales(): lo que el cliente necesita al conectarse.

Manejo de errores:
  - Un error esperado (PalancaError) NO cierra la conexión: se responde con un
    mensaje de tipo "error" y la sesión queda intacta y utilizable.
  - Un error inesperado (un bug) se propaga hacia arriba para que el servidor
    lo registre. No se oculta.
  - Si la integración se vuelve inestable, la simulación se reinicia y se avisa.

No abre conexiones ni crea temporizadores: eso es de servidor.py. Una Sesion
NO es segura entre hilos, pero sí entre tareas de asyncio, porque ninguno de
sus métodos espera (await) a mitad de una operación.
"""

import logging
from collections.abc import Callable
from typing import Any

from backend.api.esquemas import (
    MensajeParametros,
    MensajePerturbar,
    MensajeReiniciar,
    a_json,
    interpretar_mensaje,
    serializar_error,
    serializar_estado,
    serializar_resultados,
)
from backend.dominio.excepciones import PalancaError, SimulacionInestableError
from backend.simulacion.simulador import Simulador

registro = logging.getLogger(__name__)

Respuesta = dict[str, object]
Manejador = Callable[[Any], list[Respuesta]]


class Sesion:
    """Conecta un Simulador con los mensajes del protocolo WebSocket."""

    def __init__(self, simulador: Simulador) -> None:
        self._simulador = simulador
        # Registro de manejadores (principio O): un mensaje nuevo se agrega con
        # un método y una línea aquí, sin modificar procesar_mensaje().
        self._manejadores: dict[type, Manejador] = {
            MensajeParametros: self._manejar_parametros,
            MensajePerturbar: self._manejar_perturbar,
            MensajeReiniciar: self._manejar_reiniciar,
        }

    # --- API pública: siempre devuelve textos JSON listos para enviar ---------
    def mensajes_iniciales(self) -> list[str]:
        """Resultados y estado que el cliente recibe apenas se conecta."""
        return self._serializar([self._respuesta_resultados(), self._respuesta_estado()])

    def procesar_mensaje(self, mensaje: str | bytes) -> list[str]:
        """Interpreta y ejecuta un mensaje del cliente. Nunca lanza PalancaError."""
        try:
            entrante = interpretar_mensaje(mensaje)
            respuestas = self._manejadores[type(entrante)](entrante)
            return self._serializar(respuestas)
        except PalancaError as error:
            registro.warning("Mensaje rechazado: %s", error.detalle)
            return self._serializar([serializar_error(error)])

    def avanzar_cuadro(self) -> list[str]:
        """Avanza un cuadro y devuelve el estado. Si es inestable, reinicia y avisa."""
        try:
            estado = self._simulador.avanzar_cuadro()
            return self._serializar([serializar_estado(estado)])
        except SimulacionInestableError as error:
            registro.error("Simulación inestable, se reinicia: %s", error.detalle)
            self._simulador.reiniciar()
            return self._serializar([serializar_error(error), self._respuesta_estado()])

    # --- Manejadores: uno por tipo de mensaje ------------------------------------
    def _manejar_parametros(self, mensaje: MensajeParametros) -> list[Respuesta]:
        self._simulador.actualizar_parametros(mensaje.parametros)
        return [self._respuesta_resultados()]

    def _manejar_perturbar(self, mensaje: MensajePerturbar) -> list[Respuesta]:
        self._simulador.perturbar(mensaje.sentido)
        return [self._respuesta_estado()]

    def _manejar_reiniciar(self, _mensaje: MensajeReiniciar) -> list[Respuesta]:
        self._simulador.reiniciar()
        return [self._respuesta_estado()]

    # --- Internos ---------------------------------------------------------------------
    def _respuesta_estado(self) -> Respuesta:
        return serializar_estado(self._simulador.estado)

    def _respuesta_resultados(self) -> Respuesta:
        return serializar_resultados(
            self._simulador.resultados_estaticos, self._simulador.resultados_dinamicos
        )

    @staticmethod
    def _serializar(respuestas: list[Respuesta]) -> list[str]:
        """Convierte cada respuesta a JSON estricto (a_json rechaza NaN e infinito)."""
        return [a_json(respuesta) for respuesta in respuestas]