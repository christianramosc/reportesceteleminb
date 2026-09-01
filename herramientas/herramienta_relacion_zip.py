# -*- coding: utf-8 -*-
"""Adaptador de bitacora_zip.py (Relación de clientes por STATUS) para el registro."""

from .bitacora_zip import procesar_zip_a_excel
from .registro import Herramienta


def ejecutar(rutas_archivos, carpeta_salida="salida", **_opciones):
    ruta_zip = rutas_archivos[0]
    ruta_excel = procesar_zip_a_excel(ruta_zip, carpeta_salida=carpeta_salida)
    return [ruta_excel]


HERRAMIENTA = Herramienta(
    id="relacion_zip",
    nombre="📁 Relación de Clientes (ZIP → Excel)",
    descripcion=(
        "Sube el ZIP del mes, con la misma estructura de siempre (una carpeta "
        "por STATUS: Aprobados, Rechazados, Contrapropuestas, etc., cada una "
        "con sus PDFs de Solicitud y Amortización). Se genera el Excel de la "
        "bitácora, listo para usarse en las otras herramientas de esta app."
    ),
    multiple_archivos=False,
    tipos_permitidos=["zip"],
    ejecutar=ejecutar,
)
