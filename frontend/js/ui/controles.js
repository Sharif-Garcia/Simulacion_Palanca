/**
 * Controles del usuario: sliders de masa, distancias, fuerza, selector de
 * gravedad y botones de perturbar/reiniciar.
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
 *
 * No dibuja el resultado ni el estado: eso lo hace panelResultados.js al
 * recibir los mensajes de vuelta.
 */

import { TIPO_MENSAJE_SALIENTE, URL_CONFIGURACION } from "../configuracion.js";

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
const ID_BOTON_PERTURBAR = "boton-perturbar";
const ID_BOTON_REINICIAR = "boton-reiniciar";
// Cada botón de preset trae en data-preset la clave que usar en
// presets_amortiguamiento (coincide con TipoRespuesta en el backend).
const SELECTOR_BOTONES_PRESET = "[data-preset]";

export class Controles {
  /**
   * @param {import("../red/clienteWebSocket.js").ClienteWebSocket} clienteWebSocket
   */
  constructor(clienteWebSocket) {
    this._cliente = clienteWebSocket;
    this._elementosSlider = this._obtenerElementosSlider();
    this._selectorGravedad = document.getElementById(ID_SELECTOR_GRAVEDAD);
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
    const parametros = { nombre_gravedad: this._selectorGravedad.value };
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
    }
  }

  _conectarEventos() {
    for (const nombreParametro of Object.keys(this._elementosSlider)) {
      this._elementosSlider[nombreParametro].control.addEventListener(
        "input",
        () => {
          this._actualizarTextoValor(nombreParametro);
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
