# -*- coding: utf-8 -*-
"""
Genera la versión .docx (editable en Word) de los reportes de avance
preliminar y comparativo mensual.

No es una copia pixel-por-pixel del PDF: usa las MISMAS tablas, gráficas
e insights ya calculados por los scripts originales (no se recalcula ni
se redacta nada distinto salvo donde se indica), pero en un documento de
Word normal, para que cualquiera lo pueda editar libremente.
"""

import os
import re
from datetime import date

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROJO_MG = RGBColor(0xE4, 0x00, 0x2B)
GRIS_OSCURO = RGBColor(0x2B, 0x2B, 0x2B)

_PATRON_NEGRITAS = re.compile(r"<b>(.*?)</b>", re.DOTALL)


# =======================================================================
# Helpers genéricos (compartidos por ambos reportes)
# =======================================================================
def _preparar_documento(nombre_pdv):
    """Crea el documento en carta (Letter) con estilos base consistentes
    con la identidad MG Colima usada en los PDFs."""
    documento = Document()

    # Tamaño carta (Letter): 8.5 x 11 in = 21.59 x 27.94 cm
    for seccion in documento.sections:
        seccion.page_width = Cm(21.59)
        seccion.page_height = Cm(27.94)
        seccion.left_margin = Cm(2.2)
        seccion.right_margin = Cm(2.2)

    estilo_normal = documento.styles["Normal"]
    estilo_normal.font.name = "Calibri"
    estilo_normal.font.size = Pt(10.5)

    return documento


def _texto_con_negritas(parrafo, texto):
    """Convierte las marcas <b>...</b> (usadas en los insights del PDF con
    ReportLab) en runs en negritas dentro de un párrafo de Word."""
    posicion = 0
    for coincidencia in _PATRON_NEGRITAS.finditer(texto):
        if coincidencia.start() > posicion:
            parrafo.add_run(texto[posicion:coincidencia.start()])
        run_negrita = parrafo.add_run(coincidencia.group(1))
        run_negrita.bold = True
        posicion = coincidencia.end()
    if posicion < len(texto):
        parrafo.add_run(texto[posicion:])


def _agregar_encabezado(documento, nombre_empresa, nombre_pdv, subtitulo_reporte, nombre_analista):
    titulo = documento.add_heading(nombre_empresa, level=0)
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    titulo.runs[0].font.color.rgb = ROJO_MG

    subtitulo = documento.add_paragraph()
    subtitulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitulo.add_run(f"{subtitulo_reporte} · {nombre_pdv}")
    run.bold = True
    run.font.size = Pt(13)

    pie = documento.add_paragraph()
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_pie = pie.add_run(
        f"Elaborado por {nombre_analista}  ·  Generado el {date.today().strftime('%d/%m/%Y')}"
    )
    run_pie.font.size = Pt(9.5)
    run_pie.font.color.rgb = GRIS_OSCURO
    documento.add_paragraph()


def _dar_formato_encabezado_tabla(tabla):
    for celda in tabla.rows[0].cells:
        celda_fill = celda._tc.get_or_add_tcPr()
        sombra = celda_fill.makeelement(qn("w:shd"), {qn("w:val"): "clear", qn("w:fill"): "E4002B"})
        celda_fill.append(sombra)
        for parrafo in celda.paragraphs:
            parrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in parrafo.runs:
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.bold = True
                run.font.size = Pt(9)


def _agregar_tabla_dataframe(documento, df_tabla, nombre_columna_indice="", decimales_pct=True):
    """Inserta un pandas DataFrame (como tabla_vendedor / tabla_categoria /
    tabla_comp) como tabla de Word, con la primera columna = el índice."""
    df_mostrar = df_tabla.reset_index()
    if nombre_columna_indice:
        df_mostrar = df_mostrar.rename(columns={df_mostrar.columns[0]: nombre_columna_indice})

    columnas = [str(c) for c in df_mostrar.columns]
    tabla = documento.add_table(rows=1, cols=len(columnas))
    tabla.style = "Light Grid Accent 2"
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, nombre_col in enumerate(columnas):
        tabla.rows[0].cells[i].text = nombre_col
    _dar_formato_encabezado_tabla(tabla)

    for _, fila in df_mostrar.iterrows():
        celdas = tabla.add_row().cells
        for i, valor in enumerate(fila):
            if isinstance(valor, float):
                texto = f"{valor:,.1f}" if ("%" in columnas[i] and decimales_pct) else f"{valor:,.2f}"
            elif isinstance(valor, (int,)):
                texto = f"{valor:,}"
            else:
                texto = "" if pd.isna(valor) else str(valor)
            celdas[i].text = texto
            for parrafo in celdas[i].paragraphs:
                parrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in parrafo.runs:
                    run.font.size = Pt(8.5)

    documento.add_paragraph()
    return tabla


_TITULOS_GRAFICAS = {
    "status": "Solicitudes por estatus",
    "dona_categoria": "Distribución por categoría",
    "vendedores": "Solicitudes por vendedor",
    "vendedor_status": "Vendedor vs. estatus",
    "monto_por_vendedor": "Monto financiado por vendedor",
    "modelos": "Solicitudes por modelo",
    "gap_por_categoria": "GAP por categoría",
    "gap_por_vendedor": "GAP total por vendedor",
    "gap_vendedor_status": "GAP por vendedor y estatus",
    "gap_financiado_vend": "GAP financiado por vendedor",
    "totales_mes": "Totales por mes",
    "tasa_conversion": "Tasa de conversión por mes",
    "montos_mes": "Montos por mes",
    "gap_mes": "GAP por mes",
    "gap_vs_gap_fin_mes": "GAP vs. GAP financiado por mes",
    "gap_categoria_mes": "GAP por categoría y mes",
}


def _agregar_graficas(documento, rutas_graficas):
    documento.add_heading("Gráficas", level=1)
    for clave, ruta in rutas_graficas.items():
        if not ruta or not os.path.exists(ruta):
            continue
        documento.add_heading(_TITULOS_GRAFICAS.get(clave, clave.replace("_", " ").title()), level=2)
        documento.add_picture(ruta, width=Cm(15.5))
        parrafo_img = documento.paragraphs[-1]
        parrafo_img.alignment = WD_ALIGN_PARAGRAPH.CENTER


# =======================================================================
# Reporte: Avance Preliminar Mensual
# =======================================================================
def generar_docx_avance(df, resumen, tabla_vendedor, tabla_categoria, rutas_graficas, ctx,
                         nombre_pdv, nombre_analista, nombre_archivo=None, carpeta_salida="."):
    from . import avance_preliminar_original as _avance

    if nombre_archivo is None:
        fecha_archivo = date.today().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"Avance_Preliminar_{fecha_archivo}.docx"
    ruta_final = os.path.join(carpeta_salida, nombre_archivo)

    documento = _preparar_documento(nombre_pdv)
    _agregar_encabezado(documento, "AUTOEXPRESS INBURSA", nombre_pdv,
                        "Avance Preliminar de Bitácora", nombre_analista)

    documento.add_paragraph(
        f"Corte al día {ctx['dia_actual']} de {ctx['dias_en_mes']} de {ctx['nombre_mes']} "
        f"({ctx['pct_transcurrido']:.0f}% del mes transcurrido). Estos resultados son "
        f"preliminares: aún faltan {ctx['dias_restantes']} día(s) para el cierre de mes."
    ).italic = True

    # --- Resumen general (KPIs) ---
    documento.add_heading("Resumen General", level=1)
    total = resumen.get("total", 0)
    puntos = [f"Total de solicitudes ingresadas: {total}"]
    if "financiados" in resumen:
        puntos += [
            f"Financiadas (crédito dispersado): {resumen['financiados']} "
            f"({resumen['financiados']/total*100:.1f}%)",
            f"Aprobadas (aún sin dispersar): {resumen['aprobados']} "
            f"({resumen['aprobados']/total*100:.1f}%)",
            f"Rechazadas: {resumen['rechazados']} ({resumen['rechazados']/total*100:.1f}%)",
            f"Contrapropuesta / negociación: {resumen['en_tramite']} "
            f"({resumen['en_tramite']/total*100:.1f}%)",
        ]
    if "monto_financiado" in resumen:
        puntos.append(f"Monto FINANCIADO (ya dispersado): ${resumen['monto_financiado']:,.2f}")
    if "monto_aprobado" in resumen:
        puntos.append(f"Monto APROBADO (aún sin dispersar): ${resumen['monto_aprobado']:,.2f}")
    if "pct_enganche" in resumen:
        puntos.append(f"Enganche promedio sobre precio de venta: {resumen['pct_enganche']:.1f}%")
    if "plazo_promedio" in resumen:
        puntos.append(f"Plazo promedio solicitado: {resumen['plazo_promedio']:.0f} meses")
    if "tasa_promedio" in resumen:
        puntos.append(f"Tasa de interés anual promedio: {resumen['tasa_promedio']:.2f}%")
    if "pct_gap" in resumen:
        puntos.append(f"Solicitudes con GAP: {resumen['pct_gap']:.1f}% ({resumen.get('n_gap', 0)})")
    for punto in puntos:
        documento.add_paragraph(punto, style="List Bullet")

    # --- Tabla por vendedor ---
    if tabla_vendedor is not None and not tabla_vendedor.empty:
        documento.add_heading("Análisis por Vendedor", level=1)
        _agregar_tabla_dataframe(documento, tabla_vendedor, nombre_columna_indice="Vendedor")

    # --- Tabla financiera por categoría ---
    if tabla_categoria is not None and not tabla_categoria.empty:
        documento.add_heading("Panorama Financiero por Categoría", level=1)
        _agregar_tabla_dataframe(documento, tabla_categoria, nombre_columna_indice="Categoría")

    # --- Gráficas ---
    if rutas_graficas:
        _agregar_graficas(documento, rutas_graficas)

    # --- Conclusiones (editable; mismo criterio que el PDF, redactado aquí) ---
    documento.add_heading("Conclusiones", level=1)
    conclusiones = []
    if tabla_vendedor is not None and not tabla_vendedor.empty:
        if "Total" in tabla_vendedor.columns:
            nombres, valor = _avance._quienes_maximo(tabla_vendedor["Total"])
            if nombres:
                conclusiones.append(
                    f"<b>Carga de trabajo por vendedor:</b> {_avance._nombres_y(nombres)} "
                    f"concentra{'n' if len(nombres) > 1 else ''} el mayor número de solicitudes, con {int(valor)}."
                )
        if "FINANCIADO" in tabla_vendedor.columns:
            nombres, valor = _avance._quienes_maximo(tabla_vendedor["FINANCIADO"])
            if nombres:
                conclusiones.append(
                    f"<b>Mejor conversión a financiado:</b> {_avance._nombres_y(nombres)} "
                    f"lidera{'n' if len(nombres) > 1 else ''} con {int(valor)} crédito(s) dispersado(s)."
                )
        if "GAP Financiado" in tabla_vendedor.columns:
            nombres, valor = _avance._quienes_maximo(tabla_vendedor["GAP Financiado"])
            if nombres and valor:
                conclusiones.append(
                    f"<b>Venta cruzada de GAP:</b> {_avance._nombres_y(nombres)} "
                    f"destaca{'n' if len(nombres) > 1 else ''} colocando GAP en créditos ya financiados."
                )
    if resumen.get("incompletas"):
        conclusiones.append(
            f"<b>Datos pendientes de capturar:</b> {resumen['incompletas']} solicitud(es) "
            f"aún no tienen vehículo o monto asignado."
        )
    if not conclusiones:
        conclusiones.append("Sin hallazgos adicionales para este corte.")
    for texto in conclusiones:
        parrafo = documento.add_paragraph(style="List Bullet")
        _texto_con_negritas(parrafo, texto)

    documento.add_paragraph()
    nota = documento.add_paragraph()
    nota.add_run(
        "Este documento es la versión editable del reporte — modifica el texto, las "
        "tablas o el orden libremente antes de compartirlo."
    ).italic = True

    documento.save(ruta_final)
    return ruta_final


# =======================================================================
# Reporte: Comparativo Mensual
# =======================================================================
def generar_docx_comparativo(datos_por_mes, orden_meses, tabla_comp, df_combinado, rutas_graficas,
                              nombre_pdv, nombre_analista, nombre_archivo=None, carpeta_salida="."):
    from . import comparativo_mensual_original as _comparativo

    rango = f"{orden_meses[0].title()} a {orden_meses[-1].title()}" if len(orden_meses) > 1 else orden_meses[0].title()

    if nombre_archivo is None:
        fecha_archivo = date.today().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"Reporte_Comparativo_{fecha_archivo}.docx"
    ruta_final = os.path.join(carpeta_salida, nombre_archivo)

    documento = _preparar_documento(nombre_pdv)
    _agregar_encabezado(documento, "AUTOEXPRESS INBURSA", nombre_pdv,
                        f"Reporte Comparativo Mensual · {rango}", nombre_analista)

    # --- Tabla comparativa ---
    if tabla_comp is not None and not tabla_comp.empty:
        documento.add_heading("Tabla Comparativa Mensual", level=1)
        _agregar_tabla_dataframe(documento, tabla_comp, nombre_columna_indice="Mes")

    # --- Gráficas ---
    if rutas_graficas:
        _agregar_graficas(documento, rutas_graficas)

    # --- Insights automáticos (idénticos a los del PDF) ---
    documento.add_heading("Insights Automáticos", level=1)
    insights = _comparativo.generar_insights_automaticos(tabla_comp, orden_meses, datos_por_mes, df_combinado)
    for texto in insights:
        parrafo = documento.add_paragraph(style="List Bullet")
        _texto_con_negritas(parrafo, texto)

    documento.add_paragraph()
    nota = documento.add_paragraph()
    nota.add_run(
        "Este documento es la versión editable del reporte — modifica el texto, las "
        "tablas o el orden libremente antes de compartirlo."
    ).italic = True

    documento.save(ruta_final)
    return ruta_final
