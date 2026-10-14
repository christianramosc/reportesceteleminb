# -*- coding: utf-8 -*-
"""Adaptador de avance_preliminar_original.py (Avance Preliminar Mensual) para el registro."""

import os

from . import avance_preliminar_original as _avance
from .docx_reportes import generar_docx_avance
from . import conclusiones as _c
from .ficha_resumen import generar_ficha_segura, ficha_mensual
from .libros_analisis import libro_mensual
from .nombres import marca_fecha
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

    base = f"Avance_{marca_fecha()}"
    ruta_pdf = os.path.join(carpeta_salida, f"{base}.pdf")

    # El PDF deja aquí sus flowables y el Word se construye con ESOS mismos
    # elementos, para que ambos documentos digan exactamente lo mismo.
    elementos_pdf = []
    # El nombre de la hoja ("JULIO 2026") es la única pista del mes al que
    # pertenecen los datos. Se usa para advertir si la fecha de corte cae en
    # otro mes: sin esto, correr el avance sobre un mes ya cerrado afirmaba
    # "quedan 10 días para el cierre".
    try:
        import pandas as _pd
        hoja = _pd.ExcelFile(rutas_archivos[0]).sheet_names[0]
    except Exception:
        hoja = None

    _avance.generar_reporte_pdf_avance(
        df, resumen, tabla_vendedor, tabla_categoria,
        nombre_archivo=ruta_pdf, fecha_corte=fecha_corte,
        recolectar_elementos=elementos_pdf, hoja=hoja,
    )

    ruta_docx = generar_docx_avance(
        elementos_pdf, nombre_pdv, nombre_analista,
        nombre_archivo=f"{base}.docx",
        carpeta_salida=carpeta_salida,
    )

    # Libro de análisis: las mismas tablas del reporte pero con fórmulas
    # vivas, para que quien lo reciba pueda auditarlas o rehacer el corte
    # por su cuenta sin volver a ejecutar la herramienta.
    ruta_xlsx = os.path.join(carpeta_salida, f"{base}.xlsx")
    libro_mensual(df, ruta_xlsx, "Avance Preliminar — datos y cálculos",
                  os.path.basename(rutas_archivos[0]))

    # Ficha de una página (PNG) para mandar por WhatsApp.
    periodo = f"Corte al {ctx['dia_actual']} de {ctx['nombre_mes']} de {ctx['fecha_corte'].year}"
    if hoja:
        # Si la hoja es del mismo mes del corte, no se repite mes y año.
        if _c.mes_desde_hoja(hoja) == ctx["fecha_corte"].month:
            periodo = f"{str(hoja).strip().title()}  ·  corte al día {ctx['dia_actual']}"
        else:
            periodo = f"{str(hoja).strip().title()}  ·  {periodo.lower()}"
    ruta_png = generar_ficha_segura(
        ficha_mensual, df, os.path.join(carpeta_salida, f"{base}.png"),
        modo="avance", periodo=periodo, pdv=nombre_pdv, analista=nombre_analista,
        resumen=resumen, ctx=ctx, hoja=hoja)

    return [ruta_pdf, ruta_docx, ruta_xlsx] + ([ruta_png] if ruta_png else [])


HERRAMIENTA = Herramienta(
    id="avance_preliminar",
    nombre="📈 Avance Preliminar Mensual",
    descripcion=(
        "Sube el Excel de la bitácora del mes (el que genera la herramienta "
        "'Relación de Clientes') y obtén el PDF de avance preliminar, un "
        "Word editable con el mismo contenido y una ficha de una página "
        "(imagen) para compartir por WhatsApp."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes en curso.",
)
