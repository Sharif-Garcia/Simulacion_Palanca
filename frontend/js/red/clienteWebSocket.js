/**
 * Cliente WebSocket con reconexión automática.
 *
 * Responsabilidad única: abrir la conexión, reconectar con espera creciente
 * si se cae, y entregar cada mensaje ya convertido a objeto (JSON.parse) a
 * quien lo use. No conoce sliders, el dibujo ni los resultados: todo eso lo
 * maneja quien construya este cliente, a través de las funciones que reciba.
 */

import {
  RECONEXION_FACTOR_CRECIMIENTO,
  RECONEXION_RETRASO_INICIAL_MS,
  RECONEXION_RETRASO_MAXIMO_MS,
} from "../configuracion.js";

/** Estados posibles de la conexión, para que quien escuche decida qué mostrar. */
export const ESTADO_CONEXION = Object.freeze({
  CONECTANDO: "conectando",
  CONECTADO: "conectado",
  RECONECTANDO: "reconectando",
  DESCONECTADO: "desconectado",
});

export class ClienteWebSocket {
  /**
   * @param {string} url Dirección del WebSocket (ver URL_WEBSOCKET en configuracion.js).
   * @param {object} manejadores
   * @param {(mensaje: object) => void} manejadores.alRecibirMensaje
   *   Se llama con cada mensaje ya interpretado (JSON.parse).
   * @param {(estado: string) => void} [manejadores.alCambiarEstado]
   *   Se llama cuando cambia el estado de la conexión (ver ESTADO_CONEXION).
   */
  constructor(url, { alRecibirMensaje, alCambiarEstado = () => {} }) {
    this._url = url;
    this._alRecibirMensaje = alRecibirMensaje;
    this._alCambiarEstado = alCambiarEstado;

    this._socket = null;
    this._retrasoReconexionMs = RECONEXION_RETRASO_INICIAL_MS;
    this._idTemporizadorReconexion = null;
    this._cerradoPorElUsuario = false;
  }

  /** Abre la conexión. Es seguro llamarlo una sola vez al iniciar la aplicación. */
  conectar() {
    this._cerradoPorElUsuario = false;
    this._abrirSocket();
  }

  /** Cierra la conexión de forma definitiva y cancela cualquier reintento pendiente. */
  desconectar() {
    this._cerradoPorElUsuario = true;
    this._cancelarReconexionPendiente();
    this._socket?.close();
  }

  /**
   * Envía un objeto al servidor como JSON.
   * Si la conexión no está abierta, el mensaje se descarta (no se guarda en
   * cola): el siguiente cuadro de estado que llegue del servidor será la
   * fuente de verdad, así que no hace falta reenviar mensajes viejos.
   * @param {object} mensaje
   */
  enviar(mensaje) {
    if (this._socket?.readyState !== WebSocket.OPEN) {
      console.warn(
        "No se envió el mensaje porque el WebSocket no está conectado:",
        mensaje,
      );
      return;
    }
    this._socket.send(JSON.stringify(mensaje));
  }

  // --- Internos ------------------------------------------------------------------

  _abrirSocket() {
    this._notificarEstado(
      this._retrasoReconexionMs === RECONEXION_RETRASO_INICIAL_MS
        ? ESTADO_CONEXION.CONECTANDO
        : ESTADO_CONEXION.RECONECTANDO,
    );

    const socket = new WebSocket(this._url);
    this._socket = socket;

    socket.addEventListener("open", () => {
      this._retrasoReconexionMs = RECONEXION_RETRASO_INICIAL_MS; // se restablece al conectar
      this._notificarEstado(ESTADO_CONEXION.CONECTADO);
    });

    socket.addEventListener("message", (evento) => {
      this._manejarMensaje(evento.data);
    });

    socket.addEventListener("close", () => {
      this._notificarEstado(ESTADO_CONEXION.DESCONECTADO);
      if (!this._cerradoPorElUsuario) {
        this._programarReconexion();
      }
    });

    // "error" siempre va seguido de "close" en el WebSocket estándar, así que
    // aquí solo se registra en consola; la reconexión la maneja "close".
    socket.addEventListener("error", (evento) => {
      console.error("Error en el WebSocket:", evento);
    });
  }

  _manejarMensaje(datosCrudos) {
    let mensaje;
    try {
      mensaje = JSON.parse(datosCrudos);
    } catch (error) {
      console.error(
        "Mensaje del servidor no es JSON válido:",
        datosCrudos,
        error,
      );
      return;
    }
    this._alRecibirMensaje(mensaje);
  }

  _programarReconexion() {
    this._notificarEstado(ESTADO_CONEXION.RECONECTANDO);
    this._idTemporizadorReconexion = setTimeout(() => {
      this._abrirSocket();
    }, this._retrasoReconexionMs);

    // Espera creciente (backoff exponencial), con un tope máximo.
    this._retrasoReconexionMs = Math.min(
      this._retrasoReconexionMs * RECONEXION_FACTOR_CRECIMIENTO,
      RECONEXION_RETRASO_MAXIMO_MS,
    );
  }

  _cancelarReconexionPendiente() {
    if (this._idTemporizadorReconexion !== null) {
      clearTimeout(this._idTemporizadorReconexion);
      this._idTemporizadorReconexion = null;
    }
  }

  _notificarEstado(estado) {
    this._alCambiarEstado(estado);
  }
}
