# -*- coding: utf-8 -*-
"""Adaptador de validar_csf.py (Validación de Constancia de Situación Fiscal) para el registro."""

import os
import re

from . import validar_csf as _csf
from .registro import Herramienta


def _nombre_original(ruta):
    # La app guarda cada archivo como "0_Csf_XXXX.pdf"; se quita el prefijo.
    return re.sub(r"^\d+_", "", os.path.basename(ruta))


def ejecutar(rutas_archivos, carpeta_salida="salida", **_opciones):
    os.makedirs(carpeta_salida, exist_ok=True)
    archivos, resumen = _csf.main(
        rutas=list(rutas_archivos),
        carpeta_salida=carpeta_salida,
        consultar_sat=True,
        nombres=[_nombre_original(r) for r in rutas_archivos],
        devolver_resumen=True,
    )
    # Los PDF se descargan; el resumen se dibuja en la página (vista_validar_csf).
    return {"archivos": archivos, "resumen": resumen}


def mostrar_resumen(resumen):
    from .vista_validar_csf import mostrar   # importa streamlit solo en la app
    mostrar(resumen)


HERRAMIENTA = Herramienta(
    id="validar_csf",
    nombre="🛡️ Validar CSF",
    descripcion=(
        "Revisa si una Constancia de Situación Fiscal es auténtica o fue alterada: "
        "33 candados de seguridad, resultado en pantalla y reporte en PDF."
    ),
    multiple_archivos=True,
    tipos_permitidos=["pdf", "jpg", "jpeg", "png", "tif", "tiff", "webp"],
    ejecutar=ejecutar,
    mostrar_resumen=mostrar_resumen,
    ayuda_archivo=(
        "Sube el PDF tal como se descargó del SAT. Escaneos y fotos también se revisan "
        "(códigos y datos visibles), pero su autenticidad no se puede comprobar."
    ),
)
