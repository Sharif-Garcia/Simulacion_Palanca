/**
 * Configuración central del frontend.
 *
 * Única fuente de verdad para constantes propias del navegador: cómo llegar
 * al servidor, la política de reconexión del WebSocket y cuánto tiempo
 * muestra la gráfica de ángulo. Los rangos de los controles (masa, distancias,
 * fuerza) NO están aquí: llegan del backend por GET /api/configuracion, para
 * no repetir esos números en dos lugares (DRY entre backend y frontend).
 */

// --- Conexión con el servidor ------------------------------------------------
// Usa el mismo host y protocolo con el que se cargó la página, para que el
// simulador funcione igual en localhost que si se publica en otra dirección.
export const URL_CONFIGURACION = "/api/configuracion";
export const URL_WEBSOCKET = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

// --- Reconexión del WebSocket -------------------------------------------------
// Espera creciente (backoff exponencial): 0.5 s, 1 s, 2 s, 4 s, hasta el tope.
export const RECONEXION_RETRASO_INICIAL_MS = 500;
export const RECONEXION_RETRASO_MAXIMO_MS = 8000;
export const RECONEXION_FACTOR_CRECIMIENTO = 2;

// --- Gráfica de ángulo ---------------------------------------------------------
// Cuántos segundos de historia se muestran; los puntos más viejos se descartan.
export const GRAFICA_VENTANA_S = 6;

// --- Tipos de mensaje del protocolo (deben coincidir con backend/api/esquemas.py) --
export const TIPO_MENSAJE = Object.freeze({
  ESTADO: "estado",
  RESULTADOS: "resultados",
  ERROR: "error",
});

export const TIPO_MENSAJE_SALIENTE = Object.freeze({
  PARAMETROS: "parametros",
  PERTURBAR: "perturbar",
  REINICIAR: "reiniciar",
});
