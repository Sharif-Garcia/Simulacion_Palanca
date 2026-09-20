/**
 * Tarjeta "Constantes del modelo": rigidez, amortiguamiento, masa de la
 * barra, tolerancia de equilibrio y las gravedades disponibles.
 *
 * Son constantes fijas de configuracion.py: llegan una sola vez en GET
 * /api/configuracion y no cambian durante la sesión (a diferencia de
 * panelResultados.js, esta tarjeta no escucha ningún mensaje del
 * WebSocket). No calcula nada: solo muestra los números que ya vienen
 * calculados del backend.
 */
export class PanelConstantes {
  constructor() {
    this._rigidez = document.getElementById("constante-rigidez");
    this._amortiguamiento = document.getElementById(
      "constante-amortiguamiento",
    );
    this._masaBarra = document.getElementById("constante-masa-barra");
    this._tolerancia = document.getElementById("constante-tolerancia");
    this._gravedadTierra = document.getElementById(
      "constante-gravedad-tierra",
    );
    this._gravedadLuna = document.getElementById("constante-gravedad-luna");
    this._gravedadMarte = document.getElementById("constante-gravedad-marte");
  }

  /**
   * Se llama una sola vez, al iniciar, con la configuración que devolvió
   * GET /api/configuracion (la misma que ya usa Controles).
   */
  mostrar(configuracion) {
    this._rigidez.textContent =
      configuracion.rigidez_restauradora_n_m_rad.toFixed(0);
    this._amortiguamiento.textContent =
      configuracion.amortiguamiento_n_m_s_rad.toFixed(0);
    this._masaBarra.textContent = configuracion.masa_barra_kg.toFixed(1);
    this._tolerancia.textContent =
      configuracion.tolerancia_equilibrio_n_m.toFixed(1);

    const gravedades = configuracion.gravedades_m_s2;
    this._gravedadTierra.textContent = gravedades.Tierra.toFixed(2);
    this._gravedadLuna.textContent = gravedades.Luna.toFixed(2);
    this._gravedadMarte.textContent = gravedades.Marte.toFixed(2);
  }
}
