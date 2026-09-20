/**
 * Dibuja el ángulo de la palanca en el tiempo, en una ventana deslizante.
 *
 * Responsabilidad única: acumular los puntos (ángulo, tiempo) que llegan del
 * WebSocket y dibujarlos como una curva. No calcula física ni conoce el
 * dibujo de la barra (eso es de renderizadorPalanca.js).
 *
 * Igual que renderizadorPalanca.js: la escala vertical se fija UNA VEZ a
 * partir del límite del tope (establecerLimiteAngulo), tomado de
 * GET /api/configuracion, no de un valor calculado en caliente. Así los
 * ejes no "saltan" mientras la palanca oscila.
 */

import { leerTema } from "../utilidades/tema.js";
import { GRAFICA_VENTANA_S } from "../configuracion.js";

const MARGEN_IZQUIERDO_PX = 40; // espacio para las etiquetas del eje vertical
const MARGEN_DERECHO_PX = 12;
const MARGEN_SUPERIOR_PX = 20;
const MARGEN_INFERIOR_PX = 24;
const FACTOR_MARGEN_VERTICAL = 1.2; // el eje muestra un poco más que el tope, no exacto
const RADIO_PUNTO_ACTUAL_PX = 4;
const MAXIMO_PUNTOS_EN_MEMORIA = 2000; // límite de seguridad, no depende de la ventana visible

export class GraficaAngulo {
  /**
   * @param {string} idCanvas El id del elemento <canvas> en index.html.
   */
  constructor(idCanvas) {
    this._canvas = document.getElementById(idCanvas);
    this._contexto = this._canvas.getContext("2d");
    this._tema = leerTema();

    this._limiteAnguloGrados = null;
    this._puntos = []; // { tiempoS, anguloGrados }

    this._observador = new ResizeObserver(() => this._ajustarResolucion());
    this._observador.observe(this._canvas);
    this._ajustarResolucion();
  }

  /**
   * Fija el rango vertical del eje a partir del tope mecánico del backend
   * (limite_angulo_grados de GET /api/configuracion). Se llama una sola vez,
   * al iniciar la aplicación.
   */
  establecerLimiteAngulo(gradosMaximo) {
    this._limiteAnguloGrados = gradosMaximo;
  }

  /**
   * Agrega un punto nuevo a la curva.
   * Se llama con cada mensaje {"tipo": "estado", ...} (60 veces por segundo).
   * Si el tiempo retrocede (la simulación se reinició), la curva se limpia
   * sola: no hace falta que quien la use llame a un método aparte.
   */
  agregarPunto(estado) {
    const ultimoPunto = this._puntos.at(-1);
    if (ultimoPunto && estado.tiempo_s < ultimoPunto.tiempoS) {
      this._puntos = [];
    }

    this._puntos.push({
      tiempoS: estado.tiempo_s,
      anguloGrados: estado.angulo_grados,
    });

    if (this._puntos.length > MAXIMO_PUNTOS_EN_MEMORIA) {
      this._puntos.shift();
    }
  }

  /** Dibuja la curva con los puntos acumulados hasta ahora. */
  dibujar() {
    if (this._limiteAnguloGrados === null || this._puntos.length === 0) {
      return; // aún no hay límite configurado o no ha llegado ningún dato
    }

    const ctx = this._contexto;
    const anchoCss = this._canvas.width / this._escala;
    const altoCss = this._canvas.height / this._escala;

    ctx.save();
    ctx.scale(this._escala, this._escala);
    ctx.clearRect(0, 0, anchoCss, altoCss);

    const geometria = this._calcularGeometria(anchoCss, altoCss);
    const puntosVisibles = this._puntosDentroDeLaVentana();

    this._dibujarEjesYEtiquetas(ctx, geometria);
    this._dibujarLineasDeTope(ctx, geometria);
    this._dibujarCurva(ctx, geometria, puntosVisibles);
    this._dibujarPuntoActual(ctx, geometria, puntosVisibles.at(-1));

    ctx.restore();
  }

  /** Libera el observador de tamaño. Se llama si el canvas deja de usarse. */
  destruir() {
    this._observador.disconnect();
  }

  // --- Geometría -------------------------------------------------------------------

  _calcularGeometria(anchoCss, altoCss) {
    const limiteEjeGrados = this._limiteAnguloGrados * FACTOR_MARGEN_VERTICAL;
    return {
      x0: MARGEN_IZQUIERDO_PX,
      x1: anchoCss - MARGEN_DERECHO_PX,
      y0: MARGEN_SUPERIOR_PX,
      y1: altoCss - MARGEN_INFERIOR_PX,
      limiteEjeGrados,
    };
  }

  /** Solo los puntos dentro de la ventana de tiempo visible (los últimos N segundos). */
  _puntosDentroDeLaVentana() {
    const tiempoActual = this._puntos.at(-1).tiempoS;
    const tiempoInicioVentana = Math.max(0, tiempoActual - GRAFICA_VENTANA_S);
    return this._puntos.filter((punto) => punto.tiempoS >= tiempoInicioVentana);
  }

  /** Convierte (tiempo, ángulo) a coordenadas de píxel dentro del área de dibujo. */
  _aCoordenadas(geometria, puntosVisibles, punto) {
    const tiempoActual = puntosVisibles.at(-1).tiempoS;
    const tiempoInicioVentana = Math.max(0, tiempoActual - GRAFICA_VENTANA_S);
    const duracionVentana = tiempoActual - tiempoInicioVentana || 1; // evita dividir por 0 en t=0

    const proporcionX = (punto.tiempoS - tiempoInicioVentana) / duracionVentana;
    const proporcionY =
      0.5 - punto.anguloGrados / (2 * geometria.limiteEjeGrados);

    return {
      x: geometria.x0 + proporcionX * (geometria.x1 - geometria.x0),
      y: geometria.y0 + proporcionY * (geometria.y1 - geometria.y0),
    };
  }

  // --- Dibujo ------------------------------------------------------------------------

  _dibujarEjesYEtiquetas(ctx, geometria) {
    ctx.save();
    ctx.strokeStyle = this._tema.graficaEje;
    ctx.fillStyle = this._tema.textoSecundario;
    ctx.font = "11px sans-serif";
    ctx.textBaseline = "middle";

    // Línea de referencia en 0° (el equilibrio).
    const yCero = geometria.y0 + 0.5 * (geometria.y1 - geometria.y0);
    ctx.beginPath();
    ctx.moveTo(geometria.x0, yCero);
    ctx.lineTo(geometria.x1, yCero);
    ctx.stroke();

    ctx.textAlign = "right";
    ctx.fillText("0°", geometria.x0 - 6, yCero);
    ctx.fillText(
      `${geometria.limiteEjeGrados.toFixed(0)}°`,
      geometria.x0 - 6,
      geometria.y0,
    );
    ctx.fillText(
      `${(-geometria.limiteEjeGrados).toFixed(0)}°`,
      geometria.x0 - 6,
      geometria.y1,
    );

    ctx.restore();
  }

  /** Líneas punteadas en ±30° (o el tope que sea), para relacionar la gráfica con el dibujo. */
  _dibujarLineasDeTope(ctx, geometria) {
    const yTopeSuperior =
      geometria.y0 +
      (0.5 - this._limiteAnguloGrados / (2 * geometria.limiteEjeGrados)) *
        (geometria.y1 - geometria.y0);
    const yTopeInferior =
      geometria.y0 +
      (0.5 + this._limiteAnguloGrados / (2 * geometria.limiteEjeGrados)) *
        (geometria.y1 - geometria.y0);

    ctx.save();
    ctx.strokeStyle = this._tema.graficaReferencia;
    ctx.setLineDash([3, 5]);
    ctx.lineWidth = 1;
    for (const y of [yTopeSuperior, yTopeInferior]) {
      ctx.beginPath();
      ctx.moveTo(geometria.x0, y);
      ctx.lineTo(geometria.x1, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  _dibujarCurva(ctx, geometria, puntosVisibles) {
    if (puntosVisibles.length < 2) return;

    const coordenadas = puntosVisibles.map((punto) =>
      this._aCoordenadas(geometria, puntosVisibles, punto),
    );

    ctx.save();

    // Área rellena bajo la curva, hasta la línea de 0°.
    const yCero = geometria.y0 + 0.5 * (geometria.y1 - geometria.y0);
    ctx.fillStyle = this._tema.graficaRelleno;
    ctx.beginPath();
    ctx.moveTo(coordenadas[0].x, yCero);
    for (const punto of coordenadas) ctx.lineTo(punto.x, punto.y);
    ctx.lineTo(coordenadas.at(-1).x, yCero);
    ctx.closePath();
    ctx.fill();

    // La curva en sí.
    ctx.strokeStyle = this._tema.graficaLinea;
    ctx.lineWidth = 2;
    ctx.beginPath();
    coordenadas.forEach((punto, indice) => {
      if (indice === 0) ctx.moveTo(punto.x, punto.y);
      else ctx.lineTo(punto.x, punto.y);
    });
    ctx.stroke();

    ctx.restore();
  }

  _dibujarPuntoActual(ctx, geometria, ultimoPunto) {
    if (!ultimoPunto) return;
    const coordenada = this._aCoordenadas(
      geometria,
      [ultimoPunto],
      ultimoPunto,
    );

    ctx.save();
    ctx.fillStyle = this._tema.graficaLinea;
    ctx.beginPath();
    ctx.arc(coordenada.x, coordenada.y, RADIO_PUNTO_ACTUAL_PX, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  // --- Resolución del canvas ----------------------------------------------------------

  _ajustarResolucion() {
    const { width, height } = this._canvas.getBoundingClientRect();
    this._escala = window.devicePixelRatio || 1;
    this._canvas.width = Math.round(width * this._escala);
    this._canvas.height = Math.round(height * this._escala);
  }
}
