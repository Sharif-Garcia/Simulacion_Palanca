"""Validadores de los parámetros que llegan desde el cliente.

El navegador NO es de fiar: aunque los sliders limiten los valores, alguien
puede enviar mensajes manualmente. Por eso el backend valida siempre y es la
autoridad final (los rangos vienen de configuracion.py, una sola fuente de
verdad).

Flujo:
    datos crudos (dict) -> validar_parametros() -> ParametrosPalanca válido

Si algo es inválido se lanza ParametroInvalidoError con el nombre del
parámetro, el valor recibido y el motivo.
"""

import math
from collections.abc import Mapping

from backend import configuracion
from backend.configuracion import RangoParametro
from backend.dominio.excepciones import ParametroInvalidoError
from backend.dominio.modelos import ParametrosPalanca

# Clave del parámetro que no es numérico (se elige por nombre, no por rango).
CLAVE_GRAVEDAD = "nombre_gravedad"


def convertir_a_numero_finito(nombre: str, valor: object) -> float:
    """Convierte el valor a float verificando que sea un número real y finito.

    Rechaza: texto, None, listas, booleanos, NaN, infinitos y enteros tan
    grandes que no caben en un float.
    """
    # bool es subclase de int en Python: True se colaría como 1 si no se excluye.
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ParametroInvalidoError(nombre, valor, "debe ser un número")

    try:
        numero = float(valor)
    except OverflowError:
        raise ParametroInvalidoError(nombre, valor, "el número es demasiado grande") from None

    if not math.isfinite(numero):
        raise ParametroInvalidoError(
            nombre, valor, "debe ser un número finito (sin NaN ni infinito)"
        )
    return numero


def validar_numero_en_rango(nombre: str, valor: object, rango: RangoParametro) -> float:
    """Valida que el valor sea un número finito dentro del rango indicado."""
    numero = convertir_a_numero_finito(nombre, valor)
    if not rango.contiene(numero):
        raise ParametroInvalidoError(
            nombre,
            valor,
            f"debe estar entre {rango.minimo} y {rango.maximo} {rango.unidad}",
        )
    return numero


def validar_nombre_gravedad(valor: object) -> str:
    """Valida que la gravedad elegida exista en la tabla de configuracion.py."""
    if not isinstance(valor, str) or valor not in configuracion.GRAVEDADES_M_S2:
        raise ParametroInvalidoError(
            CLAVE_GRAVEDAD,
            valor,
            f"debe ser uno de {list(configuracion.GRAVEDADES_M_S2)}",
        )
    return valor


def validar_parametros(datos: Mapping[str, object]) -> ParametrosPalanca:
    """Valida un diccionario de datos crudos y devuelve ParametrosPalanca.

    Los parámetros numéricos se recorren desde RANGOS_PARAMETROS, así que
    agregar uno nuevo en configuracion.py lo valida automáticamente (DRY).
    Requisito: cada clave de RANGOS_PARAMETROS debe coincidir con el nombre
    del campo correspondiente en ParametrosPalanca.

    Las claves desconocidas se ignoran; las que faltan generan error.
    """
    if not isinstance(datos, Mapping):
        raise ParametroInvalidoError("parametros", datos, "debe ser un objeto con pares clave-valor")

    valores_numericos: dict[str, float] = {}
    for nombre, rango in configuracion.RANGOS_PARAMETROS.items():
        if nombre not in datos:
            raise ParametroInvalidoError(nombre, None, "es obligatorio")
        valores_numericos[nombre] = validar_numero_en_rango(nombre, datos[nombre], rango)

    if CLAVE_GRAVEDAD not in datos:
        raise ParametroInvalidoError(CLAVE_GRAVEDAD, None, "es obligatorio")
    nombre_gravedad = validar_nombre_gravedad(datos[CLAVE_GRAVEDAD])

    return ParametrosPalanca(**valores_numericos, nombre_gravedad=nombre_gravedad)


def exigir_positivo(nombre: str, valor: float) -> float:
    """Devuelve el valor si es mayor que cero; si no, lanza ParametroInvalidoError.

    Escrito como 'not valor > 0' para que también rechace NaN, porque toda
    comparación con NaN da False.
    """
    if not valor > 0:
        raise ParametroInvalidoError(nombre, valor, "debe ser mayor que cero")
    return valor