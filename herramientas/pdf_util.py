# -*- coding: utf-8 -*-
"""Utilidades de maquetación compartidas por los cuatro reportes."""

from reportlab.platypus import PageBreak, Spacer


def quitar_espacios_antes_de_salto(elementos):
    """Quita los Spacer que quedan justo antes de un PageBreak.

    Un espacio antes de un salto de página no separa nada: el salto ya lo
    hace. Y cuando la página anterior terminó exactamente llena, ese espacio
    no cabe, ReportLab abre una página nueva solo para él y enseguida el
    PageBreak abre otra. Resultado: una hoja en blanco que depende de cuánto
    texto traiga el mes (así apareció en el Resumen Mensual de julio, con los
    focos de atención llenando la página 2).

    Se compara el tipo exacto y no isinstance: CondPageBreak hereda de
    Spacer y ese sí debe conservarse.
    """
    limpio = []
    for elemento in elementos:
        if isinstance(elemento, PageBreak):
            while limpio and type(limpio[-1]) is Spacer:
                limpio.pop()
        limpio.append(elemento)
    return limpio


import re as _re

try:
    from . import iconos as _iconos
except ImportError:  # ejecución suelta (Colab)
    import iconos as _iconos

from reportlab.lib import colors as _col
from reportlab.lib.pagesizes import letter as _letter
from reportlab.lib.units import cm as _cm

# ===========================================================================
#  Resaltado de cifras y estatus en el texto corrido
# ===========================================================================
_AZUL_DATOS = "#191970"   # azul Inbursa

# Orden de las alternativas: lo más específico primero. Las fechas se
# reconocen para CONSUMIRLAS sin marcarlas (si no, "20/07/2026" quedaría en
# tres pedazos azules). Los números no se marcan si van pegados a letras:
# así no se resalta el "5" de "MG5" ni el "1.5" de "1.5T".
_PAT_DATOS = _re.compile(
    r"(?P<fecha>(?<!\w)\d{1,2}/\d{1,2}/\d{2,4}(?!\w))"
    r"|(?P<monto>\$\d[\d,.]*\d(?=[^\d]|$)|\$\d+)"
    r"|(?P<pct>(?<![\w.,])\d+(?:[.,]\d+)*%)"
    r"|(?P<num>(?<![\w.,/$])\d+(?:[.,]\d+)*(?![\w%/]|[.,]\d))"
    r"|(?P<estatus>\b(?:FINANCIAD(?:A|O|AS|OS)|APROBAD(?:A|O|AS|OS)"
    r"|RECHAZAD(?:A|O|AS|OS)|CONTRAPROPUESTA)\b)"
)
# Un año ("Julio 2026") no es una cifra del negocio: se deja sin marcar.
_PAT_ANIO = _re.compile(r"^(?:19|20)\d{2}$")
_PAT_TAG = _re.compile(r"<[^>]+>")
_MARCA = f'color="{_AZUL_DATOS}"'


def resaltar(texto):
    """Devuelve el texto con montos, porcentajes, números y estatus en azul
    negrita. Respeta las etiquetas que ya trae (<b>, <font>…) y es
    idempotente: un texto ya resaltado se devuelve igual.

    No usar en encabezados ni en celdas de tabla.
    """
    if not texto or _MARCA in texto:
        return texto
    if not _re.search(r"\d|FINANCIAD|APROBAD|RECHAZAD|CONTRAPROPUESTA", texto):
        return texto
    salida, ultimo = [], 0
    for m in _PAT_TAG.finditer(texto):
        if m.start() > ultimo:
            salida.append(_resaltar_fragmento(texto[ultimo:m.start()]))
        salida.append(m.group())
        ultimo = m.end()
    if ultimo < len(texto):
        salida.append(_resaltar_fragmento(texto[ultimo:]))
    return "".join(salida)


def _resaltar_fragmento(texto):
    resultado, ultimo = [], 0
    for m in _PAT_DATOS.finditer(texto):
        if m.start() > ultimo:
            resultado.append(texto[ultimo:m.start()])
        token = m.group()
        if m.lastgroup == "fecha" or (m.lastgroup == "num" and _PAT_ANIO.match(token)):
            resultado.append(token)
        else:
            resultado.append(f'<font {_MARCA}><b>{token}</b></font>')
        ultimo = m.end()
    if ultimo < len(texto):
        resultado.append(texto[ultimo:])
    return "".join(resultado)


# ===========================================================================
#  Formato compartido de los cuatro reportes
# ===========================================================================
# Antes cada reporte tenía su propia copia de márgenes, colores de tabla y
# encabezado/pie, y se desincronizaban. Cambiar el formato de los cuatro es
# cambiar este bloque.

# Márgenes de 2.4 cm: ~16.8 cm de texto, unos 95 caracteres por renglón.
# Con 1.5 cm eran ~115 y los párrafos se leían como bloques.
MARGEN = 2.4 * _cm
MARGEN_SUPERIOR = 2.2 * _cm
MARGEN_INFERIOR = 1.9 * _cm
ANCHO_UTIL = _letter[0] - 2 * MARGEN

# Un solo color de estructura (azul Inbursa). El rojo MG queda para la
# etiqueta de portada y las alertas: así vuelve a significar "atención".
AZUL = "#191970"
LINEA = "#E3E7EE"
FONDO_SUAVE = "#F3F5F9"
GRIS_SEC = "#6B7280"

def repartir(primera, n_resto):
    """Anchos de columna que suman exactamente el ancho útil: la primera
    columna con el ancho dado y el resto repartido en partes iguales.

    Las tablas se calculaban contra 18 cm fijos; al mover el margen quedaban
    saliéndose de la hoja. Con esto dependen del margen, no de un número.
    """
    resto = (ANCHO_UTIL - primera) / max(n_resto, 1)
    return [primera] + [resto] * n_resto


_HUECO_KPI = 0.3 * _cm
ANCHO_KPI = (ANCHO_UTIL - 3 * _HUECO_KPI) / 4
ANCHOS_KPIS = [ANCHO_KPI, _HUECO_KPI, ANCHO_KPI, _HUECO_KPI,
               ANCHO_KPI, _HUECO_KPI, ANCHO_KPI]


def estilo_fila_kpis():
    """Franja de KPI: línea fina arriba, abajo y entre indicadores, en vez
    de cuatro tarjetas con borde y barra de color."""
    linea = _col.HexColor(LINEA)
    return [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, linea),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, linea),
        ("LINEBEFORE", (2, 0), (2, 0), 0.6, linea),
        ("LINEBEFORE", (4, 0), (4, 0), 0.6, linea),
        ("LINEBEFORE", (6, 0), (6, 0), 0.6, linea),
    ]


def estilo_tabla(n_filas, alinear_desde=1, compacta=False, fila_total=False,
                 fuente_regular="Helvetica", fuente_bold="Helvetica-Bold",
                 color_texto="#2B2B2B"):
    """TableStyle de todas las tablas de datos: encabezado gris azulado con
    texto azul, sin zebrado ni recuadro, reglas finas entre renglones. La
    fila de totales conserva su énfasis, en azul en vez de rojo."""
    azul, linea = _col.HexColor(AZUL), _col.HexColor(LINEA)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), _col.HexColor(FONDO_SUAVE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), azul),
        ("FONTNAME", (0, 0), (-1, 0), fuente_bold),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, azul),
        ("FONTNAME", (0, 1), (-1, -1), fuente_regular),
        ("FONTSIZE", (0, 1), (-1, -1), 7.0 if compacta else 8.8),
        ("TEXTCOLOR", (0, 1), (-1, -1), _col.HexColor(color_texto)),
        ("ALIGN", (alinear_desde, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -2 if fila_total else -1), 0.4, linea),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 if compacta else 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 if compacta else 7),
    ]
    if fila_total and n_filas >= 2:
        f = n_filas - 1
        estilo += [
            ("LINEABOVE", (0, f), (-1, f), 1.0, azul),
            ("BACKGROUND", (0, f), (-1, f), _col.HexColor(FONDO_SUAVE)),
            ("FONTNAME", (0, f), (-1, f), fuente_bold),
            ("FONTSIZE", (0, f), (-1, f), 7.4 if compacta else 9.0),
            ("TEXTCOLOR", (0, f), (-1, f), azul),
            ("TOPPADDING", (0, f), (-1, f), 7),
            ("BOTTOMPADDING", (0, f), (-1, f), 7),
        ]
    return estilo


def pintar_encabezado_pie(canvas, doc, empresa, subtitulo, fecha, analista,
                          fuente_regular="Helvetica", fuente_bold="Helvetica-Bold"):
    """Encabezado y pie de los cuatro reportes. Arriba: franja azul, marca y
    nombre del reporte, fecha. Abajo: quién lo elaboró y la página. La marca
    ya no se repite en el pie y se quitaron los cuadritos rojos."""
    canvas.saveState()
    ancho, alto = _letter
    portada = _es_portada(doc)
    if portada:
        # Columna gris de las cifras clave, de arriba abajo.
        canvas.setFillColor(_col.HexColor(COLOR_LATERAL))
        canvas.rect(0, 0, ANCHO_LATERAL, alto, fill=1, stroke=0)
    canvas.setFillColor(_col.HexColor(AZUL))
    canvas.rect(0, alto - 0.12 * _cm, ancho, 0.12 * _cm, fill=1, stroke=0)
    canvas.setFont(fuente_bold, 9.5)
    canvas.drawString(1.2 * _cm if portada else MARGEN, alto - 1.05 * _cm, str(empresa))
    canvas.setFillColor(_col.HexColor(GRIS_SEC))
    if not portada:   # en la portada el título ya dice qué reporte es
        canvas.setFont(fuente_regular, 8)
        canvas.drawString(MARGEN, alto - 1.42 * _cm, str(subtitulo))
    canvas.setFont(fuente_regular, 8.5)
    canvas.drawRightString(ancho - MARGEN, alto - 1.05 * _cm, str(fecha))
    x_pie = _X_PRINCIPAL if portada else MARGEN
    canvas.setStrokeColor(_col.HexColor(LINEA))
    canvas.setLineWidth(0.6)
    canvas.line(x_pie, 1.4 * _cm, ancho - MARGEN, 1.4 * _cm)
    canvas.setFont(fuente_regular, 8)
    if analista:
        canvas.drawString(x_pie, 0.95 * _cm, f"Elaborado por {analista}")
    canvas.drawRightString(ancho - MARGEN, 0.95 * _cm, f"Página {doc.page}")
    canvas.restoreState()


def como_entrada(tabla_intro):
    """El recuadro de introducción de la portada pasa a párrafo de entrada:
    sin fondo ni barra, un punto más grande y en gris oscuro."""
    from reportlab.platypus import Paragraph as _P
    celda = tabla_intro._cellvalues[0][0]
    lista = list(celda) if isinstance(celda, (list, tuple)) else [celda]
    nuevos = [
        _P(p.text, p.style.clone("EntradaPortada", fontSize=11, leading=16.5,
                                 textColor=_col.HexColor("#4B5563")))
        if isinstance(p, _P) else p
        for p in lista
    ]
    tabla_intro._cellvalues[0][0] = nuevos if isinstance(celda, (list, tuple)) else nuevos[0]


_ESTILOS_CUERPO = {"CuerpoMG", "EntradaPortada"}


def pulir(elementos):
    """Última pasada antes de construir el PDF:

    - Resalta cifras y estatus en TODOS los párrafos de cuerpo, no solo en
      los envueltos a mano (así se escapó el "Panorama general").
    - Convierte "•  texto" en viñeta con sangría: el segundo renglón queda
      alineado con el texto, no con el punto.
    Entra en KeepTogether y en las celdas de tabla.
    """
    from reportlab.platypus import Paragraph as _P, Table as _T, KeepTogether as _K

    def _uno(f):
        if isinstance(f, _P) and f.style.name in _ESTILOS_CUERPO:
            texto = resaltar(f.text)
            if texto.lstrip().startswith("•"):
                estilo = f.style.clone("VinetaMG", leftIndent=13, bulletIndent=0,
                                       bulletFontName=f.style.fontName,
                                       bulletFontSize=f.style.fontSize)
                return _P(texto.lstrip()[1:].lstrip(), estilo, bulletText="•")
            return f if texto == f.text else _P(texto, f.style)
        if isinstance(f, _K):
            f._content = [_uno(x) for x in f._content]
        elif isinstance(f, _T):
            for i, fila in enumerate(f._cellvalues):
                for j, celda in enumerate(fila):
                    f._cellvalues[i][j] = ([_uno(x) for x in celda]
                                           if isinstance(celda, (list, tuple)) else _uno(celda))
        return f

    return [_uno(f) for f in elementos]


# ===========================================================================
#  Plantilla: portada con columna lateral de cifras clave y barras de sección
# ===========================================================================
ANCHO_LATERAL = 6.0 * _cm
COLOR_LATERAL = "#F2F3F7"
_X_PRINCIPAL = ANCHO_LATERAL + 0.9 * _cm      # inicio de la columna principal


def _es_portada(doc):
    return getattr(doc, "con_lateral", False) and doc.page == 1


def _flowables_lateral(cifras, alto, ancho=ANCHO_LATERAL - 1.9 * _cm):
    """Las cifras clave, repartidas en todo el alto de la columna."""
    from reportlab.platypus import Paragraph as _P, Spacer as _S
    from reportlab.lib.styles import ParagraphStyle as _PS
    titulo = _PS("LatTit", fontName="Helvetica-Bold", fontSize=8.5,
                 textColor=_col.HexColor("#E4002B"), leading=11)
    etiqueta = _PS("LatEtq", fontName="Helvetica-Bold", fontSize=7, leading=9,
                   textColor=_col.HexColor(GRIS_SEC))
    numero = _PS("LatNum", fontName="Times-Bold", fontSize=30, leading=33,
                 textColor=_col.HexColor(AZUL))
    alerta = numero.clone("LatNumAlerta", textColor=_col.HexColor("#E4002B"))
    nota = _PS("LatNota", fontName="Helvetica", fontSize=8, leading=10.5,
               textColor=_col.HexColor(GRIS_SEC))
    bloques = []
    for c in cifras:
        en_alerta = bool(c.get("alerta"))
        dibujo = _iconos.icono(_iconos.nombre_cifra(c["etiqueta"], en_alerta), 13,
                               "#E4002B" if en_alerta else AZUL)
        if dibujo is not None:
            from reportlab.platypus import Table as _T, TableStyle as _TS
            fila = _T([[dibujo, _P(c["etiqueta"], etiqueta)]],
                      colWidths=[0.62 * _cm, "*"], hAlign="LEFT")
            fila.setStyle(_TS([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            encabezado = fila
        else:
            encabezado = _P(c["etiqueta"], etiqueta)
        bloques.append([encabezado, _P(c["valor"], alerta if en_alerta else numero),
                        _P(c.get("nota", ""), nota)])

    # El espacio entre cifras se calcula MIDIENDO la altura real de cada una.
    # Antes se estimaba (~56 pt por cifra) y quedaba tan justo que, al agregar
    # los iconos, la última cifra se desbordó y empujó la portada entera a la
    # página 2. Se deja además un margen del 10% del alto.
    encabezado_col = [_S(1, 1.6 * _cm), _P("CIFRAS CLAVE", titulo)]
    ocupado = sum(f.wrap(ancho, alto)[1] for f in encabezado_col)
    ocupado += sum(f.wrap(ancho, alto)[1] for b in bloques for f in b)
    libre = alto * 0.90 - ocupado
    hueco = max(10, min(70, libre / max(len(bloques), 1)))
    salida = list(encabezado_col)
    for b in bloques:
        salida += [_S(1, hueco)] + b
    return salida


def _recalcular_al_cambiar_ancho(tabla):
    """Hace que la tabla vuelva a calcular sus anchos si cambia el espacio.

    ReportLab calcula los anchos en la primera medición y activa la bandera
    _width_calculated_once. Si la tabla se intentó colocar al final de la
    portada (columna de 12.3 cm), no cupo y pasó a una página interior
    (16.8 cm), se dibujaba con el ancho de la portada. Así salió la barra
    "02 Panorama financiero" más angosta que el resto.
    """
    original = tabla.wrap
    # Se guarda la especificación ORIGINAL de anchos ("*", porcentajes). Si
    # las celdas llevan párrafos o dibujos, ReportLab calcula por otra vía que
    # sobrescribe _argW con los anchos ya resueltos ([0.85, 11.45] en lugar de
    # [0.85, "*"]); apagar la bandera no bastaba, porque ya no quedaba un "*"
    # que expandir. Así volvieron a salir barras de 12.3 cm con los iconos.
    especificacion = list(tabla._argW)

    def wrap(aw, ah, _o=original, _t=tabla, _esp=especificacion):
        if getattr(_t, "_ancho_previo", None) not in (None, aw):
            _t._argW = list(_esp)
            _t._colWidths = list(_esp)
            _t.__dict__.pop("_width_calculated_once", None)
        _t._ancho_previo = aw
        return _o(aw, ah)
    tabla.wrap = wrap


def barra_seccion(texto, numero):
    """Título de sección como barra azul numerada."""
    from reportlab.platypus import Paragraph as _P, Table as _T, TableStyle as _TS
    from reportlab.lib.styles import ParagraphStyle as _PS
    estilo = _PS("Barra", fontName="Helvetica-Bold", fontSize=10, leading=13,
                 textColor=_col.white)
    titulo = _P(f'<font color="#FF8A9B">{numero:02d}</font>&nbsp;&nbsp;&nbsp;{texto.upper()}', estilo)
    dibujo = _iconos.icono(_iconos.nombre_seccion(texto), 12.5, "#FFFFFF")
    if dibujo is not None:
        # Columna del icono de ancho FIJO y "*" para el texto: con un
        # porcentaje, en la columna angosta de la portada el icono quedaba
        # pegado al número. Y "*" (no None): None ajusta la columna a su
        # contenido y la barra no llenaba la línea.
        t = _T([[dibujo, titulo]], colWidths=[0.85 * _cm, "*"])
        estilo_t = [("LEFTPADDING", (0, 0), (0, 0), 10), ("LEFTPADDING", (1, 0), (1, 0), 2)]
    else:
        t = _T([[titulo]], colWidths=["100%"])
        estilo_t = [("LEFTPADDING", (0, 0), (-1, -1), 10)]
    t.setStyle(_TS([("BACKGROUND", (0, 0), (-1, -1), _col.HexColor(AZUL)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
                   + estilo_t))
    # Nunca al pie de una página sin su contenido.
    t.keepWithNext = True
    _recalcular_al_cambiar_ancho(t)
    return t


def _para_pdf(elementos):
    """Ajustes que solo aplican al PDF (el Word ya se copió antes):

    - Subtítulos (H2MG) -> barras azules numeradas. Se quita la numeración
      que traían escrita ("5. Seguro GAP") para no duplicarla.
    - Anchos de tabla fijos -> porcentajes: en la portada la columna
      principal es más angosta y la tabla debe caber igual.
    - Imágenes: se encogen si no caben en el espacio disponible.
    """
    import re as _r
    from reportlab.platypus import (Paragraph as _P, Table as _T, KeepTogether as _K,
                                    Image as _I, Spacer as _S)
    contador = [0]

    def _tabla(t):
        anchos = getattr(t, "_argW", None)
        if anchos and all(isinstance(w, (int, float)) for w in anchos):
            t._argW = [f"{w / ANCHO_UTIL * 100:.2f}%" for w in anchos]
        _recalcular_al_cambiar_ancho(t)

    def _imagen(img):
        original = img.wrap

        def wrap(aw, ah, _o=original, _i=img):
            if _i.drawWidth > aw:
                f = aw / _i.drawWidth
                _i.drawWidth *= f
                _i.drawHeight *= f
            return _o(aw, ah)
        img.wrap = wrap

    def _uno(f):
        if isinstance(f, _P) and f.style.name == "H2MG":
            contador[0] += 1
            texto = _r.sub(r"^\s*\d+\.\s*", "", f.text)
            return [_S(1, 10), barra_seccion(texto, contador[0])]
        if isinstance(f, _K):
            f._content = [x for y in f._content for x in _lista(_uno(y))]
        elif isinstance(f, _T):
            _tabla(f)
        elif isinstance(f, _I):
            _imagen(f)
        return f

    def _lista(x):
        return x if isinstance(x, list) else [x]

    salida = [x for f in elementos for x in _lista(_uno(f))]
    # Si tras una barra viene un párrafo corto y luego una tabla o gráfica,
    # el párrafo también se amarra: así no queda "04 Vendedores" + una línea
    # al pie de la página con la tabla en la siguiente.
    for i in range(len(salida) - 2):
        if getattr(salida[i], "keepWithNext", False) and isinstance(salida[i + 1], _P) \
                and isinstance(salida[i + 2], (_T, _K, _I)):
            salida[i + 1].keepWithNext = True
    return salida


def construir_con_lateral(doc_simple, elementos, al_dibujar):
    """Construye el PDF con la plantilla: portada con columna lateral de
    cifras clave y páginas interiores a todo lo ancho.

    doc_simple: el SimpleDocTemplate que ya arma cada reporte; se reutilizan
    su archivo, título y autor.
    al_dibujar: la función de encabezado y pie de cada reporte.
    """
    from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame,
                                    FrameBreak, NextPageTemplate)
    ancho, alto = _letter
    cuerpo_y = MARGEN_INFERIOR
    cuerpo_alto = alto - MARGEN_SUPERIOR - MARGEN_INFERIOR

    # Retirar del flujo el bloque de cifras (en el Word se queda como tabla)
    cifras, resto = [], []
    for f in elementos:
        if getattr(f, "_cifras_clave", None) is not None and not cifras:
            cifras = f._cifras_clave
        else:
            resto.append(f)

    lateral = Frame(1.2 * _cm, cuerpo_y, ANCHO_LATERAL - 1.9 * _cm, cuerpo_alto, id="lateral",
                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    principal = Frame(_X_PRINCIPAL, cuerpo_y, ancho - _X_PRINCIPAL - MARGEN, cuerpo_alto,
                      id="principal", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    interior = Frame(MARGEN, cuerpo_y, ancho - 2 * MARGEN, cuerpo_alto, id="interior",
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(doc_simple.filename, pagesize=_letter,
                          title=getattr(doc_simple, "title", None) or "",
                          author=getattr(doc_simple, "author", None) or "")
    doc.con_lateral = True
    doc.addPageTemplates([
        PageTemplate("portada", [lateral, principal], onPage=al_dibujar),
        PageTemplate("interior", [interior], onPage=al_dibujar),
    ])
    # KeepInFrame(mode="shrink"): si la columna no cabe (muchas cifras, notas
    # largas), se encoge en lugar de desbordarse hacia la columna principal.
    # Un desborde ahí empuja TODA la portada a la página 2.
    from reportlab.platypus import KeepInFrame
    ancho_lat = ANCHO_LATERAL - 1.9 * _cm
    historia = ([KeepInFrame(ancho_lat, cuerpo_alto,
                             _flowables_lateral(cifras, cuerpo_alto, ancho_lat), mode="shrink"),
                 FrameBreak()]
                if cifras else [FrameBreak()])
    historia += [NextPageTemplate("interior")] + _para_pdf(resto)
    doc.build(historia)
    return doc
