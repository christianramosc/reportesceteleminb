"""
Reporte PDF de "Validar CSF" — versión visual.

Página 1 (lo esencial en 10 segundos):
  - Veredicto grande con escudo y anillo de candados aprobados.
  - Cifras: candados técnicos, fallas, avisos y vigencia.
  - Barras por sección (cada una lleva al detalle con un clic).
  - Observaciones: solo lo que falló o pide revisión.
  - Datos de la constancia.
  - Validación en el SAT: los QR oficiales regenerados (escaneables desde la
    pantalla) y links clicables. Un QR que NO va al SAT no se dibuja ni se enlaza.
Páginas siguientes: el detalle de los 33 candados, con marcadores (índice
lateral del lector de PDF) por sección.
"""

import html
import io

from reportlab.graphics.shapes import Circle, Drawing, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import iconos as _iconos

# --- Paleta -----------------------------------------------------------------
# Colores de la paleta (decoración: encabezado, títulos, iconos, links).
# Los de ESTADO y VEREDICTO, abajo, tienen significado y no se tocan.
PALETAS = {
    "violeta": {"primario": "#2E1A47", "acento": "#7C5CBF", "suave": "#F1ECF8", "texto_suave": "#CDBFE6",
                "encabezado": "tarjeta"},
    "petroleo": {"primario": "#0F3B44", "acento": "#4C9A9F", "suave": "#EAF3F3", "texto_suave": "#B9D6D8",
                 "encabezado": "lateral"},
    "grafito": {"primario": "#23262D", "acento": "#B83280", "suave": "#F4F1F4", "texto_suave": "#C9CCD3",
                "encabezado": "diagonal"},
}
# Midnight Black, Electric Blue y Cantaloupe Orange. El naranja (2.7:1
# sobre blanco) y el azul eléctrico (3.2:1) no alcanzan para texto sobre
# blanco: van en el encabezado oscuro, iconos y franjas; los links usan un
# azul un poco más oscuro (5:1).
PALETAS["medianoche"] = {"primario": "#02070A", "acento": "#0297DE", "acento2": "#FC734D",
                         "suave": "#EAF6FC", "texto_suave": "#A9B6BF", "enlace": "#0275B0",
                         "encabezado": "banda"}
PALETA = "violeta"
ENCABEZADO = None        # None = el de la paleta; o "banda", "tarjeta", "lateral", "diagonal"


def _p(clave):
    paleta = PALETAS[PALETA]
    if clave == "encabezado" and ENCABEZADO:
        return ENCABEZADO
    if clave == "enlace":
        return paleta.get("enlace", paleta["acento"])
    if clave == "acento2":
        return paleta.get("acento2", paleta["acento"])
    return paleta[clave]


TINTA = "#0F172A"
GRIS = "#64748B"
GRIS_CLARO = "#94A3B8"
LINEA = "#E2E8F0"
FONDO = "#F8FAFC"
# Estados en la familia de la paleta: OK azul, AVISO naranja, FALLA carmín.
# Todos con contraste >= 4.5:1 sobre blanco, y AVISO y FALLA también se
# distinguen por claridad (no solo por tono). VIVO = versión clara para
# fondos oscuros.
ESTADO = {  # estado -> (color fuerte, fondo suave, icono lucide, etiqueta)
    "OK": ("#0275B0", "#E3F3FB", "circle-check", "OK"),
    "AVISO": ("#C2501F", "#FFEDE5", "circle-alert", "AVISO"),
    "FALLA": ("#B3123A", "#FBE3E8", "circle-x", "FALLA"),
    "INFO": ("#5B6876", "#ECEFF2", "info", "INFO"),
}
VIVO = {"#0275B0": "#0297DE", "#C2501F": "#FC734D", "#B3123A": "#FF6B7A", "#3F5466": "#9FB3C8"}
VEREDICTO = {  # veredicto -> (color, fondo, icono, frase)
    "SIN INDICIOS DE ALTERACIÓN": ("#0275B0", "#E3F3FB", "shield-check",
                                   "Pasó los candados técnicos. Valida los QR en el SAT antes de usarla."),
    "REVISAR MANUALMENTE": ("#C2501F", "#FFEDE5", "shield-alert",
                            "Hay avisos con explicación legítima posible. Confírmalos en el QR del SAT."),
    "ALTERADA / NO CONFIABLE": ("#B3123A", "#FBE3E8", "shield-x",
                                "Hay indicios de alteración. No la uses para el expediente."),
    "COPIA: DATOS COINCIDEN": ("#3F5466", "#EDF1F5", "scan-line",
                               "Copia (escaneo o foto): los códigos y los datos legibles coinciden, pero por ser copia NO se puede comprobar que no se alteró antes de escanearse. Valida el QR en el SAT o pide el PDF original."),
    "COPIA: REVISAR A MANO": ("#C2501F", "#FFEDE5", "scan-line",
                              "Copia (escaneo o foto): algo no se alcanzó a leer o quedó dudoso. Revisa los avisos y valida el QR en el SAT, o pide el PDF original."),
    "NO VERIFICABLE": ("#B3123A", "#FBE3E8", "shield-x",
                       "No verificable: no se pudo leer ningún código de la copia. Pide el PDF original del SAT."),
}
SECCIONES = {1: ("Archivo y estructura", "file-search"), 2: ("Códigos QR y de barras", "qr-code"),
             3: ("Coherencia de datos", "fingerprint"), 4: ("Políticas de la financiera", "calendar-check")}

ANCHO = letter[0] - 3.0 * cm      # ancho útil (márgenes de 1.5 cm)
VEREDICTO_ESTILO = "mosaico"      # "solido", "mosaico" o "sello" (propuestas)


def _esc(t):
    return html.escape(str(t if t is not None else ""))


def _ico(nombre, tam, color):
    return _iconos.icono(nombre, tam, color)


def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.8, leading=12, textColor=colors.HexColor(TINTA))
    return {
        "base": base,
        "chico": ParagraphStyle("chico", parent=base, fontSize=7.6, leading=10, textColor=colors.HexColor(GRIS)),
        "etq": ParagraphStyle("etq", parent=base, fontSize=7, leading=9, textColor=colors.HexColor(GRIS)),
        "valor": ParagraphStyle("valor", parent=base, fontName="Helvetica-Bold", fontSize=9.2, leading=12),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                             textColor=colors.HexColor(_p("primario"))),
        "cifra": ParagraphStyle("cifra", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=23),
        "ver": ParagraphStyle("ver", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21),
        "titulo_c": ParagraphStyle("tc", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12),
    }


# ===========================================================================
#  Piezas gráficas
# ===========================================================================
def _anillo(aprobados, total, color, lado=2.6 * cm):
    """Dona de candados aprobados con la cifra al centro."""
    d = Drawing(lado, lado)
    cx = cy = lado / 2
    r = lado / 2 - 2
    grosor = lado * 0.13
    d.add(Wedge(cx, cy, r, 0, 360, radius1=r - grosor, fillColor=colors.HexColor(LINEA), strokeColor=None))
    if total and aprobados:
        fin = 90
        ini = 90 - 360 * aprobados / total
        if aprobados >= total:
            d.add(Wedge(cx, cy, r, 0, 360, radius1=r - grosor, fillColor=colors.HexColor(color), strokeColor=None))
        else:
            d.add(Wedge(cx, cy, r, ini, fin, radius1=r - grosor, fillColor=colors.HexColor(color),
                        strokeColor=None))
    d.add(String(cx, cy + 1, f"{aprobados}/{total}", fontName="Helvetica-Bold", fontSize=lado * 0.17,
                 fillColor=colors.HexColor(TINTA), textAnchor="middle"))
    d.add(String(cx, cy - lado * 0.14, "candados", fontName="Helvetica", fontSize=lado * 0.085,
                 fillColor=colors.HexColor(GRIS), textAnchor="middle"))
    return d


def _barra(conteo, ancho, alto=7):
    """Barra apilada OK / INFO / AVISO / FALLA con extremos redondeados."""
    d = Drawing(ancho, alto)
    total = sum(conteo.values()) or 1
    d.add(Rect(0, 0, ancho, alto, rx=alto / 2, ry=alto / 2, fillColor=colors.HexColor(LINEA), strokeColor=None))
    x = 0
    for est in ("OK", "INFO", "AVISO", "FALLA"):
        n = conteo.get(est, 0)
        if not n:
            continue
        w = ancho * n / total
        color = colors.HexColor(ESTADO[est][0] if est != "INFO" else GRIS_CLARO)
        d.add(Rect(x, 0, w, alto, rx=alto / 2 if (x == 0 or x + w >= ancho - 0.1) else 0,
                   ry=alto / 2, fillColor=color, strokeColor=None))
        x += w
    return d


def _pastilla(estado, est):
    color, fondo, icono, etiqueta = ESTADO[estado]
    t = Table([[_ico(icono, 8, color) or "", Paragraph(f'<font color="{color}"><b>{etiqueta}</b></font>',
                                                       ParagraphStyle("p", parent=est["chico"], fontSize=7))]],
              colWidths=[0.42 * cm, 1.05 * cm], rowHeights=[0.42 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(fondo)),
                           ("ROUNDEDCORNERS", [5, 5, 5, 5]),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _tarjeta(contenido, fondo="#FFFFFF", borde=LINEA, ancho=ANCHO, padding=10, barra=None):
    """Recuadro redondeado; `barra` pinta una franja de color a la izquierda."""
    filas = [[contenido]] if barra is None else [["", contenido]]
    anchos = [ancho] if barra is None else [0.18 * cm, ancho - 0.18 * cm]
    t = Table(filas, colWidths=anchos)
    estilo = [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(fondo)),
              ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(borde)),
              ("ROUNDEDCORNERS", [8, 8, 8, 8]),
              ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), padding), ("RIGHTPADDING", (0, 0), (-1, -1), padding),
              ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding)]
    if barra is not None:
        estilo += [("BACKGROUND", (0, 0), (0, -1), colors.HexColor(barra)),
                   ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 0)]
    t.setStyle(TableStyle(estilo))
    return t


def _titulo(texto, icono, est, ancla=None):
    ic = _ico(icono, 13, _p("acento"))
    p = Paragraph((f'<a name="{ancla}"/>' if ancla else "") + _esc(texto), est["h2"])
    t = Table([[ic or "", p]], colWidths=[0.6 * cm, ANCHO - 0.6 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    t._marcador = (texto, ancla)      # lo usa _Documento para el índice lateral
    return t


def _qr_imagen(url, lado=2.7 * cm):
    """El QR oficial regenerado (nítido para escanear desde la pantalla)."""
    try:
        import numpy as np
        import zxingcpp
        from PIL import Image as PILImage
        img = zxingcpp.create_barcode(url, zxingcpp.BarcodeFormat.QRCode).to_image(scale=8, add_quiet_zones=True)
        pil = PILImage.fromarray(np.asarray(img)).convert("RGB")
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=lado, height=lado)
    except Exception:
        return None


# ===========================================================================
#  Documento: encabezado, pie con "Página X de Y" e índice lateral
# ===========================================================================
class _CanvasNumerado(_canvas.Canvas):
    """Guarda las páginas para poder escribir 'Página X de Y' al final."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor(GRIS))
            self.drawRightString(letter[0] - 1.5 * cm, 0.85 * cm, f"Página {self._pageNumber} de {total}")
            super().showPage()
        super().save()


class _Documento(BaseDocTemplate):
    """Primera página con encabezado alto; las demás con uno delgado (y por
    eso más espacio para el detalle)."""

    def __init__(self, ruta, al_dibujar, **kw):
        super().__init__(ruta, pagesize=letter, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                         topMargin=2.85 * cm, bottomMargin=1.7 * cm, **kw)
        an, al = letter
        alto = lambda arriba: al - arriba - 1.7 * cm  # noqa: E731
        self.addPageTemplates([
            PageTemplate("primera", [Frame(1.5 * cm, 1.7 * cm, an - 3 * cm, alto(2.85 * cm), id="f1")],
                         onPage=al_dibujar),
            PageTemplate("resto", [Frame(1.5 * cm, 1.7 * cm, an - 3 * cm, alto(1.95 * cm), id="f2")],
                         onPage=al_dibujar),
        ])

    def afterFlowable(self, f):
        marcador = getattr(f, "_marcador", None)
        if marcador:
            texto, ancla = marcador
            clave = ancla or f"m{id(f)}"
            self.canv.bookmarkPage(clave)
            self.canv.addOutlineEntry(texto, clave, level=0)


# ===========================================================================
#  Reporte
# ===========================================================================
def _encabezado(cv, an, al, primera, analisis, d, fecha_texto):
    """Encabezado de cada página, según el estilo de la paleta."""
    prim, acento, suave, t_suave = _p("primario"), _p("acento"), _p("suave"), _p("texto_suave")
    estilo = _p("encabezado")
    x0, x1 = 1.5 * cm, an - 1.5 * cm
    folio = f"Folio {analisis.sha256[:10].upper()}"
    rfc = d.get("rfc") or ""
    titulo = "Validación de Constancia de Situación Fiscal"
    C = colors.HexColor

    if estilo == "tarjeta":
        # Tarjeta redondeada dentro de los márgenes, con una barra de acento.
        alto = 2.25 * cm if primera else 1.0 * cm
        y = al - 0.45 * cm - alto
        cv.setFillColor(C(prim))
        cv.roundRect(x0, y, x1 - x0, alto, 0.3 * cm, fill=1, stroke=0)
        cv.setFillColor(C(_p("acento2")))
        cv.roundRect(x0 + 0.45 * cm, y + alto * 0.22, 0.12 * cm, alto * 0.56, 0.06 * cm, fill=1, stroke=0)
        izq = x0 + 0.85 * cm
        claro, tenue = "#FFFFFF", t_suave
    elif estilo == "banda":
        # Banda a todo lo ancho con franja de dos colores abajo.
        alto = 2.3 * cm if primera else 1.35 * cm
        y = al - alto
        cv.setFillColor(C(prim))
        cv.rect(0, y, an, alto, fill=1, stroke=0)
        cv.setFillColor(C(acento))
        cv.rect(0, y - 0.12 * cm, an * 0.72, 0.12 * cm, fill=1, stroke=0)
        cv.setFillColor(C(_p("acento2")))
        cv.rect(an * 0.72, y - 0.12 * cm, an * 0.28, 0.12 * cm, fill=1, stroke=0)
        izq = x0
        claro, tenue = "#FFFFFF", t_suave
    elif estilo == "lateral":
        # Fondo suave con un bloque de color a la izquierda; texto oscuro.
        alto = 2.25 * cm if primera else 1.1 * cm
        y = al - 0.45 * cm - alto
        cv.setFillColor(C(suave))
        cv.rect(x0, y, x1 - x0, alto, fill=1, stroke=0)
        cv.setFillColor(C(prim))
        cv.rect(x0, y, 0.55 * cm, alto, fill=1, stroke=0)
        cv.setFillColor(C(acento))
        cv.rect(x0 + 0.55 * cm, y, x1 - x0 - 0.55 * cm, 0.07 * cm, fill=1, stroke=0)
        izq = x0 + 1.0 * cm
        claro, tenue = prim, GRIS
    else:  # "diagonal"
        # Bloque oscuro con un corte en diagonal y una cuña de acento.
        alto = 2.3 * cm if primera else 1.35 * cm
        y = al - alto
        corte = an * 0.68
        for color, puntos in ((prim, [(0, al), (corte + alto * 0.6, al), (corte, y), (0, y)]),
                              (acento, [(corte + alto * 0.6, al), (corte + alto * 0.6 + 0.35 * cm, al),
                                        (corte + 0.35 * cm, y), (corte, y)]),
                              (_p("acento2"), [(corte + alto * 0.6 + 0.35 * cm, al),
                                               (corte + alto * 0.6 + 0.47 * cm, al),
                                               (corte + 0.47 * cm, y), (corte + 0.35 * cm, y)])):
            trazo = cv.beginPath()
            trazo.moveTo(*puntos[0])
            for punto in puntos[1:]:
                trazo.lineTo(*punto)
            trazo.close()
            cv.setFillColor(C(color))
            cv.drawPath(trazo, fill=1, stroke=0)
        izq = x0
        claro, tenue = "#FFFFFF", t_suave

    if primera:
        cv.setFillColor(C(claro))
        cv.setFont("Helvetica-Bold", 14.5)
        cv.drawString(izq, y + alto - 0.82 * cm, titulo)
        cv.setFont("Helvetica", 8.5)
        cv.setFillColor(C(tenue))
        cv.drawString(izq, y + 0.48 * cm, f"Archivo: {analisis.archivo[:70]}")
        # Derecha: RFC, fecha y folio (en la diagonal van sobre blanco).
        derecha = x1 - (0.5 * cm if estilo in ("tarjeta", "lateral") else 0)
        fuerte = claro if estilo != "diagonal" else prim
        if estilo == "banda":
            fuerte = acento
        suave_der = tenue if estilo != "diagonal" else GRIS
        cv.setFillColor(C(fuerte))
        cv.setFont("Helvetica-Bold", 9.5)
        cv.drawRightString(derecha, y + alto - 0.82 * cm, rfc)
        cv.setFont("Helvetica", 8)
        cv.setFillColor(C(suave_der))
        cv.drawRightString(derecha, y + 0.88 * cm, fecha_texto)
        cv.drawRightString(derecha, y + 0.48 * cm, folio)
    else:
        cv.setFillColor(C(claro))
        cv.setFont("Helvetica-Bold", 9.5)
        cv.drawString(izq, y + alto / 2 - 0.12 * cm, titulo)
        cv.setFont("Helvetica", 8)
        derecha = x1 - (0.5 * cm if estilo in ("tarjeta", "lateral") else 0)
        cv.setFillColor(C(tenue if estilo != "diagonal" else GRIS))
        cv.drawRightString(derecha, y + alto / 2 - 0.12 * cm, rfc or analisis.archivo[:40])


def _mosaico_candados(candados, ancho, est, oscuro=False):
    """Un cuadrito por candado, por sección: se ve de un golpe dónde está
    cada falla o aviso."""
    filas = []
    etiqueta = 2.85 * cm
    mas_largo = max((sum(c.seccion == s for c in candados) for s in SECCIONES), default=1) or 1
    sep = 0.06 * cm
    lado = min(0.3 * cm, (ancho - etiqueta - 2) / mas_largo - sep)   # que quepa la sección más larga
    for sec, (nombre, _icono) in SECCIONES.items():
        lista = [c for c in candados if c.seccion == sec]
        if not lista:
            continue
        d = Drawing(len(lista) * (lado + sep), lado)
        for i, c in enumerate(lista):
            color = ESTADO[c.estado][0]
            if oscuro:
                color = VIVO.get(color, "#8A96A3")
            d.add(Rect(i * (lado + sep), 0, lado, lado, rx=2, ry=2, fillColor=colors.HexColor(color),
                       strokeColor=None))
        etq_color = "#A9B6BF" if oscuro else GRIS
        filas.append([Paragraph(f'<font color="{etq_color}">{_esc(nombre)}</font>',
                                ParagraphStyle("m", parent=est["chico"], fontSize=7, leading=9)), d])
    t = Table(filas, colWidths=[etiqueta, ancho - etiqueta])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    return t


def _veredicto(analisis, ver, c_ver, f_ver, i_ver, frase, aprobados, total, nota_politicas, est):
    """El cuadro del veredicto, en el estilo de VEREDICTO_ESTILO."""
    estilo = VEREDICTO_ESTILO
    aviso = ESTADO["AVISO"][0]

    if estilo == "solido":
        # Bloque de color sólido, texto claro, anillo blanco.
        texto_color = "#FFFFFF"
        sub = "#E6F1F8"
        anillo = Drawing(3.0 * cm, 3.0 * cm)
        lado = 3.0 * cm
        r = lado / 2 - 2
        grosor = lado * 0.12
        anillo.add(Wedge(lado / 2, lado / 2, r, 0, 360, radius1=r - grosor,
                         fillColor=colors.Color(1, 1, 1, alpha=0.28), strokeColor=None))
        if total and aprobados:
            ini = 90 - 360 * aprobados / total if aprobados < total else 0
            fin = 90 if aprobados < total else 360
            anillo.add(Wedge(lado / 2, lado / 2, r, ini, fin, radius1=r - grosor, fillColor=colors.white,
                             strokeColor=None))
        anillo.add(String(lado / 2, lado / 2 + 1, f"{aprobados}/{total}", fontName="Helvetica-Bold",
                          fontSize=lado * 0.17, fillColor=colors.white, textAnchor="middle"))
        anillo.add(String(lado / 2, lado / 2 - lado * 0.14, "candados", fontName="Helvetica",
                          fontSize=lado * 0.085, fillColor=colors.white, textAnchor="middle"))
        texto = [Paragraph(f'<font size="7.5" color="{sub}"><b>VEREDICTO DE AUTENTICIDAD</b></font>', est["base"]),
                 Spacer(1, 3), Paragraph(f'<font color="{texto_color}">{_esc(ver)}</font>', est["ver"]),
                 Spacer(1, 3), Paragraph(f'<font color="{texto_color}">{_esc(frase)}</font>', est["base"])]
        if nota_politicas:
            texto += [Spacer(1, 5), Paragraph(f'<font color="{texto_color}">{nota_politicas}</font>',
                                              est["base"])]
        burbuja = Drawing(1.5 * cm, 1.5 * cm)
        burbuja.add(Circle(0.75 * cm, 0.75 * cm, 0.75 * cm, fillColor=colors.white, strokeColor=None))
        ic = _ico(i_ver, 26, c_ver)
        if ic is not None:
            ic.translate((1.5 * cm - ic.width) / 2, (1.5 * cm - ic.height) / 2)
            burbuja.add(ic)
        interior = Table([[burbuja, texto, anillo]],
                         colWidths=[1.9 * cm, ANCHO - 1.9 * cm - 3.3 * cm - 28, 3.3 * cm])
        interior.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "CENTER"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        return _tarjeta(interior, fondo=c_ver, borde=c_ver, padding=14)

    if estilo == "sello":
        # Tarjeta oscura (Midnight Black) con un sello circular del color del veredicto.
        vivo = VIVO.get(c_ver, c_ver)
        lado = 2.5 * cm
        sello = Drawing(lado, lado)
        sello.add(Circle(lado / 2, lado / 2, lado / 2 - 1, fillColor=None, strokeColor=colors.HexColor(vivo),
                         strokeWidth=2.4))
        sello.add(Circle(lado / 2, lado / 2, lado / 2 - 6, fillColor=None, strokeColor=colors.HexColor(vivo),
                         strokeWidth=0.6, strokeDashArray=[2, 2]))
        ic = _ico(i_ver, 22, vivo)
        if ic is not None:
            ic.translate((lado - ic.width) / 2, lado * 0.42)
            sello.add(ic)
        sello.add(String(lado / 2, lado * 0.24, f"{aprobados}/{total}", fontName="Helvetica-Bold", fontSize=9,
                         fillColor=colors.HexColor(vivo), textAnchor="middle"))
        texto = [Paragraph('<font size="7.5" color="#A9B6BF"><b>VEREDICTO DE AUTENTICIDAD</b></font>', est["base"]),
                 Spacer(1, 3), Paragraph(f'<font color="{vivo}">{_esc(ver)}</font>', est["ver"]),
                 Spacer(1, 3), Paragraph(f'<font color="#E8EDF1">{_esc(frase)}</font>', est["base"])]
        if nota_politicas:
            texto += [Spacer(1, 5), Paragraph(f'<font color="{VIVO[aviso]}">{nota_politicas}</font>', est["base"])]
        ancho_mosaico = 6.6 * cm
        interior = Table([[sello, texto, _mosaico_candados(analisis.candados, ancho_mosaico - 10, est, oscuro=True)]],
                         colWidths=[2.9 * cm, ANCHO - 2.9 * cm - ancho_mosaico - 28, ancho_mosaico])
        interior.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                      ("LEFTPADDING", (2, 0), (2, 0), 10)]))
        return _tarjeta(interior, fondo="#02070A", borde="#02070A", padding=14)

    # "mosaico": tarjeta blanca con encabezado de color y el mosaico de candados.
    cinta = Table([[_ico(i_ver, 15, "#FFFFFF") or "",
                    Paragraph(f'<font color="#FFFFFF"><b>{_esc(ver)}</b></font>',
                              ParagraphStyle("c", parent=est["base"], fontName="Helvetica-Bold", fontSize=13,
                                             leading=16)),
                    Paragraph(f'<font color="#FFFFFF"><b>{aprobados}/{total}</b> candados técnicos OK</font>',
                              ParagraphStyle("c2", parent=est["base"], alignment=2, fontSize=8.5))]],
                  colWidths=[0.75 * cm, ANCHO - 0.75 * cm - 5.2 * cm - 24, 5.2 * cm])
    cinta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    texto = [Paragraph(f'<font size="7.5" color="{GRIS}"><b>QUÉ SIGNIFICA</b></font>', est["base"]), Spacer(1, 3),
             Paragraph(_esc(frase), est["base"])]
    if nota_politicas:
        texto += [Spacer(1, 5), Paragraph(f'<font color="{aviso}">{nota_politicas}</font>', est["base"])]
    ancho_mosaico = 7.4 * cm
    leyenda = Drawing(ancho_mosaico, 9)
    x = 0
    for e in ("OK", "AVISO", "FALLA", "INFO"):
        leyenda.add(Rect(x, 1, 7, 7, rx=1.5, ry=1.5, fillColor=colors.HexColor(ESTADO[e][0]), strokeColor=None))
        leyenda.add(String(x + 10, 1.5, e, fontName="Helvetica", fontSize=6.8, fillColor=colors.HexColor(GRIS)))
        x += 10 + len(e) * 4.3 + 12
    derecha = [Paragraph(f'<font size="7.5" color="{GRIS}"><b>CADA CANDADO</b></font>', est["base"]), Spacer(1, 4),
               _mosaico_candados(analisis.candados, ancho_mosaico, est), Spacer(1, 3),
               leyenda]
    cuerpo = Table([[texto, derecha]], colWidths=[ANCHO - ancho_mosaico - 24 - 14, ancho_mosaico + 14])
    cuerpo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (1, 0), (1, 0), 14),
                                ("LINEBEFORE", (1, 0), (1, 0), 0.6, colors.HexColor(LINEA))]))
    t = Table([[cinta], [cuerpo]], colWidths=[ANCHO])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(c_ver)),
                           ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                           ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(c_ver)),
                           ("ROUNDEDCORNERS", [10, 10, 10, 10]),
                           ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                           ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
                           ("TOPPADDING", (0, 1), (-1, 1), 11), ("BOTTOMPADDING", (0, 1), (-1, 1), 12)]))
    return t


def generar(analisis, ruta_salida, fecha_texto=""):
    est = _estilos()
    d = analisis.datos or {}
    candados = analisis.candados
    ver = analisis.veredicto
    c_ver, f_ver, i_ver, frase = VEREDICTO.get(ver, ("#475569", FONDO, "shield-alert", ""))
    tecnicos = [c for c in candados if c.seccion < 4]
    aprobados = sum(c.estado in ("OK", "INFO") for c in tecnicos)
    n_fallas = sum(c.estado == "FALLA" for c in candados)
    n_avisos = sum(c.estado == "AVISO" for c in candados)
    emision = d.get("fecha_emision")
    hoy = None
    try:
        from . import fechas as _f
        hoy = _f.hoy()
    except Exception:
        from datetime import date
        hoy = date.today()
    dias = (hoy - emision).days if emision else None
    vigente = dias is not None and 0 <= dias <= 30
    el = []

    # --- 1. Veredicto -------------------------------------------------------
    nota_politicas = None
    if ver in ("SIN INDICIOS DE ALTERACIÓN", "COPIA: DATOS COINCIDEN") and not analisis.cumple_politicas:
        nota_politicas = ("<b>Además, no cumple políticas</b> (vigencia o estatus): "
                          "pide al cliente una constancia reciente.")
    el += [_veredicto(analisis, ver, c_ver, f_ver, i_ver, frase, aprobados, len(tecnicos), nota_politicas, est),
           Spacer(1, 10)]

    # --- 2. Cifras ------------------------------------------------------------
    def cifra(etq, valor, color, icono, nota=""):
        ic = _ico(icono, 12, color)
        fila_etq = Table([[ic or "", Paragraph(_esc(etq).upper(), est["etq"])]], colWidths=[0.5 * cm, None])
        fila_etq.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return [fila_etq, Spacer(1, 4), Paragraph(f'<font color="{color}">{_esc(valor)}</font>', est["cifra"]),
                Paragraph(nota, est["chico"])]
    ancho_c = (ANCHO - 3 * 8) / 4
    celdas = [
        cifra("Candados técnicos", f"{aprobados}/{len(tecnicos)}", _p("primario"), "shield-check",
              "archivo, códigos y datos"),
        cifra("Fallas", n_fallas, ESTADO["FALLA"][0] if n_fallas else GRIS_CLARO, "circle-x",
              "indicios de alteración" if n_fallas else "ninguna"),
        cifra("Avisos", n_avisos, ESTADO["AVISO"][0] if n_avisos else GRIS_CLARO, "circle-alert",
              "revisar a mano" if n_avisos else "ninguno"),
        cifra("Emitida hace", f"{dias} días" if dias is not None else "—",
              ESTADO["OK"][0] if vigente else ESTADO["FALLA"][0], "calendar-check",
              (f'<font color="{ESTADO["OK"][0] if vigente else ESTADO["FALLA"][0]}"><b>'
               f'{"Vigente" if vigente else "Vencida"}</b></font> · máximo 30 días') if dias is not None else ""),
    ]
    fila = Table([[_tarjeta(c, ancho=ancho_c, padding=9) for c in celdas]],
                 colWidths=[ancho_c + 8] * 3 + [ancho_c])
    fila.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                              ("RIGHTPADDING", (-1, 0), (-1, 0), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [fila, Spacer(1, 12)]

    # --- 3. Por sección (cada renglón lleva a su detalle) ---------------------
    filas = []
    for sec, (nombre, icono) in SECCIONES.items():
        lista = [c for c in candados if c.seccion == sec]
        if not lista:
            continue
        cuenta = {e: sum(c.estado == e for c in lista) for e in ESTADO}
        ok = cuenta["OK"] + cuenta["INFO"]
        resumen = " · ".join(x for x in (f'<font color="{ESTADO["FALLA"][0]}">{cuenta["FALLA"]} falla(s)</font>'
                                         if cuenta["FALLA"] else "",
                                         f'<font color="{ESTADO["AVISO"][0]}">{cuenta["AVISO"]} aviso(s)</font>'
                                         if cuenta["AVISO"] else "") if x) or \
            f'<font color="{ESTADO["OK"][0]}">todo en orden</font>'
        filas.append([_ico(icono, 12, _p("acento")) or "",
                      Paragraph(f'<a href="#sec{sec}" color="{TINTA}"><b>{_esc(nombre)}</b></a>', est["base"]),
                      _barra(cuenta, 6.3 * cm),
                      Paragraph(f"<b>{ok}/{len(lista)}</b>", ParagraphStyle("r", parent=est["base"],
                                                                         alignment=TA_RIGHT)),
                      Paragraph(resumen, est["chico"])])
    tabla = Table(filas, colWidths=[0.6 * cm, 4.4 * cm, 6.7 * cm, 1.2 * cm, None])
    tabla.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor(LINEA)),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    el += [_titulo("Candados por sección", "badge-check", est), Spacer(1, 2),
           Paragraph("Haz clic en una sección para ir a su detalle.", est["chico"]), Spacer(1, 4),
           _tarjeta(tabla, padding=8), Spacer(1, 12)]

    # --- 4. Observaciones -----------------------------------------------------
    obs = [c for c in candados if c.estado in ("FALLA", "AVISO")]
    obs.sort(key=lambda c: (c.estado != "FALLA", c.seccion))
    bloque = [_titulo("Observaciones", "circle-alert", est), Spacer(1, 6)]
    if obs:
        for c in obs:
            color = ESTADO[c.estado][0]
            contenido = Table([[_pastilla(c.estado, est),
                                [Paragraph(f"<b>{_esc(c.clave)} · {_esc(c.titulo)}</b>", est["base"]),
                                 Paragraph(_esc(c.detalle), est["base"])]]],
                              colWidths=[1.7 * cm, ANCHO - 1.7 * cm - 0.18 * cm - 20])
            contenido.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            bloque += [_tarjeta(contenido, fondo=ESTADO[c.estado][1], borde=ESTADO[c.estado][1],
                                barra=color, padding=7), Spacer(1, 5)]
    else:
        bloque.append(_tarjeta(Paragraph(f'<font color="{ESTADO["OK"][0]}"><b>Sin observaciones:</b> '
                                         'todos los candados pasaron.</font>', est["base"]),
                               fondo=ESTADO["OK"][1], borde=ESTADO["OK"][1], barra=ESTADO["OK"][0], padding=8))
    el += bloque + [Spacer(1, 8)]

    # --- 5. Datos de la constancia -----------------------------------------
    if d:
        moral = d.get("tipo") == "moral"
        regimen = "; ".join(r["regimen"] for r in d.get("regimenes", [])) or "—"
        domicilio = ", ".join(x for x in (d.get("vialidad"), d.get("num_ext"), d.get("colonia"),
                                          f"CP {d.get('cp')}" if d.get("cp") else "",
                                          d.get("municipio"), d.get("entidad")) if x) or "—"
        datos = [
            ("building-2" if moral else "user", "Nombre / razón social", d.get("nombre_completo")),
            ("fingerprint", "RFC", d.get("rfc")),
            ("fingerprint", "CURP", d.get("curp") or ("No aplica" if moral else "—")),
            ("qr-code", "idCIF", d.get("idcif")),
            ("badge-check", "Estatus en el padrón", d.get("estatus")),
            ("calendar-check", "Emisión", d.get("emision_texto")),
            ("calendar-check", "Inicio de operaciones", d.get("inicio_operaciones")),
            ("file-search", "Régimen", regimen),
        ]

        def dato(icono, etq, valor, ancho):
            t = Table([[_ico(icono, 11, GRIS) or "",
                        [Paragraph(_esc(etq).upper(), est["etq"]), Paragraph(_esc(valor or "—"), est["valor"])]]],
                      colWidths=[0.55 * cm, ancho - 0.55 * cm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            return t
        mitad = (ANCHO - 20) / 2
        renglones = [[dato(*datos[i], mitad), dato(*datos[i + 1], mitad) if i + 1 < len(datos) else ""]
                     for i in range(0, len(datos), 2)]
        renglones.append([dato("map-pin", "Domicilio fiscal", domicilio, ANCHO - 20), ""])
        t = Table(renglones, colWidths=[mitad, mitad])
        t.setStyle(TableStyle([("SPAN", (0, len(renglones) - 1), (1, len(renglones) - 1)),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        el += [KeepTogether([_titulo("Datos de la constancia", "user", est), Spacer(1, 6),
                             _tarjeta(t, fondo=FONDO, padding=10)]), Spacer(1, 12)]

    # --- 6. Validación en el SAT --------------------------------------------
    sat = [CondPageBreak(7 * cm), _titulo("Valida en el portal del SAT", "qr-code", est), Spacer(1, 2),
           Paragraph("Escanea cada QR con el celular o haz clic en el link y compara lo que muestra el "
                     "SAT contra el documento.", est["chico"]), Spacer(1, 6)]
    celdas = []
    for i, url in enumerate(analisis.urls_qr[:2], 1):
        oficial = url.startswith("https://siat.sat.gob.mx/")
        que = ("nombre, RFC, CURP, situación, régimen y domicilio" if i == 1 else "fecha y RFC de la cadena original")
        if oficial:
            img = _qr_imagen(url)
            cuerpo = [Paragraph(f"<b>QR {i} · {'cédula' if i == 1 else 'sello'}</b>", est["titulo_c"]),
                      Paragraph(f"Compara: {que}.", est["chico"]), Spacer(1, 4),
                      Paragraph(f'<a href="{_esc(url)}" color="{_p("enlace")}"><u>Abrir en siat.sat.gob.mx</u></a>',
                                est["base"])]
            celda = Table([[img or "", cuerpo]], colWidths=[2.9 * cm, None])
            fondo, borde = "#FFFFFF", LINEA
        else:
            cuerpo = [Paragraph(f'<font color="{ESTADO["FALLA"][0]}"><b>QR {i}: página NO oficial</b></font>',
                                est["titulo_c"]),
                      Paragraph("Lleva a una página que no es del SAT. No la abras ni la uses para validar:", est["chico"]),
                      Paragraph(f'<font color="{ESTADO["FALLA"][0]}">{_esc(url[:90])}</font>', est["chico"])]
            celda = Table([[_ico("shield-x", 30, ESTADO["FALLA"][0]) or "", cuerpo]], colWidths=[1.4 * cm, None])
            fondo, borde = ESTADO["FALLA"][1], ESTADO["FALLA"][1]
        celda.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        celdas.append(_tarjeta(celda, fondo=fondo, borde=borde, ancho=(ANCHO - 10) / 2, padding=8))
    if celdas:
        fila = Table([celdas + ([""] if len(celdas) == 1 else [])], colWidths=[(ANCHO - 10) / 2 + 10, (ANCHO - 10) / 2])
        fila.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        sat += [fila, Spacer(1, 8)]
    el += [KeepTogether(sat)]

    # --- 7. Detalle de candados ----------------------------------------------
    el.append(Spacer(1, 14))
    for sec, (nombre, icono) in SECCIONES.items():
        lista = [c for c in candados if c.seccion == sec]
        if not lista:
            continue
        filas = []
        for c in lista:
            det = _esc(c.detalle)
            if c.previene:
                det += f'<br/><font color="{GRIS_CLARO}" size="7">Previene: {_esc(c.previene)}</font>'
            filas.append([Paragraph(f'<font color="{GRIS}">{_esc(c.clave)}</font>', est["chico"]),
                          Paragraph(f"<b>{_esc(c.titulo)}</b>", est["base"]),
                          _pastilla(c.estado, est), Paragraph(det, est["base"])])
        t = Table(filas, colWidths=[1.05 * cm, 4.45 * cm, 1.75 * cm, None], repeatRows=0)
        estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor(LINEA)),
                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
        for i, c in enumerate(lista):
            if c.estado in ("FALLA", "AVISO"):
                estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(ESTADO[c.estado][1])))
        t.setStyle(TableStyle(estilo))
        el += [CondPageBreak(4 * cm), _titulo(f"{sec}. {nombre}", icono, est, ancla=f"sec{sec}"), Spacer(1, 6),
               t, Spacer(1, 14)]
    el += [Paragraph("Este análisis revisa candados técnicos del archivo y no sustituye la consulta al portal "
                     "del SAT. Huella SHA-256 del archivo revisado:", est["chico"]),
           Paragraph(f'<font name="Courier" size="7">{analisis.sha256}</font>', est["chico"])]

    # --- Encabezado y pie ------------------------------------------------------
    def pagina(cv, doc):
        cv.saveState()
        an, al = letter
        primera = doc.page == 1
        _encabezado(cv, an, al, primera, analisis, d, fecha_texto)
        cv.setStrokeColor(colors.HexColor(LINEA))
        cv.setLineWidth(0.6)
        cv.line(1.5 * cm, 1.25 * cm, an - 1.5 * cm, 1.25 * cm)
        cv.setFont("Helvetica", 7.5)
        cv.setFillColor(colors.HexColor(GRIS))
        cv.drawString(1.5 * cm, 0.85 * cm, f"Validación de CSF · Folio {analisis.sha256[:10].upper()}")
        cv.restoreState()

    doc = _Documento(ruta_salida, pagina, title=f"Validación CSF {d.get('rfc', '')}", subject=ver, creator="Reportes MG Colima")
    doc.build([NextPageTemplate("resto")] + el, canvasmaker=_CanvasNumerado)
    return ruta_salida
