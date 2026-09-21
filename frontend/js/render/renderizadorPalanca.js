/**
 * Dibuja la palanca (barra, fulcro, carga y esfuerzo) en un <canvas>,
 * rotando según el ángulo que llega del backend.
 *
 * Convención de ángulo: positivo => el esfuerzo baja (y lo que esté del otro
 * lado, sube). Esto no depende del género.
 *
 * Convención de lados (ver backend/dominio/estatica.py, GENEROS_DISPONIBLES):
 *   - Primer género: el fulcro queda ENTRE el esfuerzo y la carga (lados
 *     opuestos), como un balancín. El esfuerzo empuja hacia abajo, igual que
 *     el peso.
 *   - Segundo y tercer género: el esfuerzo y la carga quedan del MISMO lado
 *     del fulcro (cuál de los dos brazos es más corto ya lo deciden los
 *     sliders, no el dibujo). El esfuerzo actúa hacia ARRIBA, en sentido
 *     contrario al peso (por eso la palanca se sostiene): su flecha se
 *     dibuja al revés que en el primer género.
 *
 * Escala fija, fulcro fijo: la escala (píxeles por metro) se calcula UNA
 * SOLA VEZ a partir de las distancias MÁXIMAS posibles (establecerLimites),
 * no de los valores actuales. Así, mover un slider alarga o acorta el brazo
 * correspondiente sin mover el fulcro ni reescalar el resto del dibujo.
 *
 * No calcula nada de física: solo traduce (ángulo, distancias, género) a
 * píxeles.
 */

import { leerTema } from "../utilidades/tema.js";
import { GENERO_LADOS_OPUESTOS } from "../configuracion.js";

const MARGEN_HORIZONTAL_PROPORCION = 0.12; // espacio a cada lado, relativo al ancho del canvas
const GROSOR_BARRA_PX = 10;
const RADIO_FULCRO_PX = 14;
const RADIO_CARGA_PX = 16;
const LONGITUD_FLECHA_ESFUERZO_PX = 46;
const GROSOR_LINEA_GUIA_PX = 1;

// Sentido de una flecha vertical: hacia dónde apunta la punta.
const SENTIDO = Object.freeze({ ABAJO: 1, ARRIBA: -1 });

export class RenderizadorPalanca {
  /**
   * @param {string} idCanvas El id del elemento <canvas> en index.html.
   */
  constructor(idCanvas) {
    this._canvas = document.getElementById(idCanvas);
    this._contexto = this._canvas.getContext("2d");
    this._tema = leerTema();

    this._distanciaEsfuerzoMaximaM = null;
    this._distanciaCargaMaximaM = null;
    this._pixelesPorMetro = null;

    this._observador = new ResizeObserver(() => this._ajustarResolucion());
    this._observador.observe(this._canvas);
    this._ajustarResolucion();
  }

  /**
   * Fija la escala del dibujo a partir de las distancias máximas posibles
   * (los "maximo" de RANGOS_PARAMETROS en configuracion.py). Se llama una
   * sola vez, al iniciar la aplicación, con los rangos que ya pidió
   * controles.js al backend (DRY: los números no se repiten aquí).
   */
  establecerLimites(distanciaEsfuerzoMaximaM, distanciaCargaMaximaM) {
    this._distanciaEsfuerzoMaximaM = distanciaEsfuerzoMaximaM;
    this._distanciaCargaMaximaM = distanciaCargaMaximaM;
    this._recalcularEscala();
  }

  /**
   * Dibuja un cuadro de la palanca.
   * @param {{angulo_rad: number, en_tope: boolean}} estado Del mensaje "estado".
   * @param {{distancia_carga_m: number, distancia_esfuerzo_m: number, nombre_genero: string}} parametros
   *   Los valores actuales de los sliders (y el género elegido en el selector).
   */
  dibujar(estado, parametros) {
    if (this._pixelesPorMetro === null) {
      return; // todavía no se llamó a establecerLimites()
    }

    const ctx = this._contexto;
    const anchoCss = this._canvas.width / this._escala;
    const altoCss = this._canvas.height / this._escala;

    ctx.save();
    ctx.scale(this._escala, this._escala);
    ctx.clearRect(0, 0, anchoCss, altoCss);

    const geometria = this._calcularGeometria(anchoCss, altoCss, parametros);
    const puntos = this._calcularPuntosRotados(
      geometria,
      estado.angulo_rad,
      parametros.nombre_genero,
    );

    this._dibujarLineaGuia(ctx, anchoCss, geometria);
    this._dibujarBarra(ctx, puntos, estado.en_tope);
    this._dibujarFulcro(ctx, geometria);
    this._dibujarEsfuerzo(ctx, puntos.esfuerzo, parametros.nombre_genero);
    this._dibujarCarga(ctx, puntos.carga);

    ctx.restore();
  }

  /** Libera el observador de tamaño. Se llama si el canvas deja de usarse. */
  destruir() {
    this._observador.disconnect();
  }

  // --- Geometría -------------------------------------------------------------------

  /**
   * Píxeles por metro tal que, incluso con el brazo más largo posible en
   * cualquiera de los dos lados, el dibujo no se sale del canvas. El fulcro
   * siempre queda exactamente en el centro horizontal.
   */
  _recalcularEscala() {
    if (this._distanciaEsfuerzoMaximaM === null) {
      return; // aún no se llamó a establecerLimites()
    }
    const anchoCss = this._canvas.getBoundingClientRect().width;
    const margenPx = anchoCss * MARGEN_HORIZONTAL_PROPORCION;
    const mitadDisponiblePx = anchoCss / 2 - margenPx;

    this._pixelesPorMetro = Math.min(
      mitadDisponiblePx / this._distanciaEsfuerzoMaximaM,
      mitadDisponiblePx / this._distanciaCargaMaximaM,
    );
  }

  _calcularGeometria(anchoCss, altoCss, parametros) {
    return {
      fulcro: { x: anchoCss / 2, y: altoCss * 0.55 },
      brazoEsfuerzoPx: parametros.distancia_esfuerzo_m * this._pixelesPorMetro,
      brazoCargaPx: parametros.distancia_carga_m * this._pixelesPorMetro,
      alturaSueloPx: altoCss * 0.85,
    };
  }

  /** Rota los extremos de la barra alrededor del fulcro según el ángulo. */
  _calcularPuntosRotados(geometria, anguloRad, nombreGenero) {
    const { fulcro, brazoEsfuerzoPx, brazoCargaPx } = geometria;
    const seno = Math.sin(anguloRad);
    const coseno = Math.cos(anguloRad);

    // Convención: lx negativo (izquierda), lx positivo (derecha).
    // y = fulcro.y - lx * sin(θ): con θ > 0, la izquierda baja y la derecha sube.
    const rotar = (lx) => ({
      x: fulcro.x + lx * coseno,
      y: fulcro.y - lx * seno,
    });

    // Primer género: el esfuerzo va a la izquierda del fulcro (lx negativo) y
    // la carga a la derecha (lados opuestos). Segundo y tercer género: los
    // dos van al mismo lado (acá, a la derecha), porque en esos géneros el
    // fulcro queda en un extremo de la barra, no entre las dos fuerzas.
    const ladoEsfuerzo = nombreGenero === GENERO_LADOS_OPUESTOS ? -1 : 1;
    const lxEsfuerzo = ladoEsfuerzo * brazoEsfuerzoPx;
    const lxCarga = brazoCargaPx;

    // La barra en sí (la línea que se dibuja) no siempre va de esfuerzo a
    // carga: en el primer género el fulcro (lx = 0) queda entre los dos, así
    // que sigue siendo así; pero en el segundo y el tercero el fulcro es una
    // PUNTA de la barra (los dos quedan del mismo lado), así que la barra
    // debe llegar hasta el fulcro aunque ninguna fuerza esté ahí, o se vería
    // flotando sin tocarlo. Por eso siempre se incluye 0 (el fulcro) al
    // buscar los dos extremos de la barra.
    const lxExtremoA = Math.min(lxEsfuerzo, lxCarga, 0);
    const lxExtremoB = Math.max(lxEsfuerzo, lxCarga, 0);

    return {
      esfuerzo: rotar(lxEsfuerzo),
      carga: rotar(lxCarga),
      barraInicio: rotar(lxExtremoA),
      barraFin: rotar(lxExtremoB),
    };
  }

  // --- Dibujo ------------------------------------------------------------------------

  _dibujarLineaGuia(ctx, anchoCss, geometria) {
    ctx.save();
    ctx.strokeStyle = this._tema.guia;
    ctx.lineWidth = GROSOR_LINEA_GUIA_PX;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(0, geometria.fulcro.y);
    ctx.lineTo(anchoCss, geometria.fulcro.y);
    ctx.stroke();
    ctx.restore();
  }

  _dibujarBarra(ctx, puntos, enTope) {
    ctx.save();
    ctx.strokeStyle = enTope ? this._tema.advertencia : this._tema.barra;
    ctx.lineWidth = GROSOR_BARRA_PX;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(puntos.barraInicio.x, puntos.barraInicio.y);
    ctx.lineTo(puntos.barraFin.x, puntos.barraFin.y);
    ctx.stroke();
    ctx.restore();
  }

  _dibujarFulcro(ctx, geometria) {
    const { x, y } = geometria.fulcro;
    ctx.save();

    ctx.fillStyle = this._tema.fulcro;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - RADIO_FULCRO_PX, geometria.alturaSueloPx);
    ctx.lineTo(x + RADIO_FULCRO_PX, geometria.alturaSueloPx);
    ctx.closePath();
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, RADIO_FULCRO_PX * 0.4, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }

  _dibujarEsfuerzo(ctx, punto, nombreGenero) {
    // Primer género: el esfuerzo empuja hacia abajo, como la carga. Segundo
    // y tercer género: actúa hacia arriba (en sentido contrario al peso), así
    // que la flecha se dibuja al revés; el comportamiento físico ya sale así
    // del backend (por eso la barra se mueve bien), esto es solo el dibujo.
    const sentido =
      nombreGenero === GENERO_LADOS_OPUESTOS ? SENTIDO.ABAJO : SENTIDO.ARRIBA;
    this._dibujarFlechaVertical(ctx, punto, this._tema.esfuerzo, "F", 0, sentido);
  }

  _dibujarCarga(ctx, punto) {
    ctx.save();
    ctx.fillStyle = this._tema.carga;
    ctx.beginPath();
    ctx.arc(punto.x, punto.y, RADIO_CARGA_PX, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // El peso siempre apunta hacia abajo, sin importar el género.
    this._dibujarFlechaVertical(
      ctx,
      punto,
      this._tema.carga,
      "W",
      RADIO_CARGA_PX,
      SENTIDO.ABAJO,
    );
  }

  /**
   * Dibuja una flecha vertical (fuerza) que "llega" al punto desde el lado
   * indicado por sentido: ABAJO (por defecto) la flecha viene de arriba y
   * apunta hacia el punto; ARRIBA es la misma flecha reflejada verticalmente
   * (viene de abajo y apunta hacia arriba). desplazamientoY separa la flecha
   * del punto (por ejemplo, para no encimarla con el círculo de la carga).
   */
  _dibujarFlechaVertical(
    ctx,
    punto,
    color,
    etiqueta,
    desplazamientoY = 0,
    sentido = SENTIDO.ABAJO,
  ) {
    const yInicio = punto.y - sentido * (LONGITUD_FLECHA_ESFUERZO_PX + desplazamientoY);
    const yFin = punto.y - sentido * (desplazamientoY + 4);

    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 3;

    ctx.beginPath();
    ctx.moveTo(punto.x, yInicio);
    ctx.lineTo(punto.x, yFin);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(punto.x, yFin + sentido * 8);
    ctx.lineTo(punto.x - 6, yFin - sentido * 4);
    ctx.lineTo(punto.x + 6, yFin - sentido * 4);
    ctx.closePath();
    ctx.fill();

    ctx.font = "600 13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(etiqueta, punto.x, yInicio - sentido * 8);
    ctx.restore();
  }

  // --- Resolución del canvas ----------------------------------------------------------

  _ajustarResolucion() {
    const { width, height } = this._canvas.getBoundingClientRect();
    this._escala = window.devicePixelRatio || 1;
    this._canvas.width = Math.round(width * this._escala);
    this._canvas.height = Math.round(height * this._escala);
    this._recalcularEscala();
  }
}
