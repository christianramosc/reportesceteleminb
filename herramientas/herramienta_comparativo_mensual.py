# -*- coding: utf-8 -*-
"""Adaptador de comparativo_mensual_original.py (Reporte Comparativo Mensual) para el registro."""

import glob
import os
import shutil
import time

from . import comparativo_mensual_original as _comparativo
from .registro import Herramienta


def ejecutar(rutas_archivos, carpeta_salida="salida", nombres_meses=None, **_opciones):
    os.makedirs(carpeta_salida, exist_ok=True)
    marca_tiempo = time.time()

    _comparativo.main(rutas_locales=rutas_archivos, nombres_meses=nombres_meses)

    candidatos = [
        f for f in glob.glob("Reporte_Comparativo_*.pdf")
        if os.path.getmtime(f) >= marca_tiempo
    ]
    if not candidatos:
        return []

    ruta_generada = max(candidatos, key=os.path.getmtime)
    ruta_final = os.path.join(carpeta_salida, os.path.basename(ruta_generada))
    shutil.move(ruta_generada, ruta_final)
    return [ruta_final]


HERRAMIENTA = Herramienta(
    id="comparativo_mensual",
    nombre="📊 Comparativo Mensual",
    descripcion=(
        "Sube 2 o más Excel de la bitácora (uno por mes, mismo formato que "
        "el avance preliminar) y obtén el PDF comparativo entre esos meses: "
        "volumen, conversión, panorama financiero, GAP y desempeño por "
        "vendedor a lo largo del periodo."
    ),
    multiple_archivos=True,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="Un Excel por cada mes que quieras comparar (etiqueta de mes = nombre de la hoja).",
)
