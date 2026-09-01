# -*- coding: utf-8 -*-
"""Adaptador de avance_preliminar_original.py (Avance Preliminar Mensual) para el registro."""

import glob
import os
import shutil
import time

from . import avance_preliminar_original as _avance
from .registro import Herramienta


def ejecutar(rutas_archivos, carpeta_salida="salida", fecha_corte=None, **_opciones):
    os.makedirs(carpeta_salida, exist_ok=True)
    marca_tiempo = time.time()

    # main() genera el PDF con nombre automático (Avance_Preliminar_<fecha>.pdf)
    # en el directorio de trabajo actual del proceso.
    _avance.main(ruta_local=rutas_archivos[0], fecha_corte=fecha_corte)

    candidatos = [
        f for f in glob.glob("Avance_Preliminar_*.pdf")
        if os.path.getmtime(f) >= marca_tiempo
    ]
    if not candidatos:
        return []

    ruta_generada = max(candidatos, key=os.path.getmtime)
    ruta_final = os.path.join(carpeta_salida, os.path.basename(ruta_generada))
    shutil.move(ruta_generada, ruta_final)
    return [ruta_final]


HERRAMIENTA = Herramienta(
    id="avance_preliminar",
    nombre="📈 Avance Preliminar Mensual",
    descripcion=(
        "Sube el Excel de la bitácora del mes (el que genera la herramienta "
        "'Relación de Clientes') y obtén el PDF de avance preliminar, con "
        "resumen ejecutivo, tablas y gráficas, listo para revisar antes del "
        "cierre de mes."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes en curso.",
)
