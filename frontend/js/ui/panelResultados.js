/**
 * Panel de resultados: escribe en el HTML los mensajes "resultados", "estado"
 * y "error" que llegan del WebSocket.
 *
 * Responsabilidad única: formatear y mostrar. No calcula nada (eso ya lo
 * resolvió el backend) y no sabe nada de la conexión ni de los sliders.
 *
 * Excepción: la fórmula de la reacción en el fulcro (R) sí depende del
 * género activo (R = F + W en primer género, R = W - F en segundo y
 * tercero), y el género no viaja en el mensaje "resultados". Por eso
 * actualizarGenero() existe aparte: main.js la llama cuando Controles avisa
 * que el género cambió, no cuando llega un mensaje del WebSocket.
 */

import { GENERO_LADOS_OPUESTOS } from "../configuracion.js";

// Texto e insignia para cada valor de EstadoPalanca (backend/dominio/modelos.py).
const PRESENTACION_ESTADO = Object.freeze({
  equilibrio: { texto: "En equilibrio", clase: "insignia--exito" },
  carga_sube: { texto: "La carga sube", clase: "insignia--neutra" },
  carga_baja: { texto: "La carga baja", clase: "insignia--neutra" },
});

// Texto e insignia para cada valor de TipoRespuesta.
const PRESENTACION_TIPO_RESPUESTA = Object.freeze({
  subamortiguada: {
    texto: "Subamortiguada (oscila y se estabiliza)",
    clase: "insignia--exito",
  },
  critica: {
    texto: "Crítica (se estabiliza sin oscilar)",
    clase: "insignia--neutra",
  },
  sobreamortiguada: {
    texto: "Sobreamortiguada (se estabiliza lento)",
    clase: "insignia--advertencia",
  },
});

const TEXTO_ESTADO_CONEXION = Object.freeze({
  conectando: "Conectando…",
  conectado: "Conectado",
  reconectando: "Reconectando…",
  desconectado: "Desconectado",
});

// Cada cuántos cuadros se actualiza la lectura para lectores de pantalla.
// El estado llega 60 veces por segundo; anunciarlo con esa frecuencia sería
// inútil y pesado. Con 30 alcanza unas 2 actualizaciones por segundo.
const CUADROS_POR_ACTUALIZACION_ACCESIBLE = 30;

export class PanelResultados {
  constructor() {
    this._resultadoPeso = document.getElementById("resultado-peso");
    this._resultadoFuerzaEquilibrio = document.getElementById(
      "resultado-fuerza-equilibrio",
    );
    this._resultadoVentajaMecanica = document.getElementById(
      "resultado-ventaja-mecanica",
    );
    this._resultadoReaccion = document.getElementById("resultado-reaccion");

    this._insigniaEstado = document.getElementById("insignia-estado");
    this._insigniaTope = document.getElementById("insignia-tope");
    this._insigniaTipoRespuesta = document.getElementById(
      "insignia-tipo-respuesta",
    );

    this._resultadoFrecuenciaNatural = document.getElementById(
      "resultado-frecuencia-natural",
    );
    this._resultadoFactorAmortiguamiento = document.getElementById(
      "resultado-factor-amortiguamiento",
    );
    this._resultadoSobreimpulso = document.getElementById(
      "resultado-sobreimpulso",
    );
    this._resultadoTiempoEstablecimiento = document.getElementById(
      "resultado-tiempo-establecimiento",
    );

    this._mensajeError = document.getElementById("mensaje-error");
    this._lecturaEnVivo = document.getElementById("lectura-en-vivo");
    this._indicadorConexion = document.getElementById("indicador-conexion");
    this._textoConexion = document.getElementById("texto-conexion");
    this._contadorCuadros = 0;

    // Dos versiones de la fórmula de R, una por disposición geométrica (ver
    // actualizarGenero). Cada una vive dos veces en el HTML: junto al
    // resultado y en la tarjeta de ecuaciones.
    this._formulasReaccionLadosOpuestos = document.querySelectorAll(
      "#formula-reaccion-lados-opuestos, #ecuacion-reaccion-lados-opuestos",
    );
    this._formulasReaccionMismoLado = document.querySelectorAll(
      "#formula-reaccion-mismo-lado, #ecuacion-reaccion-mismo-lado",
    );
  }

  /**
   * Actualiza las tarjetas de estática y dinámica.
   * Se llama cuando llega un mensaje {"tipo": "resultados", ...}.
   */
  actualizarResultados(mensaje) {
    const { estaticos, dinamicos } = mensaje;

    this._resultadoPeso.textContent = estaticos.peso_n.toFixed(1);
    this._resultadoFuerzaEquilibrio.textContent =
      estaticos.fuerza_equilibrio_n.toFixed(2);
    this._resultadoVentajaMecanica.textContent =
      estaticos.ventaja_mecanica.toFixed(2);
    this._resultadoReaccion.textContent =
      estaticos.reaccion_fulcro_n.toFixed(1);

    this._aplicarInsignia(
      this._insigniaEstado,
      PRESENTACION_ESTADO[dinamicos.estado],
    );
    this._aplicarInsignia(
      this._insigniaTipoRespuesta,
      PRESENTACION_TIPO_RESPUESTA[dinamicos.tipo_respuesta],
    );

    this._resultadoFrecuenciaNatural.textContent =
      dinamicos.frecuencia_natural_rad_s.toFixed(3);
    this._resultadoFactorAmortiguamiento.textContent =
      dinamicos.factor_amortiguamiento.toFixed(3);
    this._resultadoSobreimpulso.textContent =
      dinamicos.sobreimpulso_porcentaje.toFixed(1);
    this._resultadoTiempoEstablecimiento.textContent =
      dinamicos.tiempo_establecimiento_s.toFixed(2);

    // Los parámetros nuevos se aceptaron: cualquier error anterior ya no aplica.
    this._ocultarError();
  }

  /**
   * Actualiza el indicador de tope y la lectura accesible del ángulo.
   * Se llama con cada mensaje {"tipo": "estado", ...} (60 veces por segundo).
   */
  actualizarEstado(mensaje) {
    this._insigniaTope.hidden = !mensaje.en_tope;

    this._contadorCuadros += 1;
    if (this._contadorCuadros >= CUADROS_POR_ACTUALIZACION_ACCESIBLE) {
      this._contadorCuadros = 0;
      this._lecturaEnVivo.textContent = `Ángulo: ${mensaje.angulo_grados.toFixed(1)} grados. Tiempo: ${mensaje.tiempo_s.toFixed(1)} segundos.`;
    }
  }

  /**
   * Muestra el mensaje de error del servidor.
   * Se llama con cada mensaje {"tipo": "error", ...}.
   */
  mostrarError(mensaje) {
    this._mensajeError.textContent = mensaje.detalle;
    this._mensajeError.hidden = false;
  }
  mostrarEstadoConexion(estado) {
    this._indicadorConexion.className = `indicador-conexion indicador-conexion--${estado}`;
    this._textoConexion.textContent = TEXTO_ESTADO_CONEXION[estado] ?? estado;
  }

  /**
   * Muestra la fórmula de R que corresponde al género activo y oculta la
   * otra. Se llama cuando Controles avisa un cambio de género (ver main.js),
   * no con cada mensaje "resultados": el número de R sí llega ahí, pero de
   * qué fórmula viene no.
   */
  actualizarGenero(nombreGenero) {
    const ladosOpuestos = nombreGenero === GENERO_LADOS_OPUESTOS;
    for (const formula of this._formulasReaccionLadosOpuestos) {
      formula.hidden = !ladosOpuestos;
    }
    for (const formula of this._formulasReaccionMismoLado) {
      formula.hidden = ladosOpuestos;
    }
  }

  // --- Internos ------------------------------------------------------------------

  _ocultarError() {
    this._mensajeError.hidden = true;
  }

  _aplicarInsignia(elemento, presentacion) {
    if (!presentacion) {
      console.warn("Valor sin presentación definida:", elemento.id);
      return;
    }
    elemento.textContent = presentacion.texto;
    elemento.className = `insignia ${presentacion.clase}`;
  }
}
