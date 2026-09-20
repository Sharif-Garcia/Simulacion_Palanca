/**
 * Punto de entrada de la aplicación.
 *
 * Responsabilidad única: construir cada módulo, conectarlos entre sí (quién
 * escucha qué mensaje) y arrancar el bucle de dibujo. No calcula física, no
 * toca el DOM directamente y no valida nada: eso ya lo hace cada módulo.
 */

import { ClienteWebSocket } from "./red/clienteWebSocket.js";
import { Controles } from "./ui/controles.js";
import { PanelResultados } from "./ui/panelResultados.js";
import { PanelConstantes } from "./ui/panelConstantes.js";
import { RenderizadorPalanca } from "./render/renderizadorPalanca.js";
import { GraficaAngulo } from "./render/graficaAngulo.js";
import { URL_WEBSOCKET, TIPO_MENSAJE } from "./configuracion.js";

const ID_LIENZO_PALANCA = "lienzo-palanca";
const ID_LIENZO_GRAFICA = "lienzo-grafica";

async function iniciar() {
  const renderizadorPalanca = new RenderizadorPalanca(ID_LIENZO_PALANCA);
  const graficaAngulo = new GraficaAngulo(ID_LIENZO_GRAFICA);
  const panelResultados = new PanelResultados();
  const panelConstantes = new PanelConstantes();

  // Único estado "vivo" que necesita el bucle de dibujo; todo lo demás
  // reacciona a los mensajes en el momento en que llegan.
  let ultimoEstado = null;

  const cliente = new ClienteWebSocket(URL_WEBSOCKET, {
    alRecibirMensaje: (mensaje) => manejarMensaje(mensaje),
    alCambiarEstado: (estado) => panelResultados.mostrarEstadoConexion(estado),
  });

  const controles = new Controles(cliente);

  function manejarMensaje(mensaje) {
    switch (mensaje.tipo) {
      case TIPO_MENSAJE.ESTADO:
        ultimoEstado = mensaje;
        graficaAngulo.agregarPunto(mensaje);
        panelResultados.actualizarEstado(mensaje);
        break;
      case TIPO_MENSAJE.RESULTADOS:
        panelResultados.actualizarResultados(mensaje);
        break;
      case TIPO_MENSAJE.ERROR:
        panelResultados.mostrarError(mensaje);
        break;
      default:
        console.warn("Tipo de mensaje desconocido:", mensaje.tipo);
    }
  }

  function dibujar() {
    if (ultimoEstado) {
      renderizadorPalanca.dibujar(
        ultimoEstado,
        controles.leerParametrosActuales(),
      );
      graficaAngulo.dibujar();
    }
    requestAnimationFrame(dibujar);
  }

  await controles.inicializar();

  const rangos = controles.obtenerRangos();
  renderizadorPalanca.establecerLimites(
    rangos.distancia_esfuerzo_m.maximo,
    rangos.distancia_carga_m.maximo,
  );

  const configuracionServidor = controles.obtenerConfiguracionCompleta();
  graficaAngulo.establecerLimiteAngulo(
    configuracionServidor.limite_angulo_grados,
  );
  panelConstantes.mostrar(configuracionServidor);

  cliente.conectar();
  requestAnimationFrame(dibujar);
}

iniciar().catch((error) => {
  console.error("No se pudo iniciar la aplicación:", error);
});
