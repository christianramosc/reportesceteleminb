# -*- coding: utf-8 -*-
"""Adaptador de avance_preliminar_original.py (Avance Preliminar Mensual) para el registro."""

import os
from datetime import date

from . import avance_preliminar_original as _avance
from .docx_reportes import generar_docx_avance
from .registro import Herramienta

# Valores originales del script, usados como default si el usuario no
# escribe nada en el campo de PDV / analista.
_PDV_DEFECTO = _avance.SUBTITULO_EMPRESA
_ANALISTA_DEFECTO = _avance.NOMBRE_ANALISTA


def ejecutar(rutas_archivos, carpeta_salida="salida", fecha_corte=None,
             nombre_pdv=None, nombre_analista=None, **_opciones):
    nombre_pdv = (nombre_pdv or "").strip() or _PDV_DEFECTO
    nombre_analista = (nombre_analista or "").strip() or _ANALISTA_DEFECTO

    # avance_preliminar_original.py usa estas constantes de módulo
    # directamente en la portada y el pie de página del PDF; las
    # ajustamos aquí para no tener que tocar ese archivo.
    _avance.SUBTITULO_EMPRESA = nombre_pdv
    _avance.NOMBRE_ANALISTA = nombre_analista

    os.makedirs(carpeta_salida, exist_ok=True)

    df_crudo = _avance.cargar_archivo(ruta_local=rutas_archivos[0])
    df = _avance.limpiar_datos(df_crudo)
    resumen = _avance.resumen_general(df)
    tabla_vendedor = _avance.analisis_por_vendedor(df)
    tabla_categoria = _avance.analisis_financiero_por_categoria(df)
    ctx = _avance.contexto_de_corte(fecha_corte)
    rutas_graficas = _avance.generar_graficas_para_pdf(df)

    marca = date.today().strftime("%Y%m%d_%H%M")
    ruta_pdf = os.path.join(carpeta_salida, f"Avance_Preliminar_{marca}.pdf")
    _avance.generar_reporte_pdf_avance(
        df, resumen, tabla_vendedor, tabla_categoria,
        nombre_archivo=ruta_pdf, fecha_corte=fecha_corte,
    )

    ruta_docx = generar_docx_avance(
        df, resumen, tabla_vendedor, tabla_categoria, rutas_graficas, ctx,
        nombre_pdv, nombre_analista,
        nombre_archivo=f"Avance_Preliminar_{marca}.docx",
        carpeta_salida=carpeta_salida,
    )

    return [ruta_pdf, ruta_docx]


HERRAMIENTA = Herramienta(
    id="avance_preliminar",
    nombre="📈 Avance Preliminar Mensual",
    descripcion=(
        "Sube el Excel de la bitácora del mes (el que genera la herramienta "
        "'Relación de Clientes') y obtén el PDF de avance preliminar más un "
        "Word editable con el mismo contenido."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes en curso.",
)
