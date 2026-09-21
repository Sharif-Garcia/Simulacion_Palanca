/**
 * Controles del usuario: sliders de masa, distancias, fuerza, selector de
 * gravedad, botones de género y botones de perturbar/reiniciar.
 *
 * Responsabilidades:
 *   1. Pedir los rangos al backend (GET /api/configuracion) y aplicarlos a
 *      los sliders del HTML, para no repetir esos números aquí (DRY).
 *   2. Mostrar el valor actual de cada slider mientras se mueve.
 *   3. Enviar cada cambio al servidor por el WebSocket.
 *   4. Aplicar los presets de amortiguamiento (botones junto a la gráfica):
 *      los valores ya vienen calculados en presets_amortiguamiento, esta
 *      capa solo los copia a los sliders y los envía como cualquier otro
 *      cambio (no calcula ni conoce ningún número propio).
 *   5. Crear los botones de género a partir de generos_disponibles (nombres
 *      legibles incluidos): ni el HTML ni este módulo hardcodean "Primer
 *      género", etc. Como no son un <select>, este módulo también recuerda
 *      cuál está elegido (no hay un .value nativo que preguntar).
 *   6. En segundo y tercer género, acoplar los sliders de distancia: cada
 *      uno tiene una restricción con el otro (ver GENEROS_DISPONIBLES en
 *      backend/dominio/estatica.py — validadores.py la exige igual, pero
 *      solo como red de seguridad), así que este módulo nunca deja que el
 *      slider "arrastre" al otro más allá de esa restricción, en vez de
 *      dejar que el usuario choque con el mensaje de error del backend.
 *
 * No dibuja el resultado ni el estado: eso lo hace panelResultados.js al
 * recibir los mensajes de vuelta. Tampoco decide cómo se ve la palanca según
 * el género: eso lo hace renderizadorPalanca.js, a partir del nombre_genero
 * que ya viaja en leerParametrosActuales().
 */

import { TIPO_MENSAJE_SALIENTE, URL_CONFIGURACION } from "../configuracion.js";

// Los dos géneros donde la carga y el esfuerzo comparten lado del fulcro y
// por eso necesitan una separación mínima entre sus distancias (ver
// GENEROS_DISPONIBLES en backend/dominio/estatica.py). El primer género no
// aparece aquí a propósito: ahí los sliders son independientes.
const GENERO_SEGUNDO = "segundo_genero";
const GENERO_TERCERO = "tercer_genero";

// Los "name" de estos inputs coinciden con las claves de RANGOS_PARAMETROS en
// configuracion.py, así el mapeo entre backend y frontend es directo.
const IDS_SLIDERS = Object.freeze({
  masa_kg: { control: "control-masa", valor: "valor-masa", decimales: 0 },
  distancia_carga_m: {
    control: "control-distancia-carga",
    valor: "valor-distancia-carga",
    decimales: 2,
  },
  distancia_esfuerzo_m: {
    control: "control-distancia-esfuerzo",
    valor: "valor-distancia-esfuerzo",
    decimales: 2,
  },
  fuerza_n: { control: "control-fuerza", valor: "valor-fuerza", decimales: 1 },
});

const ID_SELECTOR_GRAVEDAD = "selector-gravedad";
const ID_GRUPO_GENERO = "selector-genero";
const ID_BOTON_PERTURBAR = "boton-perturbar";
const ID_BOTON_REINICIAR = "boton-reiniciar";
// Cada botón de preset trae en data-preset la clave que usar en
// presets_amortiguamiento (coincide con TipoRespuesta en el backend).
const SELECTOR_BOTONES_PRESET = "[data-preset]";

export class Controles {
  /**
   * @param {import("../red/clienteWebSocket.js").ClienteWebSocket} clienteWebSocket
   * @param {{alCambiarGenero?: (nombreGenero: string) => void}} [callbacks]
   *   alCambiarGenero: se llama con el nuevo género apenas se elige (antes de
   *   que el backend confirme el cambio), para que otros módulos que no
   *   escuchan el WebSocket (como panelResultados.js, para la fórmula de R)
   *   puedan reaccionar. Mismo patrón que los callbacks de ClienteWebSocket.
   */
  constructor(clienteWebSocket, { alCambiarGenero = () => {} } = {}) {
    this._cliente = clienteWebSocket;
    this._alCambiarGenero = alCambiarGenero;
    this._elementosSlider = this._obtenerElementosSlider();
    this._selectorGravedad = document.getElementById(ID_SELECTOR_GRAVEDAD);
    this._grupoGenero = document.getElementById(ID_GRUPO_GENERO);
    this._botonesGenero = [];
    this._nombreGeneroActual = null;
    this._botonPerturbar = document.getElementById(ID_BOTON_PERTURBAR);
    this._botonReiniciar = document.getElementById(ID_BOTON_REINICIAR);
    this._botonesPreset = document.querySelectorAll(SELECTOR_BOTONES_PRESET);
  }

  /**
   * Pide los rangos al backend, configura los sliders y conecta los eventos.
   * Se llama una sola vez, al iniciar la aplicación.
   */
  async inicializar() {
    this._configuracion = await this._pedirConfiguracion();
    this._aplicarRangos(this._configuracion.rangos);
    this._aplicarGeneros(
      this._configuracion.generos_disponibles,
      this._configuracion.genero_inicial,
    );
    this._conectarEventos();
  }

  /** Los rangos que llegaron del backend (min, max, paso, valor_inicial por parámetro). */
  obtenerRangos() {
    return this._configuracion.rangos;
  }

  /** La configuración completa que devolvió el backend (rangos, gravedades, límite de ángulo, etc.). */
  obtenerConfiguracionCompleta() {
    return this._configuracion;
  }

  /** Lee los valores actuales de todos los controles, listos para validar_parametros(). */
  leerParametrosActuales() {
    const parametros = {
      nombre_gravedad: this._selectorGravedad.value,
      nombre_genero: this._nombreGeneroActual,
    };
    for (const [nombreParametro, referencias] of Object.entries(
      this._elementosSlider,
    )) {
      parametros[nombreParametro] = Number(referencias.control.value);
    }
    return parametros;
  }

  // --- Internos ------------------------------------------------------------------

  async _pedirConfiguracion() {
    const respuesta = await fetch(URL_CONFIGURACION);
    if (!respuesta.ok) {
      throw new Error(
        `No se pudo obtener la configuración del servidor (${respuesta.status})`,
      );
    }
    return respuesta.json();
  }

  _obtenerElementosSlider() {
    const elementos = {};
    for (const [nombreParametro, ids] of Object.entries(IDS_SLIDERS)) {
      elementos[nombreParametro] = {
        control: document.getElementById(ids.control),
        valor: document.getElementById(ids.valor),
        decimales: ids.decimales,
      };
    }
    return elementos;
  }

  _aplicarRangos(rangos) {
    for (const [nombreParametro, referencias] of Object.entries(
      this._elementosSlider,
    )) {
      const rango = rangos[nombreParametro];
      if (!rango) {
        console.warn(`El backend no envió un rango para '${nombreParametro}'`);
        continue;
      }
      referencias.control.min = rango.minimo;
      referencias.control.max = rango.maximo;
      referencias.control.step = rango.paso;
      referencias.control.value = rango.valor_inicial;
      this._actualizarTextoValor(nombreParametro);
      this._actualizarEtiquetasRango(referencias.control, rango);
    }
  }

  /**
   * Actualiza el texto "mínimo ... máximo" bajo el slider (por ejemplo
   * "0.1 m ... 5 m"). Vive fijo en el HTML como marcador visual, pero el
   * número real siempre sale de rango (GET /api/configuracion): si no se
   * actualizara, quedaría desactualizado apenas configuracion.py cambiara
   * un mínimo o un máximo (como pasó con distancia_carga_m).
   */
  _actualizarEtiquetasRango(control, rango) {
    const [spanMinimo, spanMaximo] = control
      .closest(".control-deslizante")
      ?.querySelectorAll(".control-deslizante__rango span") ?? [];
    if (!spanMinimo || !spanMaximo) return;
    spanMinimo.textContent = `${rango.minimo} ${rango.unidad}`;
    spanMaximo.textContent = `${rango.maximo} ${rango.unidad}`;
  }

  /**
   * Crea un botón por cada género de generos_disponibles ({clave: nombre
   * legible}) y deja marcado el inicial. Ningún nombre se escribe a mano
   * aquí: todos vienen del backend. No envía nada todavía: recién al hacer
   * clic en uno (ver _elegirGenero) se manda el cambio, igual que un
   * <select> no dispara "change" solo por fijarle el valor inicial.
   */
  _aplicarGeneros(generosDisponibles, generoInicial) {
    this._botonesGenero = Object.entries(generosDisponibles).map(
      ([clave, nombre]) => {
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "boton";
        boton.textContent = nombre;
        boton.dataset.genero = clave;
        boton.addEventListener("click", () => this._elegirGenero(clave));
        return boton;
      },
    );
    this._grupoGenero.replaceChildren(...this._botonesGenero);
    this._nombreGeneroActual = generoInicial;
    this._marcarGeneroActivo(generoInicial);
    this._alCambiarGenero(generoInicial);
  }

  /** Se llama al hacer clic en un botón de género: marca, guarda y envía. */
  _elegirGenero(nombreGenero) {
    this._nombreGeneroActual = nombreGenero;
    this._marcarGeneroActivo(nombreGenero);
    this._alCambiarGenero(nombreGenero);
    // Las distancias vigentes pudieron quedar armadas para otro género (por
    // ejemplo, viniendo de primer género sin ninguna restricción entre
    // ellas): antes de enviar, se corrigen si hace falta para que este
    // cambio de género nunca llegue como una combinación inválida.
    this._forzarSeparacionSiHaceFalta();
    this._enviarParametros();
  }

  /** Resalta el botón del género activo (boton--primario) y apaga los demás. */
  _marcarGeneroActivo(nombreGenero) {
    for (const boton of this._botonesGenero) {
      const activo = boton.dataset.genero === nombreGenero;
      boton.classList.toggle("boton--primario", activo);
      boton.classList.toggle("boton--secundario", !activo);
      boton.setAttribute("aria-pressed", String(activo));
    }
  }

  /**
   * Para segundo y tercer género, cuál de las dos distancias debe quedar
   * más chica y cuál más grande (ver GeneroPalanca.validar_geometria en
   * backend/dominio/estatica.py). null en primer género: ahí no hay
   * restricción, así que tampoco hay acoplamiento.
   */
  _relacionGeneroActual() {
    if (this._nombreGeneroActual === GENERO_SEGUNDO) {
      // La carga debe quedar entre el fulcro y el esfuerzo.
      return { menor: "distancia_carga_m", mayor: "distancia_esfuerzo_m" };
    }
    if (this._nombreGeneroActual === GENERO_TERCERO) {
      // El esfuerzo debe quedar entre el fulcro y la carga.
      return { menor: "distancia_esfuerzo_m", mayor: "distancia_carga_m" };
    }
    return null;
  }

  /**
   * Si el género activo lo exige y la separación actual entre las dos
   * distancias es menor a un paso, empareja hacia mayorClave (el valor por
   * defecto cuando no sabemos cuál se está arrastrando, por ejemplo al
   * cambiar de género o al aplicar un preset).
   */
  _forzarSeparacionSiHaceFalta() {
    const relacion = this._relacionGeneroActual();
    if (!relacion) return;
    this._forzarSeparacion(relacion.menor, relacion.mayor, relacion.mayor);
  }

  /**
   * Se llama con cada "input" de un slider de distancia. Si el género activo
   * exige una separación mínima y arrastrar claveQueSeMovio la redujo por
   * debajo de un paso, mueve el OTRO slider junto con él (en el mismo
   * sentido), en vez de dejar que se crucen.
   */
  _acoplarDistancias(claveQueSeMovio) {
    const relacion = this._relacionGeneroActual();
    if (!relacion) return;
    const { menor, mayor } = relacion;
    const claveAAjustar = claveQueSeMovio === menor ? mayor : menor;
    this._forzarSeparacion(menor, mayor, claveAAjustar);
  }

  /**
   * Garantiza mayorClave >= menorClave + un paso. Ajusta primero
   * claveAAjustar; si esa no alcanza a abrir suficiente separación porque
   * chocaría con su propio mínimo o máximo, ajusta también la otra (así el
   * resultado siempre es válido, nunca solo "lo más cerca posible").
   */
  _forzarSeparacion(menorClave, mayorClave, claveAAjustar) {
    const controlMenor = this._elementosSlider[menorClave].control;
    const controlMayor = this._elementosSlider[mayorClave].control;
    const paso = Number(controlMenor.step);

    let valorMenor = Number(controlMenor.value);
    let valorMayor = Number(controlMayor.value);
    if (valorMayor - valorMenor >= paso) {
      return; // ya hay separación suficiente, no hay nada que acoplar
    }

    if (claveAAjustar === mayorClave) {
      valorMayor = Math.min(valorMenor + paso, Number(controlMayor.max));
      valorMenor = Math.min(valorMenor, valorMayor - paso);
    } else {
      valorMenor = Math.max(valorMayor - paso, Number(controlMenor.min));
      valorMayor = Math.max(valorMayor, valorMenor + paso);
    }

    controlMenor.value = valorMenor;
    controlMayor.value = valorMayor;
    this._actualizarTextoValor(menorClave);
    this._actualizarTextoValor(mayorClave);
  }

  _conectarEventos() {
    for (const nombreParametro of Object.keys(this._elementosSlider)) {
      const esDistancia =
        nombreParametro === "distancia_carga_m" ||
        nombreParametro === "distancia_esfuerzo_m";
      this._elementosSlider[nombreParametro].control.addEventListener(
        "input",
        () => {
          this._actualizarTextoValor(nombreParametro);
          if (esDistancia) {
            this._acoplarDistancias(nombreParametro);
          }
          this._enviarParametros();
        },
      );
    }

    this._selectorGravedad.addEventListener("change", () =>
      this._enviarParametros(),
    );

    this._botonPerturbar.addEventListener("click", () => {
      this._cliente.enviar({ tipo: TIPO_MENSAJE_SALIENTE.PERTURBAR });
    });

    this._botonReiniciar.addEventListener("click", () => {
      this._cliente.enviar({ tipo: TIPO_MENSAJE_SALIENTE.REINICIAR });
    });

    for (const boton of this._botonesPreset) {
      boton.addEventListener("click", () =>
        this._aplicarPreset(boton.dataset.preset),
      );
    }
  }

  /**
   * Copia un preset de presets_amortiguamiento a los sliders y lo envía,
   * exactamente como si la persona hubiera movido cada control a mano.
   *
   * A propósito NO toca el género: los presets son una demostración del
   * amortiguamiento (ζ), no del género, así que el backend siempre arma su
   * fuerza de equilibrio en primer género (ver
   * _construir_preset_amortiguamiento en esquemas.py) — pero esa fórmula es
   * la misma en los tres géneros, así que aplicar el preset conservando el
   * género que la persona ya tenga elegido sigue siendo válido.
   */
  _aplicarPreset(nombrePreset) {
    const preset = this._configuracion.presets_amortiguamiento?.[nombrePreset];
    if (!preset) {
      console.warn(`El backend no envió el preset '${nombrePreset}'`);
      return;
    }

    for (const nombreParametro of Object.keys(this._elementosSlider)) {
      this._elementosSlider[nombreParametro].control.value =
        preset[nombreParametro];
      this._actualizarTextoValor(nombreParametro);
    }
    this._selectorGravedad.value = preset.nombre_gravedad;
    // El preset trae distancias fijas pensadas para primer género (ver el
    // comentario de arriba); si segundo o tercer género está activo, se
    // corrigen para no violar su restricción geométrica.
    this._forzarSeparacionSiHaceFalta();
    this._enviarParametros();
  }

  _actualizarTextoValor(nombreParametro) {
    const referencias = this._elementosSlider[nombreParametro];
    const numero = Number(referencias.control.value);
    referencias.valor.textContent = numero.toFixed(referencias.decimales);
  }

  _enviarParametros() {
    this._cliente.enviar({
      tipo: TIPO_MENSAJE_SALIENTE.PARAMETROS,
      parametros: this.leerParametrosActuales(),
    });
  }
}
