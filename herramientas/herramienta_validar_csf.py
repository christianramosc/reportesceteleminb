# -*- coding: utf-8 -*-
"""Adaptador de validar_csf.py (Validación de Constancia de Situación Fiscal) para el registro."""

import os
import re

from . import validar_csf as _csf
from .registro import Herramienta


def _nombre_original(ruta):
    # La app guarda cada archivo como "0_Csf_XXXX.pdf"; se quita el prefijo.
    return re.sub(r"^\d+_", "", os.path.basename(ruta))


def ejecutar(rutas_archivos, carpeta_salida="salida", nombre_pdv=None,
             nombre_analista=None, **_opciones):
    os.makedirs(carpeta_salida, exist_ok=True)
    archivos, resumen = _csf.main(
        rutas=list(rutas_archivos),
        carpeta_salida=carpeta_salida,
        analista=(nombre_analista or "").strip(),
        pdv=(nombre_pdv or "").strip(),
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
        "Sube una o varias Constancias de Situación Fiscal (el PDF descargado del SAT) y "
        "obtén un PDF por constancia con más de 30 candados revisados: que el archivo no "
        "se haya editado ni re-guardado, que los QR lleven al portal oficial del SAT y "
        "coincidan con el RFC e idCIF, que RFC, CURP, fechas, régimen y domicilio sean "
        "coherentes, y la vigencia del boletín BMGFS (último mes). No sustituye escanear "
        "el QR: el reporte trae los links para hacerlo."
    ),
    multiple_archivos=True,
    tipos_permitidos=["pdf", "jpg", "jpeg", "png"],
    ejecutar=ejecutar,
    mostrar_resumen=mostrar_resumen,
    ayuda_archivo=(
        "El PDF tal como se descargó del SAT, sin abrirlo ni guardarlo en otro programa. "
        "Las fotos o capturas se aceptan solo para leer el QR: no se pueden validar."
    ),
)
