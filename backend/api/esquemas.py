"""Protocolo de mensajes del WebSocket entre el navegador y el servidor.

Mensajes del cliente al servidor (todos son objetos JSON con el campo "tipo"):
  - {"tipo": "parametros", "parametros": {masa_kg, distancia_carga_m,
        distancia_esfuerzo_m, fuerza_n, nombre_gravedad}}
  - {"tipo": "perturbar", "sentido": 1}      ("sentido" es opcional, 1 o -1)
  - {"tipo": "reiniciar"}

Mensajes del servidor al cliente:
  - {"tipo": "estado", ...}      en cada cuadro (unas 60 veces por segundo)
  - {"tipo": "resultados", ...}  al conectar y cada vez que cambian los parámetros
  - {"tipo": "error", "detalle": ..., "parametro": ...}

Este módulo solo traduce: convierte texto JSON en mensajes tipados y modelos
del dominio en diccionarios JSON. No abre conexiones ni ejecuta la simulación.
Los rangos NO se repiten aquí: los valida validadores.py (una sola fuente de
verdad, configuracion.py).
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from enum import Enum
from types import MappingProxyType

from backend import configuracion
from backend.dominio.excepciones import (
    MensajeMalformadoError,
    PalancaError,
    ParametroInvalidoError,
    SimulacionInestableError,
)
from backend.dominio.modelos import (
    EstadoSimulacion,
    ParametrosPalanca,
    ResultadosDinamicos,
    ResultadosEstaticos,
)
from backend.dominio.validadores import convertir_a_numero_finito, validar_parametros

CLAVE_TIPO = "tipo"
SENTIDO_POR_DEFECTO = 1.0


class TipoMensajeEntrante(str, Enum):
    """Tipos de mensaje que el cliente puede enviar."""

    PARAMETROS = "parametros"
    PERTURBAR = "perturbar"
    REINICIAR = "reiniciar"


class TipoMensajeSaliente(str, Enum):
    """Tipos de mensaje que el servidor puede enviar."""

    ESTADO = "estado"
    RESULTADOS = "resultados"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Mensajes entrantes ya interpretados (inmutables)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MensajeParametros:
    """El usuario cambió algún control. Los parámetros ya están validados."""

    parametros: ParametrosPalanca


@dataclass(frozen=True, slots=True)
class MensajePerturbar:
    """El usuario pulsó el botón de perturbación."""

    sentido: float


@dataclass(frozen=True, slots=True)
class MensajeReiniciar:
    """El usuario pidió volver al estado inicial."""


MensajeEntrante = MensajeParametros | MensajePerturbar | MensajeReiniciar


# ---------------------------------------------------------------------------
# Interpretación de mensajes entrantes
# ---------------------------------------------------------------------------
def _interpretar_parametros(contenido: Mapping[str, object]) -> MensajeParametros:
    if "parametros" not in contenido:
        raise MensajeMalformadoError("falta el campo 'parametros'")
    return MensajeParametros(parametros=validar_parametros(contenido["parametros"]))


def _interpretar_perturbar(contenido: Mapping[str, object]) -> MensajePerturbar:
    sentido = convertir_a_numero_finito(
        "sentido", contenido.get("sentido", SENTIDO_POR_DEFECTO)
    )
    return MensajePerturbar(sentido=sentido)


def _interpretar_reiniciar(contenido: Mapping[str, object]) -> MensajeReiniciar:
    return MensajeReiniciar()


# Registro de intérpretes (principio O): un mensaje nuevo se agrega con una
# función y una línea aquí, sin modificar interpretar_mensaje().
# Las claves son textos (.value) y no miembros del Enum: el hash de un Enum se
# calcula con su nombre, así que buscar por texto en un dict con claves Enum falla.
_INTERPRETES: Mapping[str, Callable[[Mapping[str, object]], MensajeEntrante]] = MappingProxyType(
    {
        TipoMensajeEntrante.PARAMETROS.value: _interpretar_parametros,
        TipoMensajeEntrante.PERTURBAR.value: _interpretar_perturbar,
        TipoMensajeEntrante.REINICIAR.value: _interpretar_reiniciar,
    }
)


def _decodificar(mensaje: str | bytes) -> str:
    """Obtiene el texto del mensaje; los bytes deben ser UTF-8 válido."""
    if isinstance(mensaje, str):
        return mensaje
    if isinstance(mensaje, (bytes, bytearray)):
        try:
            return bytes(mensaje).decode("utf-8")
        except UnicodeDecodeError:
            raise MensajeMalformadoError("no es texto UTF-8 válido") from None
    raise MensajeMalformadoError("debe ser texto")


def interpretar_mensaje(mensaje: str | bytes) -> MensajeEntrante:
    """Convierte el texto recibido en un mensaje tipado.

    Lanza MensajeMalformadoError si el formato es incorrecto (no es JSON, no
    es un objeto, falta el tipo o el tipo no existe) y ParametroInvalidoError
    si el formato es correcto pero un valor no es válido.
    """
    texto = _decodificar(mensaje)
    if len(texto) > configuracion.LONGITUD_MAXIMA_MENSAJE:
        raise MensajeMalformadoError(
            f"supera el tamaño máximo de {configuracion.LONGITUD_MAXIMA_MENSAJE} caracteres"
        )

    try:
        contenido = json.loads(texto)
    except (ValueError, RecursionError):
        # ValueError cubre JSON inválido; RecursionError, el anidado excesivo.
        raise MensajeMalformadoError("no es JSON válido") from None

    if not isinstance(contenido, dict):
        raise MensajeMalformadoError("debe ser un objeto JSON")

    tipo = contenido.get(CLAVE_TIPO)
    if not isinstance(tipo, str):
        raise MensajeMalformadoError("falta el campo 'tipo' o no es texto")

    interprete = _INTERPRETES.get(tipo)
    if interprete is None:
        raise MensajeMalformadoError(f"tipo de mensaje desconocido: {tipo!r}")
    return interprete(contenido)


# ---------------------------------------------------------------------------
# Serialización de mensajes salientes
# ---------------------------------------------------------------------------
def _valor_serializable(valor: object) -> object:
    """Los Enum viajan como su texto (por ejemplo "equilibrio")."""
    return valor.value if isinstance(valor, Enum) else valor


def _a_diccionario(instancia: object) -> dict[str, object]:
    """Convierte un dataclass en diccionario, con los Enum ya traducidos a texto."""
    return {
        campo.name: _valor_serializable(getattr(instancia, campo.name))
        for campo in fields(instancia)
    }


def serializar_estado(estado: EstadoSimulacion) -> dict[str, object]:
    """Mensaje 'estado': θ, ω, t y si la barra está en el tope."""
    return {
        CLAVE_TIPO: TipoMensajeSaliente.ESTADO.value,
        **_a_diccionario(estado),
        "angulo_grados": estado.angulo_grados,
    }


def serializar_resultados(
    estaticos: ResultadosEstaticos, dinamicos: ResultadosDinamicos
) -> dict[str, object]:
    """Mensaje 'resultados': W, F_eq, MA, R, ωn, ζ, etc.

    Solo cambia cuando cambian los parámetros, por eso no viaja en cada cuadro.
    """
    return {
        CLAVE_TIPO: TipoMensajeSaliente.RESULTADOS.value,
        "estaticos": _a_diccionario(estaticos),
        "dinamicos": _a_diccionario(dinamicos),
    }


def serializar_error(error: PalancaError) -> dict[str, object]:
    """Mensaje 'error'. Si falló un parámetro, indica cuál (para resaltar su control)."""
    parametro = error.nombre_parametro if isinstance(error, ParametroInvalidoError) else None
    return {
        CLAVE_TIPO: TipoMensajeSaliente.ERROR.value,
        "detalle": error.detalle,
        "parametro": parametro,
    }


def a_json(mensaje: Mapping[str, object]) -> str:
    """Serializa a JSON estricto y compacto.

    allow_nan=False impide enviar NaN o Infinity, que no son JSON válido y el
    navegador no podría leer. Si aparecen, es señal de una simulación inestable.
    """
    try:
        return json.dumps(mensaje, allow_nan=False, separators=(",", ":"), ensure_ascii=False)
    except ValueError:
        raise SimulacionInestableError("un valor no finito no se puede enviar al cliente") from None


def construir_configuracion_cliente() -> dict[str, object]:
    """Datos que el navegador necesita para armar sus controles (ruta GET /api/configuracion).

    Todo sale de configuracion.py: el frontend no repite rangos ni gravedades.
    """
    return {
        "rangos": {
            clave: asdict(rango) for clave, rango in configuracion.RANGOS_PARAMETROS.items()
        },
        "gravedades_m_s2": dict(configuracion.GRAVEDADES_M_S2),
        "gravedad_inicial": configuracion.GRAVEDAD_INICIAL,
        "limite_angulo_grados": configuracion.LIMITE_ANGULO_GRADOS,
        "frecuencia_cuadros_hz": configuracion.FRECUENCIA_CUADROS_HZ,
    }