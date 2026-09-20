/**
 * Lee los tokens de color de variables.css para que el canvas dibuje con la
 * misma paleta que el resto de la interfaz, sin repetir un solo color en
 * JavaScript (DRY: variables.css sigue siendo la única fuente de verdad).
 */

/**
 * Lee el valor de una variable CSS (--nombre) definida en :root.
 * @param {string} nombreVariable Por ejemplo "--color-acento".
 * @returns {string} El valor tal como el navegador lo resolvió (ej. "#4fd1c5").
 */
function leerVariableCss(nombreVariable) {
  const valor = getComputedStyle(document.documentElement)
    .getPropertyValue(nombreVariable)
    .trim();

  if (!valor) {
    throw new Error(
      `La variable CSS '${nombreVariable}' no está definida en variables.css`,
    );
  }
  return valor;
}

/**
 * Colores que el dibujo de la palanca y la gráfica necesitan, leídos en el
 * momento en que se llama (no se guardan en caché), para que un cambio de
 * tema en caliente (por ejemplo, un futuro modo claro) se refleje sin recargar.
 * @returns {object} Un color por cada uso, listo para pasarse a canvas.
 */
export function leerTema() {
  return {
    // Dibujo de la palanca
    barra: leerVariableCss("--color-barra"),
    fulcro: leerVariableCss("--color-fulcro"),
    carga: leerVariableCss("--color-carga"),
    esfuerzo: leerVariableCss("--color-esfuerzo"),
    guia: leerVariableCss("--color-guia"),

    // Texto y fondo, para etiquetas dibujadas dentro del canvas
    texto: leerVariableCss("--color-texto-primario"),
    textoSecundario: leerVariableCss("--color-texto-secundario"),
    fondo: leerVariableCss("--color-superficie"),

    // Gráfica de ángulo
    graficaLinea: leerVariableCss("--color-grafica-linea"),
    graficaRelleno: leerVariableCss("--color-grafica-relleno"),
    graficaEje: leerVariableCss("--color-grafica-eje"),
    graficaReferencia: leerVariableCss("--color-grafica-referencia"),

    // Estados semánticos, para colorear el dibujo según lo que pase
    exito: leerVariableCss("--color-exito"),
    advertencia: leerVariableCss("--color-advertencia"),
    peligro: leerVariableCss("--color-peligro"),
  };
}
