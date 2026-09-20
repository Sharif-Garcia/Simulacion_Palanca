"""Excepciones propias del dominio de la palanca.

Todas heredan de PalancaError. Así, las capas superiores (por ejemplo la API)
pueden capturar un solo tipo de error esperado y dejar que los errores
inesperados (bugs) se propaguen y queden registrados.
"""


class PalancaError(Exception):
    """Error base de la aplicación: cualquier fallo esperado del simulador."""

    @property
    def detalle(self) -> str:
        """Texto legible pensado para mostrarse al usuario."""
        return str(self)


class ParametroInvalidoError(PalancaError):
    """Un parámetro de entrada no es válido (fuera de rango, NaN, tipo incorrecto)."""

    def __init__(self, nombre_parametro: str, valor: object, motivo: str) -> None:
        self.nombre_parametro = nombre_parametro
        self.valor = valor
        self.motivo = motivo
        super().__init__(f"Parámetro '{nombre_parametro}' inválido ({valor!r}): {motivo}")


class SimulacionInestableError(PalancaError):
    """La integración numérica produjo valores no finitos (NaN o infinito)."""

    def __init__(self, motivo: str = "la integración produjo valores no finitos") -> None:
        self.motivo = motivo
        super().__init__(f"Simulación inestable: {motivo}")


class MensajeMalformadoError(PalancaError):
    """Un mensaje recibido por el WebSocket no cumple el formato esperado."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(f"Mensaje malformado: {motivo}")