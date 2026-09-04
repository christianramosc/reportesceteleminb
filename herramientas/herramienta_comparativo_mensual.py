# -*- coding: utf-8 -*-
"""Adaptador de comparativo_mensual_original.py (Reporte Comparativo Mensual) para el registro."""

import os
from datetime import date

import pandas as pd

from . import comparativo_mensual_original as _comparativo
from .docx_reportes import generar_docx_comparativo
from .registro import Herramienta

_PDV_DEFECTO = _comparativo.SUBTITULO_EMPRESA
_ANALISTA_DEFECTO = _comparativo.NOMBRE_ANALISTA


def ejecutar(rutas_archivos, carpeta_salida="salida", nombres_meses=None,
             nombre_pdv=None, nombre_analista=None, **_opciones):
    nombre_pdv = (nombre_pdv or "").strip() or _PDV_DEFECTO
    nombre_analista = (nombre_analista or "").strip() or _ANALISTA_DEFECTO

    _comparativo.SUBTITULO_EMPRESA = nombre_pdv
    _comparativo.NOMBRE_ANALISTA = nombre_analista

    os.makedirs(carpeta_salida, exist_ok=True)

    archivos = _comparativo.cargar_multiples_archivos(rutas_archivos, nombres_meses)

    datos_por_mes = {}
    for mes, df_crudo in archivos:
        df = _comparativo.limpiar_datos(df_crudo, mes=mes)
        resumen = _comparativo.resumen_general(df, mes=mes)
        tabla_vendedor = _comparativo.analisis_por_vendedor(df)
        tabla_categoria = _comparativo.analisis_financiero_por_categoria(df)
        datos_por_mes[mes] = {
            "df": df, "resumen": resumen,
            "tabla_vendedor": tabla_vendedor, "tabla_categoria": tabla_categoria,
        }

    orden_meses = sorted(
        datos_por_mes.keys(),
        key=lambda m: (_comparativo._orden_mes(m), list(datos_por_mes.keys()).index(m)),
    )
    tabla_comp = _comparativo.construir_tabla_comparativa(datos_por_mes, orden_meses)
    df_combinado = pd.concat([datos_por_mes[m]["df"] for m in orden_meses], ignore_index=True)
    rutas_graficas = _comparativo.generar_graficas_comparativas(datos_por_mes, orden_meses, tabla_comp, df_combinado)

    marca = date.today().strftime("%Y%m%d_%H%M")
    ruta_pdf = os.path.join(carpeta_salida, f"Reporte_Comparativo_{marca}.pdf")
    # El Word se arma con los mismos flowables que el PDF (ver docx_reportes).
    elementos_pdf = []
    _comparativo.generar_reporte_pdf_comparativo(
        datos_por_mes, orden_meses, tabla_comp, df_combinado, nombre_archivo=ruta_pdf,
        recolectar_elementos=elementos_pdf,
    )

    ruta_docx = generar_docx_comparativo(
        elementos_pdf, nombre_pdv, nombre_analista,
        nombre_archivo=f"Reporte_Comparativo_{marca}.docx",
        carpeta_salida=carpeta_salida,
    )

    return [ruta_pdf, ruta_docx]


HERRAMIENTA = Herramienta(
    id="comparativo_mensual",
    nombre="📊 Comparativo Mensual",
    descripcion=(
        "Sube 2 o más Excel de la bitácora (uno por mes, mismo formato que "
        "el avance preliminar) y obtén el PDF comparativo entre esos meses "
        "más un Word editable con el mismo contenido."
    ),
    multiple_archivos=True,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="Un Excel por cada mes que quieras comparar (etiqueta de mes = nombre de la hoja).",
)
