"""
REPORTE MENSUAL DE LA BITÁCORA — en dos modos:

  · modo="avance": corte a mitad de mes (Avance Preliminar). Ubica el corte
    en el calendario ("día 15 de 31"), dice cuántos días quedan y qué
    solicitudes todavía pueden convertirse.
  · modo="cierre": mes ya cerrado (Resumen Mensual).

Antes eran dos archivos (avance_preliminar_original.py y
resumen_mensual_original.py) iguales en un 84%: cada arreglo había que
aplicarlo dos veces. Ahora el cuerpo es uno solo y lo que cambia entre los
dos modos está marcado con `es_avance`.

La carga del Excel, la limpieza, los cálculos y las gráficas viven en
reporte_base.py; aquí solo están la portada, la narrativa y el orden de
las secciones.
"""

import os

from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

from . import conclusiones as _conclusiones
from . import estatus as _est
from . import fechas as _fechas   # hora de México, no la del servidor
from . import lateral as _lateral
from . import pdf_util as _pdf_util
from .config import DatosReporte
from .reporte_base import (
    GRIS_LINEA,
    MG_ROJO,
    clasificar_status,
    contexto_de_corte,
    crear_estilos,
    crear_maquetadores,
    filas_tabla_vendedor,
    generar_graficas_para_pdf,
    secciones_detalladas,
)

MODOS = ("avance", "cierre")


def generar_reporte_pdf(df, resumen, tabla_vendedor, tabla_categoria, modo,
                        nombre_archivo=None, fecha_corte=None,
                        recolectar_elementos=None, hoja=None, datos=None,
                        carpeta_graficas=None):
    """
    Arma el reporte: portada con KPIs, resumen ejecutivo redactado, reporte
    detallado por sección (con tablas y gráficas) y conclusiones. Recibe los
    resultados ya calculados por resumen_general(), analisis_por_vendedor()
    y analisis_financiero_por_categoria() para no repetir esos cálculos.

    modo: "avance" (corte a mitad de mes) o "cierre" (mes cerrado).
    fecha_corte: solo en modo avance. Fecha del corte (por defecto, hoy):
        ubica el corte en el calendario del mes y fecha la portada.
    hoja: nombre de la hoja del Excel ("JULIO 2026"). En modo avance sirve
        para advertir si la fecha de corte cae en otro mes.
    datos: PDV, implant y empresa (config.DatosReporte); por defecto, los de config.
    carpeta_graficas: dónde dibujar las gráficas (por defecto, junto al PDF).
    """
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}, no {modo!r}")
    es_avance = modo == "avance"
    datos = datos or DatosReporte()
    ctx = contexto_de_corte(fecha_corte) if es_avance else None

    if nombre_archivo is None:
        fecha_archivo = _fechas.ahora().strftime("%Y%m%d_%H%M")
        prefijo = "Avance_Preliminar" if es_avance else "Reporte_Bitacora"
        nombre_archivo = f"{prefijo}_{fecha_archivo}.pdf"

    print("=" * 72)
    print(" GENERANDO REPORTE PDF DE AVANCE PRELIMINAR" if es_avance
          else " GENERANDO REPORTE PDF NARRATIVO")
    print("=" * 72)

    # Las gráficas van en una carpeta junto al PDF (en la app, dentro del
    # temporal de la corrida, que se borra al terminar). Antes era una
    # carpeta fija en la raíz, compartida por todas las corridas.
    carpeta_graficas = carpeta_graficas or os.path.join(
        os.path.dirname(os.path.abspath(nombre_archivo)), "graficas")
    rutas_graficas = generar_graficas_para_pdf(df, carpeta_graficas)

    # -------------------------------------------------------------
    # Estilos
    # -------------------------------------------------------------
    _estilos = crear_estilos()
    estilo_kicker_portada = _estilos["kicker_portada"]
    estilo_titulo_portada = _estilos["titulo_portada"]
    estilo_subtitulo_portada = _estilos["subtitulo_portada"]
    estilo_meta_portada = _estilos["meta_portada"]
    estilo_h1 = _estilos["h1"]
    estilo_h2 = _estilos["h2"]
    estilo_cuerpo = _estilos["cuerpo"]
    estilo_nota = _estilos["nota"]

    FECHA_REPORTE = (ctx["fecha_corte"] if es_avance else _fechas.hoy()).strftime("%d/%m/%Y")

    _maq = crear_maquetadores(
        _estilos,
        subtitulo=(f"Avance Preliminar de Bitácora · {datos.pdv}" if es_avance
                   else "Reporte de Bitácora de Solicitudes"),
        empresa=datos.empresa, analista=datos.analista, fecha=FECHA_REPORTE,
    )
    encabezado_pie_pagina = _maq["encabezado_pie_pagina"]
    tabla_estilo_mg = _maq["tabla_estilo_mg"]

    # Frases que cambian según el modo.
    periodo = "hasta la fecha de corte" if es_avance else "en el periodo"

    # -------------------------------------------------------------
    # Datos clave ya disponibles en `resumen` (de resumen_general),
    # más algunos cálculos adicionales para la narrativa
    # -------------------------------------------------------------
    total = resumen.get("total", len(df))
    financiados = resumen.get("financiados", 0)
    tiene_categoria = "financiados" in resumen

    n_vendedores = int(tabla_vendedor.shape[0]) if tabla_vendedor is not None else 0

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
    if es_avance:
        elementos.append(Paragraph("AVANCE PRELIMINAR&nbsp;&nbsp;·&nbsp;&nbsp;BITÁCORA DE SOLICITUDES",
                                    estilo_kicker_portada))
        elementos.append(Paragraph("Reporte de Avance Mensual", estilo_titulo_portada))
    else:
        elementos.append(Paragraph("RESUMEN MENSUAL&nbsp;&nbsp;·&nbsp;&nbsp;BITÁCORA DE SOLICITUDES",
                                    estilo_kicker_portada))
        elementos.append(Paragraph("Resumen Mensual", estilo_titulo_portada))
    elementos.append(Paragraph(f"{datos.empresa} · {datos.pdv}", estilo_subtitulo_portada))
    elementos.append(Spacer(1, 0.12 * cm))
    elementos.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor(GRIS_LINEA),
                                 spaceBefore=6, spaceAfter=10, hAlign="LEFT"))

    corte_coherente = False
    if es_avance:
        # ¿La fecha de corte cae en el mismo mes que los datos? Se decide una
        # sola vez y lo respetan la portada, la introducción y los focos.
        # Antes solo los focos lo sabían, y la portada seguía diciendo
        # "quedan 9 días para el cierre de septiembre" sobre datos de julio.
        _mes_datos = _conclusiones.mes_desde_hoja(hoja)
        corte_coherente = not (_mes_datos and _mes_datos != ctx["fecha_corte"].month)

        if corte_coherente:
            elementos.append(Paragraph(
                f"Corte: <b>{FECHA_REPORTE}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"Día {ctx['dia_actual']} de {ctx['dias_en_mes']} de {ctx['nombre_mes']} "
                f"&nbsp;&nbsp;|&nbsp;&nbsp; "
                f"<font color='{MG_ROJO}'><b>{ctx['pct_transcurrido']:.0f}% del mes transcurrido</b></font>",
                estilo_meta_portada
            ))
        else:
            elementos.append(Paragraph(
                f"Corte: <b>{FECHA_REPORTE}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"<font color='{MG_ROJO}'><b>La fecha de corte no corresponde al mes "
                f"de los datos</b></font>",
                estilo_meta_portada
            ))
        elementos.append(Spacer(1, 0.5 * cm))
    else:
        elementos.append(Paragraph(f"Elaborado por <b>{datos.analista}</b> el <b>{FECHA_REPORTE}</b>",
                                   estilo_meta_portada))
        elementos.append(Spacer(1, 0.45 * cm))

    # Las categorías se enumeran a partir de las que REALMENTE trae la
    # bitácora del mes, no de una lista fija de cuatro.
    _presentes = _est.categorias_presentes(df)
    _abiertas_presentes = [c for c in _presentes
                           if _est.GRUPO_CATEGORIA.get(c, _est.ABIERTA) == _est.ABIERTA]
    _texto_clasificadas = (
        f"clasificadas en {len(_presentes)} estatus: "
        f"<b>{_est.frase_enumerada(_presentes)}</b>. "
        if _presentes else ""
    )
    if es_avance:
        _texto_pueden_moverse = (
            f"{'Queda' if ctx['dias_restantes'] == 1 else 'Quedan'} "
            f"{ctx['dias_restantes']} día{'s' if ctx['dias_restantes'] != 1 else ''} "
            f"para el cierre de {ctx['nombre_mes']}, así que las solicitudes en "
            f"<b>{_est.frase_enumerada(_abiertas_presentes, y='y')}</b> "
            f"aún pueden convertirse en FINANCIADAS. "
            if _abiertas_presentes and corte_coherente else ""
        )
        texto_intro = (
            f"Este es un corte <b>PRELIMINAR</b>: resume el comportamiento de las "
            f"{total} solicitudes de crédito automotriz registradas en la bitácora hasta el "
            f"{FECHA_REPORTE}, {_texto_clasificadas}"
            f"{_texto_pueden_moverse}"
            f"Cubre el desempeño por vendedor, la colocación del seguro GAP y los modelos "
            f"de mayor demanda."
        )
    else:
        texto_intro = (
            f"Este reporte resume el comportamiento de las {total} solicitudes de crédito automotriz "
            f"registradas en la bitácora, desde su ingreso hasta su cierre de mes, "
            f"{_texto_clasificadas}"
            f"Incluye el desempeño por vendedor, la colocación "
            f"del seguro GAP y los modelos de vehículo con mayor demanda."
        )
    intro_portada = Table([[Paragraph(texto_intro, estilo_cuerpo)]],
                          colWidths=[_pdf_util.ANCHO_UTIL])
    intro_portada.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    _pdf_util.como_entrada(intro_portada)
    elementos.append(intro_portada)
    elementos.append(Spacer(1, 0.45 * cm))

    # Cifras clave: en el PDF se dibujan como la columna lateral de la
    # portada (pdf_util.construir_con_lateral); en el Word quedan como tabla.
    cifras = (_lateral.cifras_avance(df, ctx=ctx, hoja=hoja) if es_avance
              else _lateral.cifras_resumen(df))
    elementos.append(_lateral.bloque_cifras(cifras))
    elementos.append(Spacer(1, 0.5 * cm))

    # --- Resumen Ejecutivo ---
    elementos.append(Paragraph("Resumen Ejecutivo (a la fecha de corte)" if es_avance
                               else "Resumen Ejecutivo", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    elementos.append(Paragraph("Panorama general", estilo_h2))
    if tiene_categoria:
        # El desglose enumera todas las categorías con solicitudes este mes.
        _desglose = _est.frase_desglose(resumen.get("conteo_categorias", {}), total)
        if es_avance:
            _moviles = _est.frase_enumerada(_abiertas_presentes, y="y", mayusculas=True)
            texto_panorama = (
                f"De las {total} solicitudes registradas hasta el {FECHA_REPORTE}, "
                f"{_desglose}. "
                + (f"Por tratarse de un corte preliminar, las cifras de "
                   f"{_moviles} pueden variar antes del cierre de {ctx['nombre_mes']}."
                   if _moviles else
                   f"Por tratarse de un corte preliminar, las cifras pueden variar "
                   f"antes del cierre de {ctx['nombre_mes']}.")
            )
        else:
            texto_panorama = f"De las {total} solicitudes registradas en el periodo, {_desglose}."
        elementos.append(Paragraph(texto_panorama, estilo_cuerpo))
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
    elif es_avance:
        elementos.append(Paragraph(
            f"Se registraron {total} solicitudes hasta la fecha de corte. No fue posible clasificarlas "
            f"por status porque la columna 'STATUS' no está presente en el archivo fuente.",
            estilo_cuerpo
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
        # El avance resalta en negritas el monto y el ticket; el cierre no.
        if es_avance:
            monto_fin = f"<b> ${resumen['monto_financiado']:,.2f} </b> "
            ticket_fin = (f"<b> ${resumen['ticket_financiado']:,.2f} </b> "
                          if "ticket_financiado" in resumen else "")
        else:
            monto_fin = f" ${resumen['monto_financiado']:,.2f} "
            ticket_fin = (f"${resumen['ticket_financiado']:,.2f} "
                          if "ticket_financiado" in resumen else "")
        partes_financiero.append(
            f"De ese total,{monto_fin}ya corresponden a crédito "
            f"<b>FINANCIADO</b> (dispersado)"
            + (f", con un ticket promedio de {ticket_fin}por crédito"
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
        elementos.append(Paragraph(_pdf_util.resaltar(" ".join(partes_financiero)), estilo_cuerpo))
    else:
        elementos.append(Paragraph(
            "No se encontraron columnas de monto, enganche, plazo o tasa en el archivo fuente para "
            "construir el panorama financiero.", estilo_nota
        ))
    elementos.append(Spacer(1, 0.3 * cm if es_avance else 0.6 * cm))

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
        elementos.append(Paragraph(_pdf_util.resaltar(texto_gap), estilo_cuerpo))
    else:
        elementos.append(Paragraph(
            "No se encontró la columna '¿Tiene GAP?' en el archivo fuente, por lo que no fue posible "
            "analizar la colocación de este seguro.", estilo_nota
        ))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph("Vendedores destacados", estilo_h2))
    if tabla_vendedor is not None and not tabla_vendedor.empty:
        # Antes este párrafo nombraba a los líderes en solicitudes, créditos,
        # monto y GAP: exactamente lo que la tabla de abajo muestra completo.
        # Además decía que alguien "destaca" con un solo GAP.
        texto_vend = (f"Participan {n_vendedores} vendedores. La tabla muestra "
                      f"el detalle de cada uno.")
        elementos.append(Paragraph(_pdf_util.resaltar(texto_vend), estilo_cuerpo))

        # Tabla por vendedor: el panorama completo, incluido el GAP colocado
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
            f"El vehículo más solicitado {periodo} es <b>{modelo_top}</b>, con {modelo_top_val} solicitudes.",
            estilo_cuerpo
        ))
        elementos.append(Spacer(1, 0.2 * cm))

    # --- Focos de atención ---
    # Lo que pide una acción va aquí, arriba, porque es lo primero que alguien
    # con poco tiempo debe leer. En un avance: qué se puede rescatar antes del
    # cierre y a quién hay que seguir (si la fecha de corte no corresponde al
    # mes de los datos, el primer foco lo advierte). Los criterios viven en
    # herramientas/conclusiones.py y no se repiten en las conclusiones finales.
    if es_avance:
        focos, conclusiones = _conclusiones.focos_y_conclusiones_mensual(
            df, "avance", resumen=resumen, ctx=ctx, hoja=hoja)
    else:
        focos, conclusiones = _conclusiones.focos_y_conclusiones_mensual(
            df, "cierre", resumen=resumen)
    if focos:
        elementos.append(Paragraph("Focos de atención", estilo_h2))
        for nota in focos:
            elementos.append(Paragraph(_pdf_util.resaltar("•  " + nota), estilo_cuerpo))
        elementos.append(Spacer(1, 0.2 * cm))

    elementos.append(PageBreak())
    # === FIN RESUMEN EJECUTIVO — continúa el Reporte Detallado abajo ===

    # ===============================================================
    # REPORTE DETALLADO
    # Las secciones 1 a 6 viven en reporte_base.secciones_detalladas().
    # Aquí solo van las tres frases que cambian entre los dos modos.
    secciones_detalladas(
        elementos, _estilos,
        textos={
            "estatus": "La primera gráfica cuenta las solicitudes de cada estatus; la dona muestra "
                       "esos mismos estatus como proporción del total e indica qué vendedores "
                       "aportan a cada uno.",
            "vendedores": f"Se registran {n_vendedores} vendedores con solicitudes "
                          f"{'a la fecha de corte' if es_avance else 'en el periodo'}. "
                          f"La tabla desglosa, para cada uno, cuántas solicitudes generó, en qué estatus "
                          f"{'quedaron' if es_avance else 'cerraron'} y su porcentaje de conversión a "
                          f"crédito financiado.",
            "modelos": "La siguiente gráfica muestra los modelos de vehículo con mayor número "
                       f"de solicitudes {periodo}.",
        },
        df=df, rutas_graficas=rutas_graficas, tabla_vendedor=tabla_vendedor,
        tabla_categoria=tabla_categoria, tabla_estilo_mg=tabla_estilo_mg,
        n_vendedores=n_vendedores, modelo_top=modelo_top,
        modelo_top_val=modelo_top_val,
    )

    # ===============================================================
    elementos.append(Paragraph("Conclusiones y Factores Importantes (a la fecha)" if es_avance
                               else "Conclusiones y Factores Importantes", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    for c in conclusiones:
        elementos.append(Paragraph(_pdf_util.resaltar("•  " + c), estilo_cuerpo))

    # -------------------------------------------------------------
    # Generar el PDF
    # -------------------------------------------------------------
    doc = SimpleDocTemplate(
        nombre_archivo, pagesize=letter,
        topMargin=_pdf_util.MARGEN_SUPERIOR, bottomMargin=_pdf_util.MARGEN_INFERIOR,
        leftMargin=_pdf_util.MARGEN, rightMargin=_pdf_util.MARGEN,
    )
    # Sin esto, un Spacer que no cabe al final de una página genera una
    # hoja en blanco antes del siguiente salto. Ver pdf_util.py.
    elementos[:] = _pdf_util.pulir(_pdf_util.quitar_espacios_antes_de_salto(elementos))
    # `recolectar_elementos`: si el llamador pasa una lista, aquí se le deja
    # una copia de todos los flowables del PDF. Es lo que usa docx_reportes.py
    # para generar el Word a partir de ESTE mismo contenido. Se copia ANTES de
    # doc.build() porque ReportLab va vaciando la lista conforme la maqueta.
    if recolectar_elementos is not None:
        from . import flowables_a_docx as _fd
        recolectar_elementos.extend(_fd.capturar_guion(elementos))

    _pdf_util.construir_con_lateral(doc, elementos, encabezado_pie_pagina)

    print(f"\nReporte PDF generado: {nombre_archivo}")
    print(f"Archivo guardado en: {nombre_archivo}")

    return nombre_archivo
