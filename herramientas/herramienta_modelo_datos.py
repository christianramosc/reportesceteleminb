# -*- coding: utf-8 -*-
"""Adaptador de modelo_datos.py (base histórica en esquema estrella) para el registro."""

import os
import re

from . import modelo_datos as _md
from .modelo_datos_excel import exportar_excel
from .registro import Herramienta


def _nombre_original(ruta):
    # La app guarda cada archivo como "0_JULIO 2026.xlsx"; se quita el prefijo.
    return re.sub(r"^\d+_", "", os.path.basename(ruta))


def ejecutar(rutas_archivos, carpeta_salida="salida", nombres_meses=None, **_opciones):
    os.makedirs(carpeta_salida, exist_ok=True)
    bitacoras = _md.cargar_bitacoras(rutas_archivos, nombres_meses)
    modelo = _md.construir_modelo(bitacoras)

    meses = modelo["dim_mes"]
    tramo = meses.mes_corto.iloc[0] if len(meses) == 1 else \
        f"{meses.mes_corto.iloc[0]}-{meses.mes_corto.iloc[-1]}"
    nombre = f"Modelo_Datos_Bitacora_{tramo.replace(' ', '')}.xlsx"
    ruta = exportar_excel(modelo, os.path.join(carpeta_salida, nombre),
                          fuentes=[_nombre_original(r) for r in rutas_archivos],
                          carpeta_temporal=carpeta_salida)

    h = modelo["hechos_solicitud"]
    print(f"  Meses: {', '.join(meses.mes_anio)}")
    print(f"  {len(modelo['hechos_estatus_mes'])} renglones -> {len(h)} solicitudes únicas "
          f"({int(h.cruzo_mes.sum())} cruzaron de mes)")
    if len(modelo["calidad_datos"]):
        print(f"  Avisos de calidad: {len(modelo['calidad_datos'])} (ver hoja calidad_datos)")
    return [ruta]


HERRAMIENTA = Herramienta(
    id="modelo_datos",
    nombre="🗂️ Modelo de Datos",
    descripcion=(
        "Sube las bitácoras de todos los meses que tengas (una por mes) y obtén "
        "una sola base histórica ordenada como modelo de datos (esquema estrella): "
        "una tabla de solicitudes sin duplicar los folios que cruzan de mes, la foto "
        "de cada bitácora y catálogos de mes, vendedor, vehículo, estatus y cliente. "
        "Listo para Power BI o tablas dinámicas. No incluye nombre, teléfono ni "
        "correo de los clientes."
    ),
    multiple_archivos=True,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="Un Excel por mes. El mes y el año se toman del nombre de la hoja (ej. 'SEPTIEMBRE 2026').",
)
