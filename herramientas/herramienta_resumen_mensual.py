# -*- coding: utf-8 -*-
"""Adaptador de resumen_mensual_original.py (Resumen Mensual / cierre de mes) para el registro."""

import os
from datetime import date

from . import resumen_mensual_original as _resumen
from .docx_reportes import generar_docx_resumen
from .registro import Herramienta

# Valores originales del script, usados como default si el usuario no
# escribe nada en el campo de PDV / analista.
_PDV_DEFECTO = _resumen.SUBTITULO_EMPRESA
_ANALISTA_DEFECTO = _resumen.NOMBRE_ANALISTA


def ejecutar(rutas_archivos, carpeta_salida="salida", nombre_pdv=None,
             nombre_analista=None, **_opciones):
    nombre_pdv = (nombre_pdv or "").strip() or _PDV_DEFECTO
    nombre_analista = (nombre_analista or "").strip() or _ANALISTA_DEFECTO

    # resumen_mensual_original.py usa estas constantes de módulo
    # directamente en la portada y el pie de página del PDF; las
    # ajustamos aquí para no tener que tocar ese archivo.
    _resumen.SUBTITULO_EMPRESA = nombre_pdv
    _resumen.NOMBRE_ANALISTA = nombre_analista

    os.makedirs(carpeta_salida, exist_ok=True)

    df_crudo = _resumen.cargar_archivo(ruta_local=rutas_archivos[0])
    df = _resumen.limpiar_datos(df_crudo)
    resumen = _resumen.resumen_general(df)
    tabla_vendedor = _resumen.analisis_por_vendedor(df)
    tabla_categoria = _resumen.analisis_financiero_por_categoria(df)

    marca = date.today().strftime("%Y%m%d_%H%M")
    ruta_pdf = os.path.join(carpeta_salida, f"Resumen_Mensual_{marca}.pdf")

    # El PDF deja aquí sus flowables y el Word se construye con ESOS mismos
    # elementos, para que ambos documentos digan exactamente lo mismo.
    elementos_pdf = []
    _resumen.generar_reporte_pdf_verbal(
        df, resumen, tabla_vendedor, tabla_categoria,
        nombre_archivo=ruta_pdf,
        recolectar_elementos=elementos_pdf,
    )

    ruta_docx = generar_docx_resumen(
        elementos_pdf, nombre_pdv, nombre_analista,
        nombre_archivo=f"Resumen_Mensual_{marca}.docx",
        carpeta_salida=carpeta_salida,
    )

    return [ruta_pdf, ruta_docx]


HERRAMIENTA = Herramienta(
    id="resumen_mensual",
    nombre="🗓️ Resumen Mensual",
    descripcion=(
        "Sube el Excel de la bitácora del mes ya cerrado y obtén el PDF de "
        "resumen mensual (cierre de mes) más un Word editable con el mismo "
        "contenido."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes ya cerrado.",
)
