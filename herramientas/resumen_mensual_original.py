# -*- coding: utf-8 -*-
"""
REPORTE MENSUAL (RESUMEN) — mes ya cerrado.

La carga del Excel, la limpieza, los cálculos y las 10 gráficas NO viven
aquí: son iguales para los dos reportes y están en reporte_base.py. Este
archivo solo tiene lo que distingue a ESTE reporte: su portada, su
narrativa, el orden de sus secciones y sus conclusiones.

Si vas a corregir algo que aplica también al otro reporte, hazlo en
reporte_base.py — para eso existe.
"""

try:
    from .reporte_base import *          # noqa: F401,F403  (ver __all__ allí)
    from . import estatus as _est
    from . import reporte_base as _base
    from . import conclusiones as _conclusiones
    from . import pdf_util as _pdf_util
except ImportError:                       # ejecución suelta (Colab)
    from reporte_base import *            # noqa: F401,F403
    import estatus as _est
    import reporte_base as _base
    import conclusiones as _conclusiones
    import pdf_util as _pdf_util

import datetime
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from reportlab.lib import colors as rl_colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# Estos tres SÍ se redeclaran aquí (aunque estén en la base) porque los
# adaptadores de la app los reasignan sobre ESTE módulo antes de generar,
# y la portada los lee desde aquí.
NOMBRE_EMPRESA = "AUTOEXPRESS INBURSA"
SUBTITULO_EMPRESA = "MG Colima PYD"
NOMBRE_ANALISTA = "Christian Ramos"


def generar_reporte_pdf_verbal(df, resumen, tabla_vendedor, tabla_categoria,
                                nombre_archivo=None, recolectar_elementos=None):
    """
    Arma el reporte narrativo completo: portada con KPIs, resumen ejecutivo
    redactado, reporte detallado por sección (con tablas y gráficas) y
    conclusiones. Recibe los resultados ya calculados por
    resumen_general(), analisis_por_vendedor() y analisis_financiero_por_categoria()
    para no repetir esos cálculos ni duplicar la salida de consola.
    """
    if nombre_archivo is None:
        fecha_archivo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"Reporte_Bitacora_{fecha_archivo}.pdf"

    print("=" * 72)
    print(" GENERANDO REPORTE PDF NARRATIVO")
    print("=" * 72)

    rutas_graficas = generar_graficas_para_pdf(df)

    # -------------------------------------------------------------
    # Estilos
    # -------------------------------------------------------------
    # Estilos y maquetación vienen de reporte_base: eran ~220 líneas
    # idénticas en los dos reportes. Se reatan a nombres locales con la
    # misma grafía de antes para que la narrativa de abajo no cambie.
    _estilos = crear_estilos()
    styles = _estilos["styles"]
    estilo_kicker_portada = _estilos["kicker_portada"]
    estilo_titulo_portada = _estilos["titulo_portada"]
    estilo_subtitulo_portada = _estilos["subtitulo_portada"]
    estilo_meta_portada = _estilos["meta_portada"]
    estilo_h1 = _estilos["h1"]
    estilo_h2 = _estilos["h2"]
    estilo_cuerpo = _estilos["cuerpo"]
    estilo_nota = _estilos["nota"]
    estilo_kpi_valor = _estilos["kpi_valor"]
    estilo_kpi_label = _estilos["kpi_label"]
    estilo_encabezado_tabla = _estilos["encabezado_tabla"]
    estilo_encabezado_tabla_compacto = _estilos["encabezado_tabla_compacto"]

    FECHA_REPORTE = datetime.date.today().strftime("%d/%m/%Y")

    _maq = crear_maquetadores(
        _estilos, subtitulo="Reporte de Bitácora de Solicitudes",
        empresa=NOMBRE_EMPRESA, analista=NOMBRE_ANALISTA, fecha=FECHA_REPORTE,
    )
    encabezado_pie_pagina = _maq["encabezado_pie_pagina"]
    tabla_estilo_mg = _maq["tabla_estilo_mg"]
    tarjeta_kpi = _maq["tarjeta_kpi"]

    # -------------------------------------------------------------
    # Datos clave ya disponibles en `resumen` (de resumen_general),
    # más algunos cálculos adicionales para la narrativa
    # -------------------------------------------------------------
    total = resumen.get("total", len(df))
    financiados = resumen.get("financiados", 0)
    aprobados = resumen.get("aprobados", 0)
    rechazados = resumen.get("rechazados", 0)
    en_tramite = resumen.get("en_tramite", 0)
    tiene_categoria = "financiados" in resumen

    def pct(n):
        return (n / total * 100) if total else 0

    n_vendedores = int(tabla_vendedor.shape[0]) if tabla_vendedor is not None else 0

    top_solicitudes_nombres, top_solicitudes_val = ([], 0)
    top_financiado_nombres, top_financiado_val = ([], 0)
    top_monto_nombres, top_monto_val = ([], 0)
    top_gap_nombres, top_gap_val = ([], 0)
    top_gap_fin_nombres, top_gap_fin_val = ([], 0)

    if tabla_vendedor is not None and not tabla_vendedor.empty:
        top_solicitudes_nombres, top_solicitudes_val = _quienes_maximo(tabla_vendedor["Total"])
        if "FINANCIADO" in tabla_vendedor.columns:
            top_financiado_nombres, top_financiado_val = _quienes_maximo(tabla_vendedor["FINANCIADO"])
        if "Monto Financiado ($)" in tabla_vendedor.columns:
            top_monto_nombres, top_monto_val = _quienes_maximo(tabla_vendedor["Monto Financiado ($)"])
        if "GAP Total" in tabla_vendedor.columns:
            top_gap_nombres, top_gap_val = _quienes_maximo(tabla_vendedor["GAP Total"])
        if "GAP Financiado" in tabla_vendedor.columns:
            top_gap_fin_nombres, top_gap_fin_val = _quienes_maximo(tabla_vendedor["GAP Financiado"])

    modelo_top = None
    modelo_top_val = 0
    if "Vehículo" in df.columns and df["Vehículo"].dropna().shape[0] > 0:
        conteo_modelos = df["Vehículo"].dropna().value_counts()
        if not conteo_modelos.empty:
            modelo_top = conteo_modelos.index[0]
            modelo_top_val = int(conteo_modelos.iloc[0])

    # -------------------------------------------------------------
    # Construcción del documento
    # -------------------------------------------------------------
    elementos = []

    # --- Portada ---
    elementos.append(Spacer(1, 0.2 * cm))
    elementos.append(Paragraph("REPORTE MENSUAL&nbsp;&nbsp;·&nbsp;&nbsp;BITÁCORA DE SOLICITUDES", estilo_kicker_portada))
    elementos.append(Paragraph("Reporte de Análisis", estilo_titulo_portada))
    elementos.append(Paragraph(f"{NOMBRE_EMPRESA} · {SUBTITULO_EMPRESA}", estilo_subtitulo_portada))
    elementos.append(Spacer(1, 0.12 * cm))
    elementos.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor(GRIS_LINEA),
                                 spaceBefore=6, spaceAfter=10, hAlign="LEFT"))
    elementos.append(Paragraph(f"Elaborado por <b>{NOMBRE_ANALISTA}</b> el <b>{FECHA_REPORTE}</b>", estilo_meta_portada))
    elementos.append(Spacer(1, 0.45 * cm))

    # Las categorías se enumeran a partir de las que REALMENTE trae la
    # bitácora del mes, no de una lista fija de cuatro.
    _presentes = _est.categorias_presentes(df)
    _texto_clasificadas = (
        f"clasificadas en {len(_presentes)} estatus: "
        f"<b>{_est.frase_enumerada(_presentes)}</b>. "
        if _presentes else ""
    )
    intro_portada = Table(
        [[Paragraph(
            f"Este reporte resume el comportamiento de las {total} solicitudes de crédito automotriz "
            f"registradas en la bitácora, desde su ingreso hasta su cierre de mes, "
            f"{_texto_clasificadas}"
            f"Incluye el desempeño por vendedor, la colocación "
            f"del seguro GAP y los modelos de vehículo con mayor demanda.",
            estilo_cuerpo
        )]],
        colWidths=[18 * cm]
    )
    intro_portada.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(AZUL_PALIDO)),
        ("LINEBEFORE", (0, 0), (0, 0), 3, rl_colors.HexColor(INBURSA_AZUL)),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elementos.append(intro_portada)
    elementos.append(Spacer(1, 0.45 * cm))

    _kpi_gap = ""  # columna vacía angosta entre tarjetas, para que se vean separadas
    fila_kpis = [
        tarjeta_kpi(total, "Total de\nSolicitudes", MG_ROJO_OSCURO), _kpi_gap,
        tarjeta_kpi(financiados, "Financiadas", MG_ROJO_MEDIO), _kpi_gap,
        tarjeta_kpi(aprobados, "Aprobadas", MG_ROJO), _kpi_gap,
        tarjeta_kpi(n_vendedores, "Vendedores\nInvolucrados", INBURSA_AZUL),
    ]
    anchos_kpis = [4.0 * cm, 0.35 * cm, 4.0 * cm, 0.35 * cm, 4.0 * cm, 0.35 * cm, 4.0 * cm]
    tabla_kpis = Table([fila_kpis], colWidths=anchos_kpis)
    tabla_kpis.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    elementos.append(tabla_kpis)
    elementos.append(Spacer(1, 0.5 * cm))

    # --- Resumen Ejecutivo ---
    elementos.append(Paragraph("Resumen Ejecutivo", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor(MG_ROJO), spaceAfter=8))

    elementos.append(Paragraph("Panorama general", estilo_h2))
    if tiene_categoria:
        # El desglose enumera todas las categorías con solicitudes este mes.
        _desglose = _est.frase_desglose(resumen.get("conteo_categorias", {}), total)
        elementos.append(Paragraph(
            f"De las {total} solicitudes registradas en el periodo, {_desglose}.",
            estilo_cuerpo
        ))
        # La tabla agrupa por CATEGORÍA, no por el texto crudo del Excel: si la
        # bitácora trae "FINANCIADO" y "FINANCIADOS", ambos suman una sola
        # fila. Se ordena igual que las gráficas (del cierre más fuerte al
        # más débil) para que todo el reporte se lea con el mismo criterio.
        if resumen.get("conteo_categorias"):
            filas_status = [
                [_est.etiqueta(clave), int(n), f"{n/total*100:.1f}%"]
                for clave, n in resumen["conteo_categorias"].items() if n
            ]
            elementos.append(tabla_estilo_mg(
                [["Estatus", "Solicitudes", "% del total"]] + filas_status,
                col_widths=[7 * cm, 4 * cm, 4 * cm]
            ))

            # Si un mismo estatus se capturó con varias palabras distintas,
            # se avisa: es señal de captura inconsistente en la bitácora.
            variantes = {}
            for texto_crudo in resumen.get("desglose_status", {}).index:
                variantes.setdefault(clasificar_status(texto_crudo), set()).add(texto_crudo)
            mezclados = {c: v for c, v in variantes.items() if len(v) > 1}
            if mezclados:
                detalle = "; ".join(
                    f"{_est.etiqueta(c)}: " + ", ".join(sorted(v))
                    for c, v in mezclados.items()
                )
                elementos.append(Paragraph(
                    f"Nota: algunos estatus se capturaron con más de una palabra en la "
                    f"bitácora y aquí se agrupan en una sola fila ({detalle}).",
                    estilo_nota
                ))
    else:
        elementos.append(Paragraph(
            f"Se registraron {total} solicitudes en el periodo. No fue posible clasificarlas por Estatus "
            f"porque la columna 'ESTATUS' no está presente en el archivo fuente.",
            estilo_cuerpo
        ))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph("Panorama financiero", estilo_h2))
    partes_financiero = []
    if "monto_total" in resumen:
        partes_financiero.append(
            f"El monto total a financiar de todas las solicitudes asciende a <b>${resumen['monto_total']:,.2f}</b>."
        )
    if "monto_financiado" in resumen:
        partes_financiero.append(
            f"De ese total, ${resumen['monto_financiado']:,.2f} ya corresponden a crédito "
            f"<b>FINANCIADO</b> (dispersado)"
            + (f", con un ticket promedio de ${resumen['ticket_financiado']:,.2f} por crédito"
               if "ticket_financiado" in resumen else "") + "."
        )
    if "monto_aprobado" in resumen:
        partes_financiero.append(
            f"${resumen['monto_aprobado']:,.2f} están <b>APROBADOS</b> y en espera de dispersarse"
            + (f", con un ticket promedio de ${resumen['ticket_aprobado']:,.2f}"
               if "ticket_aprobado" in resumen else "") + "."
        )
    # Antes eran cuatro oraciones seguidas con la misma estructura ("El X
    # promedio es de Y"). Se funden en una sola enumeración.
    promedios = []
    if "pct_enganche" in resumen:
        promedios.append(f"un enganche del {resumen['pct_enganche']:.1f}% del precio de venta")
    if "plazo_promedio" in resumen:
        promedios.append(f"un plazo de {resumen['plazo_promedio']:.0f} meses")
    if "tasa_promedio" in resumen:
        promedios.append(f"una tasa anual del {resumen['tasa_promedio']:.2f}%")
    if "edad_promedio" in resumen:
        promedios.append(f"clientes de {resumen['edad_promedio']:.0f} años")
    if promedios:
        cuerpo = (", ".join(promedios[:-1]) + " y " + promedios[-1]
                  if len(promedios) > 1 else promedios[0])
        partes_financiero.append(f"En promedio, las solicitudes presentan {cuerpo}.")
    if partes_financiero:
        elementos.append(Paragraph(" ".join(partes_financiero), estilo_cuerpo))
    else:
        elementos.append(Paragraph(
            "No se encontraron columnas de monto, enganche, plazo o tasa en el archivo fuente para "
            "construir el panorama financiero.", estilo_nota
        ))
    elementos.append(Spacer(1, 0.6 * cm))

    elementos.append(Paragraph("Seguro GAP", estilo_h2))
    if "pct_gap" in resumen:
        texto_gap = (
            f"{resumen.get('n_gap', 0)} solicitudes ({resumen['pct_gap']:.1f}% del total) incluyen seguro GAP. "
        )
        if tiene_categoria and financiados:
            df_fin_gap_n = int((df.loc[df["Categoria"] == "FINANCIADO", "¿Tiene GAP?"] == "SI").sum()) if "¿Tiene GAP?" in df.columns else 0
            pct_gap_fin = (df_fin_gap_n / financiados * 100) if financiados else 0
            texto_gap += (
                f"Dentro de los créditos ya <b>FINANCIADOS</b>, {df_fin_gap_n} de {financiados} "
                f"({pct_gap_fin:.1f}%) llevan GAP colocado."
            )
            if "Monto GAP" in df.columns:
                monto_gap_fin = df.loc[(df["Categoria"] == "FINANCIADO") & (df["¿Tiene GAP?"] == "SI"), "Monto GAP"].sum()
                if monto_gap_fin:
                    texto_gap += f" El monto total colocado en GAP sobre financiados es de ${monto_gap_fin:,.2f}."
        elementos.append(Paragraph(texto_gap, estilo_cuerpo))
    else:
        elementos.append(Paragraph(
            "No se encontró la columna '¿Tiene GAP?' en el archivo fuente, por lo que no fue posible "
            "analizar la colocación de este seguro.", estilo_nota
        ))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph("Vendedores destacados", estilo_h2))
    if tabla_vendedor is not None and not tabla_vendedor.empty:
        texto_vend = f"Participan {n_vendedores} vendedores. "
        if top_solicitudes_nombres:
            texto_vend += (
                f"<b>{_nombres_y(top_solicitudes_nombres)}</b> "
                f"{'concentran' if len(top_solicitudes_nombres) > 1 else 'concentra'} el mayor número de "
                f"solicitudes generadas, con {int(top_solicitudes_val)}. "
            )
        if top_financiado_nombres:
            texto_vend += (
                f"En créditos <b>FINANCIADOS</b>, {_nombres_y(top_financiado_nombres)} "
                f"{'lideran' if len(top_financiado_nombres) > 1 else 'lidera'} con {int(top_financiado_val)}. "
            )
        if top_monto_nombres:
            texto_vend += (
                f"El mayor monto colocado en créditos financiados corresponde a "
                f"{_nombres_y(top_monto_nombres)}, con ${top_monto_val:,.2f}. "
            )
        if top_gap_fin_nombres:
            texto_vend += (
                f"En colocación de GAP sobre créditos financiados, "
                f"{_nombres_y(top_gap_fin_nombres)} {'destacan' if len(top_gap_fin_nombres) > 1 else 'destaca'} "
                f"con {int(top_gap_fin_val)}."
            )
        elementos.append(Paragraph(texto_vend, estilo_cuerpo))

        # Tabla por vendedor. El texto de arriba solo nombra a los que
        # destacan; esto da el panorama completo, incluido el GAP colocado
        # en créditos ya financiados.
        filas_vend, nota_vend, anchos_vend = filas_tabla_vendedor(tabla_vendedor)
        if filas_vend:
            elementos.append(Spacer(1, 0.25 * cm))
            elementos.append(KeepTogether(tabla_estilo_mg(
                filas_vend, col_widths=[a * cm for a in anchos_vend],
                fila_total=True,
            )))
            if nota_vend:
                elementos.append(Paragraph(nota_vend, estilo_nota))
    else:
        elementos.append(Paragraph(
            "No se encontró la columna 'Nombre del Vendedor' en el archivo fuente.", estilo_nota
        ))
    elementos.append(Spacer(1, 0.3 * cm))

    if modelo_top:
        elementos.append(Paragraph("Modelo más solicitado", estilo_h2))
        elementos.append(Paragraph(
            f"El vehículo más solicitado en el periodo es <b>{modelo_top}</b>, con {modelo_top_val} solicitudes.",
            estilo_cuerpo
        ))
        elementos.append(Spacer(1, 0.2 * cm))

    # --- Focos de atención ---
    # Lo que pide una acción va aquí, arriba, porque es lo primero que alguien
    # con poco tiempo debe leer. Los criterios (umbrales, tamaños mínimos de
    # muestra) viven en herramientas/conclusiones.py y son los mismos para los
    # cuatro reportes. Nada de esto se repite en las conclusiones del final.
    focos, conclusiones = _conclusiones.focos_y_conclusiones_mensual(
        df, "cierre", resumen=resumen)
    if focos:
        elementos.append(Paragraph("Focos de atención", estilo_h2))
        for nota in focos:
            elementos.append(Paragraph("•  " + nota, estilo_cuerpo))
        elementos.append(Spacer(1, 0.2 * cm))

    elementos.append(PageBreak())
    # === FIN RESUMEN EJECUTIVO — continúa el Reporte Detallado abajo ===

    # ===============================================================
    # REPORTE DETALLADO
    # Las secciones 1 a 6 son iguales en los dos reportes: viven en
    # reporte_base.secciones_detalladas(). Aquí solo van las tres frases
    # que sí cambian entre un corte preliminar y un cierre de mes.
    secciones_detalladas(
        elementos, _estilos,
        textos={
            "estatus": f"La primera gráfica cuenta las solicitudes de cada estatus; la dona muestra "
                       f"esos mismos estatus como proporción del total e indica qué vendedores "
                       f"aportan a cada uno.",
            "vendedores": f"Se registran {n_vendedores} vendedores con solicitudes en el periodo. "
                          f"La tabla desglosa, para cada uno, cuántas solicitudes generó, en qué estatus "
                          f"cerraron y su porcentaje de conversión a crédito financiado.",
            "modelos": "La siguiente gráfica muestra los modelos de vehículo con mayor número "
                       "de solicitudes en el periodo.",
        },
        df=df, rutas_graficas=rutas_graficas, tabla_vendedor=tabla_vendedor,
        tabla_categoria=tabla_categoria, tabla_estilo_mg=tabla_estilo_mg,
        n_vendedores=n_vendedores, modelo_top=modelo_top,
        modelo_top_val=modelo_top_val,
    )

    # ===============================================================
    elementos.append(Paragraph("Conclusiones y Factores Importantes", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor(MG_ROJO), spaceAfter=8))

    # `conclusiones` ya se calculó arriba junto con los focos.


    for c in conclusiones:
        elementos.append(Paragraph("•  " + c, estilo_cuerpo))

    # -------------------------------------------------------------
    # Generar el PDF
    # -------------------------------------------------------------
    doc = SimpleDocTemplate(
        nombre_archivo, pagesize=letter,
        topMargin=1.8 * cm, bottomMargin=1.3 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    # `recolectar_elementos`: si el llamador pasa una lista, aquí se le
    # deja una copia de todos los flowables del PDF. Es lo que usa
    # docx_reportes.py para generar el Word a partir de ESTE mismo
    # contenido, en vez de volver a redactarlo por su cuenta.
    # Se copia ANTES de doc.build() porque ReportLab va vaciando la lista
    # que recibe conforme la maqueta.
    # Sin esto, un Spacer que no cabe al final de una página genera una
    # hoja en blanco antes del siguiente salto. Ver pdf_util.py.
    elementos[:] = _pdf_util.quitar_espacios_antes_de_salto(elementos)
    if recolectar_elementos is not None:
        try:
            from . import flowables_a_docx as _fd
        except ImportError:
            import flowables_a_docx as _fd
        recolectar_elementos.extend(_fd.capturar_guion(elementos))

    doc.build(elementos, onFirstPage=encabezado_pie_pagina, onLaterPages=encabezado_pie_pagina)

    print(f"\nReporte PDF generado: {nombre_archivo}")
    if EN_COLAB:
        files.download(nombre_archivo)
    else:
        print(f"Archivo guardado en: {nombre_archivo}")

    return nombre_archivo


# =======================================================================
# 9) FLUJO PRINCIPAL
# =======================================================================

def main(ruta_local=None):
    df_crudo = cargar_archivo(ruta_local=ruta_local)
    df = limpiar_datos(df_crudo)

    resumen = resumen_general(df)
    tabla_vendedor = analisis_por_vendedor(df)
    tabla_categoria = analisis_financiero_por_categoria(df)

    generar_reporte_pdf_verbal(df, resumen, tabla_vendedor, tabla_categoria)

    print("=" * 72)
    print(" Análisis completo. Se generó un PDF narrativo con resumen ejecutivo,")
    print(" tablas con estilo y todas las gráficas explicadas.")
    print(" Puedes volver a correr esta celda con otro archivo.")
    print("=" * 72)

    return df

if __name__ == "__main__":
    main()
