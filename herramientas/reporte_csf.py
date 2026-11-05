"""
Reporte PDF de "Validar CSF" — versión visual.

Pensado para entenderse de un vistazo, con color y ayudas visuales, sin
perder el detalle:

Página 1
  - Portada con el veredicto grande, el anillo de candados aprobados y un
    semáforo por sección.
  - Cuatro cifras: candados técnicos, fallas, avisos y vigencia.
  - Línea de tiempo de la vigencia: emisión -> hoy, contra la ventana de
    30 días.
  - Tarjetas por sección con su barra OK / AVISO / FALLA (cada una lleva
    a su detalle con un clic).
  - Observaciones: solo lo que falló o pide revisión.
Después
  - Datos de la constancia.
  - Cómo validar en el SAT: tres pasos y los QR oficiales regenerados
    (escaneables desde la pantalla). Un QR que NO va al SAT no se dibuja.
  - Detalle de los 33 candados por sección, con marcadores en el índice
    lateral del lector de PDF.

Los colores de estado (verde OK, ámbar AVISO, rojo FALLA, gris INFO) y los
del veredicto tienen significado: no se cambian por estética. El resto
(azul marino y rojo de la marca, fondos suaves) es decoración.

No lleva casillas, firmas ni datos de quién revisa.
"""

import html
import io

from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import iconos as _iconos

# --- Paleta -----------------------------------------------------------------
# Marca y decoración
NAVY = "#191970"          # azul Inbursa
NAVY_MEDIO = "#3B3FA6"
NAVY_SUAVE = "#EEF0FB"
LAVANDA = "#C9CCF2"       # texto suave sobre el azul
ROJO_MG = "#C8102E"
TINTA = "#14172B"
GRIS = "#5B6072"
GRIS_CLARO = "#9AA0B4"
LINEA = "#E3E5EE"
FONDO = "#F7F8FC"
# Con significado: NO se cambian por estética.
ESTADO = {  # estado -> (color fuerte, fondo suave, icono, etiqueta)
    "OK": ("#15803D", "#DCFCE7", "circle-check", "OK"),
    "AVISO": ("#B45309", "#FEF3C7", "circle-alert", "AVISO"),
    "FALLA": ("#B91C1C", "#FEE2E2", "circle-x", "FALLA"),
    "INFO": ("#475569", "#E2E8F0", "info", "INFO"),
}
VEREDICTO = {  # veredicto -> (color, fondo, icono, frase)
    "SIN INDICIOS DE ALTERACIÓN": ("#15803D", "#ECFDF3", "shield-check",
                                   "Pasó los candados técnicos. Valida los QR en el SAT antes de usarla."),
    "REVISAR MANUALMENTE": ("#B45309", "#FFF8EB", "shield-alert",
                            "Hay avisos con explicación legítima posible. Confírmalos en el QR del SAT."),
    "ALTERADA / NO CONFIABLE": ("#B91C1C", "#FEF2F2", "shield-x",
                                "Hay indicios de alteración. No la uses para el expediente."),
    "COPIA: DATOS COINCIDEN": ("#1D4ED8", "#EFF6FF", "scan-line",
                               "Copia (escaneo o foto): los códigos y los datos legibles coinciden, pero por ser copia NO se puede comprobar que no se alteró antes de escanearse. Valida el QR en el SAT o pide el PDF original."),
    "COPIA: REVISAR A MANO": ("#B45309", "#FFF8EB", "scan-line",
                              "Copia (escaneo o foto): algo no se alcanzó a leer o quedó dudoso. Revisa los avisos y valida el QR en el SAT, o pide el PDF original."),
    "NO VERIFICABLE": ("#B91C1C", "#FEF2F2", "shield-x",
                       "No verificable: no se pudo leer ningún código de la copia. Pide el PDF original del SAT."),
}
SECCIONES = {1: ("Archivo y estructura", "file-search", "¿El PDF salió tal cual del SAT?"),
             2: ("Códigos QR y de barras", "qr-code", "¿Los códigos llevan al SAT y dicen lo mismo?"),
             3: ("Coherencia de datos", "fingerprint", "¿RFC, CURP, fechas y régimen cuadran?"),
             4: ("Políticas de la financiera", "calendar-check", "¿Está vigente y ACTIVA?")}
CORTO = {1: "Archivo", 2: "Códigos", 3: "Datos", 4: "Políticas"}   # para el semáforo
DIAS_VIGENCIA = 30
LEYENDA = (("OK", "se cumple"), ("AVISO", "revisar a mano"), ("FALLA", "indicio de alteración"),
           ("INFO", "dato informativo"))

MARGEN = 1.5 * cm
ANCHO = letter[0] - 2 * MARGEN      # ancho útil


def _esc(t):
    return html.escape(str(t if t is not None else ""))


def _ico(nombre, tam, color):
    return _iconos.icono(nombre, tam, color)


def _hex(c):
    return colors.HexColor(c)


def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.8, leading=12, textColor=_hex(TINTA))
    return {
        "base": base,
        "chico": ParagraphStyle("chico", parent=base, fontSize=7.5, leading=10, textColor=_hex(GRIS)),
        "etq": ParagraphStyle("etq", parent=base, fontName="Helvetica-Bold", fontSize=6.6, leading=8.5,
                              textColor=_hex(GRIS)),
        "valor": ParagraphStyle("valor", parent=base, fontName="Helvetica-Bold", fontSize=9, leading=11.5),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=15,
                             textColor=_hex(NAVY)),
        "h2_sub": ParagraphStyle("h2_sub", parent=base, fontSize=7.8, leading=10, textColor=_hex(GRIS)),
        "ver": ParagraphStyle("ver", parent=base, fontName="Helvetica-Bold", fontSize=19, leading=22),
        "cifra": ParagraphStyle("cifra", parent=base, fontName="Helvetica-Bold", fontSize=21, leading=24),
        "sec_nombre": ParagraphStyle("sec_nombre", parent=base, fontName="Helvetica-Bold", fontSize=9.5,
                                     leading=12),
        "der": ParagraphStyle("der", parent=base, alignment=TA_RIGHT),
        "centro": ParagraphStyle("centro", parent=base, alignment=TA_CENTER),
    }


def _sin_relleno(extra=()):
    return TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), *extra])


def _tarjeta(contenido, fondo="#FFFFFF", borde=LINEA, ancho=ANCHO, padding=10, barra=None, radio=9):
    """Recuadro redondeado; `barra` pinta una franja de color a la izquierda."""
    filas = [[contenido]] if barra is None else [["", contenido]]
    anchos = [ancho] if barra is None else [0.2 * cm, ancho - 0.2 * cm]
    t = Table(filas, colWidths=anchos)
    estilo = [("BACKGROUND", (0, 0), (-1, -1), _hex(fondo)),
              ("BOX", (0, 0), (-1, -1), 0.7, _hex(borde)),
              ("ROUNDEDCORNERS", [radio] * 4),
              ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), padding), ("RIGHTPADDING", (0, 0), (-1, -1), padding),
              ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding)]
    if barra is not None:
        estilo += [("BACKGROUND", (0, 0), (0, -1), _hex(barra)),
                   ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 0)]
    t.setStyle(TableStyle(estilo))
    return t


def _burbuja(icono, color, fondo, lado=0.95 * cm, tam=None):
    """Icono dentro de un círculo de color suave."""
    d = Drawing(lado, lado)
    d.add(Circle(lado / 2, lado / 2, lado / 2, fillColor=_hex(fondo), strokeColor=None))
    ic = _ico(icono, tam or lado * 0.55, color)
    if ic is not None:
        ic.translate((lado - ic.width) / 2, (lado - ic.height) / 2)
        d.add(ic)
    return d


def _numero(n, color, lado=16):
    """Número blanco dentro de un círculo de color."""
    d = Drawing(lado, lado)
    d.add(Circle(lado / 2, lado / 2, lado / 2, fillColor=_hex(color), strokeColor=None))
    d.add(String(lado / 2, lado / 2 - 3, str(n), fontName="Helvetica-Bold", fontSize=lado * 0.5,
                 fillColor=colors.white, textAnchor="middle"))
    return d


def _pastilla(estado, est, ancho=1.6 * cm):
    """OK / AVISO / FALLA / INFO como chip de color con icono."""
    color, fondo, icono, etiqueta = ESTADO[estado]
    t = Table([[_ico(icono, 8, color) or "",
                Paragraph(f'<font color="{color}"><b>{etiqueta}</b></font>',
                          ParagraphStyle("p", parent=est["chico"], fontSize=7, leading=8.5))]],
              colWidths=[0.42 * cm, ancho - 0.42 * cm], rowHeights=[0.44 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _hex(fondo)), ("ROUNDEDCORNERS", [6] * 4),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _anillo(aprobados, total, color, lado=3.0 * cm):
    """Dona de candados aprobados con la cifra al centro, sobre un disco blanco."""
    d = Drawing(lado, lado)
    cx = cy = lado / 2
    r = lado / 2 - 2
    grosor = lado * 0.12
    d.add(Circle(cx, cy, r + 1, fillColor=_hex("#FFFFFF"), strokeColor=None))
    d.add(Wedge(cx, cy, r, 0, 360, radius1=r - grosor, fillColor=_hex(LINEA), strokeColor=None))
    if total and aprobados:
        if aprobados >= total:
            d.add(Wedge(cx, cy, r, 0, 360, radius1=r - grosor, fillColor=_hex(color), strokeColor=None))
        else:
            d.add(Wedge(cx, cy, r, 90 - 360 * aprobados / total, 90, radius1=r - grosor,
                        fillColor=_hex(color), strokeColor=None))
    d.add(String(cx, cy + 2, f"{aprobados}/{total}", fontName="Helvetica-Bold", fontSize=lado * 0.18,
                 fillColor=_hex(TINTA), textAnchor="middle"))
    d.add(String(cx, cy - lado * 0.13, "candados OK", fontName="Helvetica", fontSize=lado * 0.075,
                 fillColor=_hex(GRIS), textAnchor="middle"))
    return d


def _barra(conteo, ancho, alto=8):
    """Barra apilada OK / INFO / AVISO / FALLA con extremos redondeados."""
    d = Drawing(ancho, alto)
    total = sum(conteo.values()) or 1
    d.add(Rect(0, 0, ancho, alto, rx=alto / 2, ry=alto / 2, fillColor=_hex(LINEA), strokeColor=None))
    x = 0
    for e in ("OK", "INFO", "AVISO", "FALLA"):
        n = conteo.get(e, 0)
        if not n:
            continue
        w = ancho * n / total
        color = _hex(ESTADO[e][0] if e != "INFO" else GRIS_CLARO)
        d.add(Rect(x, 0, w, alto, rx=alto / 2 if (x == 0 or x + w >= ancho - 0.1) else 0,
                   ry=alto / 2, fillColor=color, strokeColor=None))
        x += w
    return d


def _linea_vigencia(dias, emision_txt, hoy_txt, ancho):
    """Línea de tiempo: la ventana de 30 días en verde, lo que pasa de ahí en
    rojo, y un marcador donde cae la constancia."""
    alto = 1.55 * cm
    d = Drawing(ancho, alto)
    escala_max = max(DIAS_VIGENCIA * 2, (dias or 0) + 10)
    x0, x1 = 6, ancho - 6
    y = alto * 0.48

    def x(dia):
        return x0 + (x1 - x0) * min(max(dia, 0), escala_max) / escala_max
    verde, rojo = ESTADO["OK"], ESTADO["FALLA"]
    corte = x(DIAS_VIGENCIA)
    d.add(Rect(x0, y - 4, corte - x0, 8, rx=4, ry=4, fillColor=_hex(verde[1]), strokeColor=None))
    d.add(Rect(corte, y - 4, x1 - corte, 8, rx=4, ry=4, fillColor=_hex(rojo[1]), strokeColor=None))
    d.add(Line(corte, y - 9, corte, y + 9, strokeColor=_hex(GRIS_CLARO), strokeWidth=0.8, strokeDashArray=[2, 2]))
    d.add(String((x0 + corte) / 2, y + 9, f"Vigente (0 a {DIAS_VIGENCIA} días)", fontName="Helvetica-Bold",
                 fontSize=7, fillColor=_hex(verde[0]), textAnchor="middle"))
    d.add(String((corte + x1) / 2, y + 9, "Vencida: pide una CSF reciente", fontName="Helvetica-Bold",
                 fontSize=7, fillColor=_hex(rojo[0]), textAnchor="middle"))
    d.add(String(x0, y - 16, f"Emisión · {emision_txt}", fontName="Helvetica", fontSize=7,
                 fillColor=_hex(GRIS), textAnchor="start"))
    if dias is not None and dias >= 0:
        color = verde[0] if dias <= DIAS_VIGENCIA else rojo[0]
        xm = x(dias)
        d.add(Circle(xm, y, 6.5, fillColor=_hex("#FFFFFF"), strokeColor=_hex(color), strokeWidth=2.2))
        d.add(Circle(xm, y, 2.6, fillColor=_hex(color), strokeColor=None))
        anclar = "end" if xm > ancho * 0.7 else ("start" if xm < ancho * 0.3 else "middle")
        d.add(String(xm, y - 16, f"Hoy · {hoy_txt} · {dias} días", fontName="Helvetica-Bold", fontSize=7,
                     fillColor=_hex(color), textAnchor=anclar))
    return d


def _titulo(texto, icono, est, sub=None, ancla=None):
    """Título de bloque: icono en burbuja azul + texto + subtítulo opcional."""
    p = [Paragraph((f'<a name="{ancla}"/>' if ancla else "") + _esc(texto), est["h2"])]
    if sub:
        p.append(Paragraph(_esc(sub), est["h2_sub"]))
    t = Table([[_burbuja(icono, NAVY, NAVY_SUAVE, 0.82 * cm), p]], colWidths=[1.05 * cm, ANCHO - 1.05 * cm])
    t.setStyle(_sin_relleno())
    t._marcador = (texto, ancla)      # índice lateral del lector de PDF
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
#  Documento: portada, pie con "Página X de Y" e índice lateral
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
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(_hex(NAVY))
            self.drawRightString(letter[0] - MARGEN, 0.75 * cm, f"Página {self._pageNumber} de {total}")
            super().showPage()
        super().save()


class _Documento(BaseDocTemplate):
    """Primera página con portada alta; las demás con banda delgada."""

    def __init__(self, ruta, al_dibujar, **kw):
        super().__init__(ruta, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN,
                         topMargin=3.6 * cm, bottomMargin=1.6 * cm, **kw)
        an, al = letter
        alto = lambda arriba: al - arriba - 1.6 * cm  # noqa: E731
        self.addPageTemplates([
            PageTemplate("primera", [Frame(MARGEN, 1.6 * cm, an - 2 * MARGEN, alto(3.6 * cm), id="f1")],
                         onPage=al_dibujar),
            PageTemplate("resto", [Frame(MARGEN, 1.6 * cm, an - 2 * MARGEN, alto(2.0 * cm), id="f2")],
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
def generar(analisis, ruta_salida, fecha_texto=""):
    est = _estilos()
    d = analisis.datos or {}
    candados = analisis.candados
    ver = analisis.veredicto
    c_ver, f_ver, i_ver, frase = VEREDICTO.get(ver, (ESTADO["INFO"][0], FONDO, "shield-alert", ""))
    tecnicos = [c for c in candados if c.seccion < 4]
    aprobados = sum(c.estado in ("OK", "INFO") for c in tecnicos)
    n_fallas = sum(c.estado == "FALLA" for c in candados)
    n_avisos = sum(c.estado == "AVISO" for c in candados)
    emision = d.get("fecha_emision")
    try:
        from . import fechas as _f
        hoy = _f.hoy()
    except Exception:
        from datetime import date
        hoy = date.today()
    dias = (hoy - emision).days if emision else None
    vigente = dias is not None and 0 <= dias <= DIAS_VIGENCIA
    folio = analisis.sha256[:10].upper()

    def cuenta_de(sec):
        lista = [c for c in candados if c.seccion == sec]
        return lista, {e: sum(c.estado == e for c in lista) for e in ESTADO}

    def estado_seccion(cuenta):
        if cuenta["FALLA"]:
            return "FALLA", "Con fallas"
        if cuenta["AVISO"]:
            return "AVISO", "Con avisos"
        return "OK", "En orden"

    el = []

    # --- 1. Veredicto -------------------------------------------------------
    sello = _burbuja(i_ver, c_ver, "#FFFFFF", 1.7 * cm, 30)
    texto = [Paragraph(f'<font color="{c_ver}"><b>VEREDICTO DE AUTENTICIDAD</b></font>', est["etq"]),
             Spacer(1, 3), Paragraph(f'<font color="{c_ver}">{_esc(ver)}</font>', est["ver"]),
             Spacer(1, 3), Paragraph(_esc(frase), est["base"])]
    if ver in ("SIN INDICIOS DE ALTERACIÓN", "COPIA: DATOS COINCIDEN") and not analisis.cumple_politicas:
        texto += [Spacer(1, 4), Paragraph(
            f'<font color="{ESTADO["AVISO"][0]}"><b>Además, no cumple políticas</b> (vigencia o estatus): '
            'pide al cliente una constancia reciente.</font>', est["base"])]
    # Semáforo: una luz por sección, con el color de su peor resultado.
    luces = []
    for sec in SECCIONES:
        lista, cuenta = cuenta_de(sec)
        if not lista:
            continue
        e, _txt = estado_seccion(cuenta)
        luz = Drawing(10, 10)
        luz.add(Circle(5, 5, 5, fillColor=_hex(ESTADO[e][0]), strokeColor=None))
        luces += [luz, Paragraph(f'<b>{CORTO[sec]}</b>', est["chico"])]
    ancho_texto = ANCHO - 2.2 * cm - 3.4 * cm - 28
    if luces:
        n = len(luces) // 2
        semaforo = Table([luces], colWidths=[0.42 * cm, ancho_texto / n - 0.42 * cm] * n)
        semaforo.setStyle(_sin_relleno([("RIGHTPADDING", (1, 0), (-1, -1), 4)]))
        texto += [Spacer(1, 8), semaforo]
    hero = Table([[sello, texto, _anillo(aprobados, len(tecnicos), c_ver)]],
                 colWidths=[2.2 * cm, ancho_texto, 3.4 * cm])
    hero.setStyle(_sin_relleno([("ALIGN", (2, 0), (2, 0), "CENTER")]))
    el += [_tarjeta(hero, fondo=f_ver, borde=c_ver, barra=c_ver, padding=13, radio=12), Spacer(1, 10)]

    # --- 2. Cifras ------------------------------------------------------------
    def cifra(etq, valor, color, fondo, icono, nota):
        cab = Table([[_ico(icono, 11, color) or "", Paragraph(_esc(etq).upper(), est["etq"])]],
                    colWidths=[0.48 * cm, None])
        cab.setStyle(_sin_relleno())
        return [cab, Spacer(1, 3), Paragraph(f'<font color="{color}">{_esc(valor)}</font>', est["cifra"]),
                Paragraph(nota, est["chico"])], fondo
    ancho_c = (ANCHO - 3 * 8) / 4
    vig = ESTADO["OK"] if vigente else ESTADO["FALLA"]
    datos_cifras = [
        cifra("Candados técnicos", f"{aprobados}/{len(tecnicos)}", NAVY, NAVY_SUAVE, "shield-check",
              "archivo, códigos y datos"),
        cifra("Fallas", n_fallas, ESTADO["FALLA"][0] if n_fallas else GRIS_CLARO,
              ESTADO["FALLA"][1] if n_fallas else FONDO, "circle-x",
              "indicios de alteración" if n_fallas else "ninguna"),
        cifra("Avisos", n_avisos, ESTADO["AVISO"][0] if n_avisos else GRIS_CLARO,
              ESTADO["AVISO"][1] if n_avisos else FONDO, "circle-alert",
              "revisar a mano" if n_avisos else "ninguno"),
        cifra("Emitida hace", f"{dias} días" if dias is not None else "—",
              vig[0] if dias is not None else GRIS_CLARO, vig[1] if dias is not None else FONDO, "calendar-check",
              (f'<font color="{vig[0]}"><b>{"Vigente" if vigente else "Vencida"}</b></font> · máximo '
               f'{DIAS_VIGENCIA} días') if dias is not None else "sin fecha legible"),
    ]
    fila = Table([[_tarjeta(c, fondo=f, borde=f, ancho=ancho_c, padding=9) for c, f in datos_cifras]],
                 colWidths=[ancho_c + 8] * 3 + [ancho_c])
    fila.setStyle(_sin_relleno([("RIGHTPADDING", (0, 0), (-2, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [fila, Spacer(1, 10)]

    # --- 3. Línea de tiempo de la vigencia -----------------------------------
    if dias is not None:
        linea = _linea_vigencia(dias, f"{emision:%d/%m/%Y}", f"{hoy:%d/%m/%Y}", ANCHO - 24)
        el += [_tarjeta([Paragraph(f"<b>¿Sigue vigente?</b> La financiera pide una constancia de máximo "
                                   f"{DIAS_VIGENCIA} días.", est["chico"]), Spacer(1, 4), linea],
                        padding=12), Spacer(1, 14)]

    # --- 4. Tarjetas por sección ---------------------------------------------
    el += [_titulo("Candados por sección", "layers", est, "Haz clic en una tarjeta para ir a su detalle."),
           Spacer(1, 7)]
    tarjetas = []
    ancho_t = (ANCHO - 10) / 2
    interior = ancho_t - 24
    for sec, (nombre, icono, pregunta) in SECCIONES.items():
        lista, cuenta = cuenta_de(sec)
        if not lista:
            continue
        e, txt = estado_seccion(cuenta)
        ok = cuenta["OK"] + cuenta["INFO"]
        cab = Table([[_burbuja(icono, NAVY, NAVY_SUAVE, 0.8 * cm),
                      [Paragraph(f'<a href="#sec{sec}" color="{TINTA}">{sec}. {_esc(nombre)}</a>',
                                 est["sec_nombre"]),
                       Paragraph(_esc(pregunta), est["chico"])],
                      Paragraph(f"<b>{ok}</b><font size='8' color='{GRIS}'>/{len(lista)}</font>",
                                ParagraphStyle("n", parent=est["der"], fontName="Helvetica-Bold", fontSize=15,
                                               leading=17))]],
                    colWidths=[1.0 * cm, interior - 1.0 * cm - 1.4 * cm, 1.4 * cm])
        cab.setStyle(_sin_relleno())
        pie = Table([[_barra(cuenta, interior - 2.25 * cm), _pastilla(e, est, 1.95 * cm)]],
                    colWidths=[interior - 2.05 * cm, 2.05 * cm])
        pie.setStyle(_sin_relleno([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
        detalle = txt + "".join(
            f' · <font color="{ESTADO[k][0]}">{cuenta[k]} {etq}</font>'
            for k, etq in (("FALLA", "falla(s)"), ("AVISO", "aviso(s)")) if cuenta[k])
        tarjetas.append(_tarjeta([cab, Spacer(1, 8), pie, Spacer(1, 3), Paragraph(detalle, est["chico"])],
                                 ancho=ancho_t, padding=12))
    rejilla = [tarjetas[i:i + 2] + ([""] if len(tarjetas[i:i + 2]) == 1 else [])
               for i in range(0, len(tarjetas), 2)]
    if rejilla:
        t = Table(rejilla, colWidths=[ancho_t + 10, ancho_t])
        t.setStyle(_sin_relleno([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        el.append(t)
    el.append(Spacer(1, 8))

    # --- 5. Observaciones -----------------------------------------------------
    obs = [c for c in candados if c.estado in ("FALLA", "AVISO")]
    obs.sort(key=lambda c: (c.estado != "FALLA", c.seccion))
    bloque = [_titulo("Observaciones", "triangle-alert", est,
                      f"{len(obs)} punto(s) a revisar, primero las fallas." if obs else None), Spacer(1, 7)]
    if obs:
        for i, c in enumerate(obs, 1):
            color, fondo, _icono, _e = ESTADO[c.estado]
            contenido = Table([[_numero(i, color),
                                [Paragraph(f"<b>{_esc(c.titulo)}</b> "
                                           f'<font color="{GRIS}" size="7.5">· candado {_esc(c.clave)}</font>',
                                           est["base"]),
                                 Paragraph(_esc(c.detalle), est["base"])],
                                _pastilla(c.estado, est)]],
                              colWidths=[0.7 * cm, ANCHO - 0.2 * cm - 18 - 0.7 * cm - 1.75 * cm, 1.75 * cm])
            contenido.setStyle(_sin_relleno([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            bloque += [_tarjeta(contenido, fondo=fondo, borde=fondo, barra=color, padding=9), Spacer(1, 5)]
    else:
        bloque.append(_tarjeta(Paragraph(f'<font color="{ESTADO["OK"][0]}"><b>Sin observaciones:</b> '
                                         'todos los candados pasaron.</font>', est["base"]),
                               fondo=ESTADO["OK"][1], borde=ESTADO["OK"][1], barra=ESTADO["OK"][0], padding=9))
    el += bloque + [Spacer(1, 12)]

    # --- 6. Datos de la constancia -----------------------------------------
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
            ("calendar-days", "Inicio de operaciones", d.get("inicio_operaciones")),
            ("file-text", "Régimen", regimen),
        ]

        def dato(icono, etq, valor, ancho):
            t = Table([[_ico(icono, 11, NAVY_MEDIO) or "",
                        [Paragraph(_esc(etq).upper(), est["etq"]), Paragraph(_esc(valor or "—"), est["valor"])]]],
                      colWidths=[0.6 * cm, ancho - 0.6 * cm])
            t.setStyle(_sin_relleno([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
            return t
        mitad = (ANCHO - 24) / 2
        renglones = [[dato(*datos[i], mitad), dato(*datos[i + 1], mitad) if i + 1 < len(datos) else ""]
                     for i in range(0, len(datos), 2)]
        renglones.append([dato("map-pin", "Domicilio fiscal", domicilio, ANCHO - 24), ""])
        t = Table(renglones, colWidths=[mitad, mitad])
        t.setStyle(_sin_relleno([("SPAN", (0, len(renglones) - 1), (1, len(renglones) - 1)),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        el += [KeepTogether([_titulo("Datos de la constancia", "user", est), Spacer(1, 7),
                             _tarjeta(t, fondo=NAVY_SUAVE, borde=NAVY_SUAVE, padding=12)]), Spacer(1, 14)]

    # --- 7. Cómo validar en el SAT ------------------------------------------
    def paso(n, texto_paso):
        t = Table([[_numero(n, NAVY, 18), Paragraph(texto_paso, est["chico"])]], colWidths=[0.75 * cm, None])
        t.setStyle(_sin_relleno())
        return t
    pasos = Table([[paso(1, "<b>Escanea</b> el QR con el celular o haz clic en el link."),
                    paso(2, "<b>Revisa</b> que la página sea <b>siat.sat.gob.mx</b>."),
                    paso(3, "<b>Compara</b> los datos del SAT contra el documento.")]],
                  colWidths=[ANCHO / 3] * 3)
    pasos.setStyle(_sin_relleno([("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    sat = [CondPageBreak(8 * cm), _titulo("Cómo validar en el portal del SAT", "qr-code", est), Spacer(1, 7),
           pasos, Spacer(1, 8)]
    celdas = []
    for i, url in enumerate(analisis.urls_qr[:2], 1):
        oficial = url.startswith("https://siat.sat.gob.mx/")
        que = ("nombre, RFC, CURP, situación, régimen y domicilio" if i == 1 else "fecha y RFC de la cadena original")
        if oficial:
            cuerpo = [Paragraph(f'<font color="{NAVY}"><b>QR {i} · {"cédula" if i == 1 else "sello"}</b></font>',
                                est["sec_nombre"]), Spacer(1, 2),
                      Paragraph(f"Compara: {que}.", est["chico"]), Spacer(1, 5),
                      Paragraph(f'<a href="{_esc(url)}" color="{NAVY_MEDIO}"><u>Abrir en siat.sat.gob.mx</u></a>',
                                est["base"])]
            celda = Table([[_qr_imagen(url) or "", cuerpo]], colWidths=[2.95 * cm, None])
            celda.setStyle(_sin_relleno())
            fondo, borde = "#FFFFFF", LINEA
        else:
            rojo, rojo_suave = ESTADO["FALLA"][0], ESTADO["FALLA"][1]
            cuerpo = [Paragraph(f'<font color="{rojo}"><b>QR {i}: página NO oficial</b></font>', est["sec_nombre"]),
                      Paragraph("Lleva a una página que no es del SAT. No la abras ni la uses para validar:",
                                est["chico"]),
                      Paragraph(f'<font color="{rojo}">{_esc(url[:90])}</font>', est["chico"])]
            celda = Table([[_burbuja("shield-x", rojo, "#FFFFFF", 1.2 * cm), cuerpo]], colWidths=[1.5 * cm, None])
            celda.setStyle(_sin_relleno())
            fondo, borde = rojo_suave, rojo_suave
        celdas.append(_tarjeta(celda, fondo=fondo, borde=borde, ancho=(ANCHO - 10) / 2, padding=9))
    if celdas:
        fila = Table([celdas + ([""] if len(celdas) == 1 else [])],
                     colWidths=[(ANCHO - 10) / 2 + 10, (ANCHO - 10) / 2])
        fila.setStyle(_sin_relleno([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        sat.append(fila)
    else:
        sat.append(Paragraph("No se leyó ningún QR del documento.", est["base"]))
    el += [KeepTogether(sat), Spacer(1, 16)]

    # --- 8. Detalle de candados ----------------------------------------------
    chips = Table([[x for e, txt in LEYENDA for x in (_pastilla(e, est, 1.55 * cm), Paragraph(txt, est["chico"]))]],
                  colWidths=[1.65 * cm, ANCHO / 4 - 1.65 * cm] * 4)
    chips.setStyle(_sin_relleno())
    el += [CondPageBreak(6 * cm),
           _titulo("Detalle de los candados", "list-checks", est, "Cada candado, qué encontró y qué fraude previene."),
           Spacer(1, 6), chips, Spacer(1, 10)]
    for sec, (nombre, icono, pregunta) in SECCIONES.items():
        lista, cuenta = cuenta_de(sec)
        if not lista:
            continue
        e, _txt = estado_seccion(cuenta)
        ok = cuenta["OK"] + cuenta["INFO"]
        banda = Table([[_burbuja(icono, "#FFFFFF", NAVY_MEDIO, 0.75 * cm),
                        [Paragraph(f'<a name="sec{sec}"/><font color="#FFFFFF"><b>{sec}. {_esc(nombre)}</b></font>',
                                   est["sec_nombre"]),
                         Paragraph(f'<font color="{LAVANDA}">{_esc(pregunta)}</font>', est["chico"])],
                        Paragraph(f'<font color="#FFFFFF"><b>{ok}/{len(lista)}</b></font>',
                                  ParagraphStyle("b", parent=est["der"], fontSize=12, leading=14)),
                        _pastilla(e, est, 1.95 * cm)]],
                      colWidths=[1.0 * cm, ANCHO - 1.0 * cm - 1.5 * cm - 2.3 * cm - 16, 1.5 * cm, 2.3 * cm])
        banda.setStyle(_sin_relleno([("ALIGN", (3, 0), (3, 0), "RIGHT"), ("LEFTPADDING", (3, 0), (3, 0), 8)]))
        cab = _tarjeta(banda, fondo=NAVY, borde=NAVY, padding=8, radio=8)
        cab._marcador = (f"{sec}. {nombre}", f"sec{sec}")
        filas = []
        estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LINEBELOW", (0, 0), (-1, -2), 0.4, _hex(LINEA)),
                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                  ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        for i, c in enumerate(lista):
            det = _esc(c.detalle)
            if c.previene:
                det += f'<br/><font color="{GRIS_CLARO}" size="7">Previene: {_esc(c.previene)}</font>'
            filas.append([Paragraph(f'<font color="{NAVY_MEDIO}"><b>{_esc(c.clave)}</b></font>', est["chico"]),
                          Paragraph(f"<b>{_esc(c.titulo)}</b>", est["base"]),
                          _pastilla(c.estado, est), Paragraph(det, est["base"])])
            if c.estado in ("FALLA", "AVISO"):
                estilo.append(("BACKGROUND", (0, i), (-1, i), _hex(ESTADO[c.estado][1])))
            elif i % 2:
                estilo.append(("BACKGROUND", (0, i), (-1, i), _hex(FONDO)))
        t = Table(filas, colWidths=[1.0 * cm, 4.4 * cm, 1.8 * cm, None])
        t.setStyle(TableStyle(estilo))
        el += [CondPageBreak(4 * cm), cab, Spacer(1, 4), t, Spacer(1, 14)]

    el += [_tarjeta([Paragraph("Este análisis revisa candados técnicos del archivo y no sustituye la consulta al "
                               "portal del SAT. Huella SHA-256 del archivo revisado:", est["chico"]),
                     Paragraph(f'<font name="Courier" size="7" color="{NAVY}">{analisis.sha256}</font>',
                               est["chico"])], fondo=FONDO, borde=FONDO, padding=9)]

    # --- Portada, banda y pie --------------------------------------------------
    def pagina(cv, doc):
        cv.saveState()
        an, al = letter
        primera = doc.page == 1
        alto = 3.0 * cm if primera else 1.4 * cm
        cv.setFillColor(_hex(NAVY))
        cv.rect(0, al - alto, an, alto, fill=1, stroke=0)
        # Decoración: círculos translúcidos a la derecha de la banda.
        cv.setFillColor(_hex("#FFFFFF"))
        for x, y, r, a in ((an - 2.2 * cm, al - 0.3 * cm, 2.4 * cm, 0.06),
                           (an - 0.4 * cm, al - 2.6 * cm, 1.8 * cm, 0.05),
                           (an - 5.4 * cm, al - 3.2 * cm, 1.4 * cm, 0.04)):
            cv.setFillAlpha(a)
            cv.circle(x, y, r * (1 if primera else 0.6), fill=1, stroke=0)
        cv.setFillAlpha(1)
        # Franja inferior: rojo de la marca, azul medio y el color del veredicto.
        franja = al - alto - 0.12 * cm
        for x0, ancho_f, color in ((0, 0.62, ROJO_MG), (0.62, 0.23, NAVY_MEDIO), (0.85, 0.15, c_ver)):
            cv.setFillColor(_hex(color))
            cv.rect(an * x0, franja, an * ancho_f, 0.12 * cm, fill=1, stroke=0)
        if primera:
            cv.setFillColor(_hex("#FFFFFF"))
            cv.setFont("Helvetica-Bold", 7.5)
            cv.drawString(MARGEN, al - 0.95 * cm, "REPORTE DE AUTENTICIDAD")
            cv.setFont("Helvetica-Bold", 17)
            cv.drawString(MARGEN, al - 1.75 * cm, "Validación de Constancia de Situación Fiscal")
            cv.setFont("Helvetica", 8.5)
            cv.setFillColor(_hex(LAVANDA))
            cv.drawString(MARGEN, al - 2.35 * cm, f"Archivo: {analisis.archivo[:70]}")
            # Pastilla blanca con el RFC
            rfc = d.get("rfc") or "RFC no legible"
            cv.setFont("Helvetica-Bold", 10)
            w = cv.stringWidth(rfc, "Helvetica-Bold", 10) + 0.8 * cm
            cv.setFillColor(_hex("#FFFFFF"))
            cv.roundRect(an - MARGEN - w, al - 1.5 * cm, w, 0.62 * cm, 0.31 * cm, fill=1, stroke=0)
            cv.setFillColor(_hex(NAVY))
            cv.drawCentredString(an - MARGEN - w / 2, al - 1.29 * cm, rfc)
            cv.setFont("Helvetica", 8)
            cv.setFillColor(_hex(LAVANDA))
            cv.drawRightString(an - MARGEN, al - 1.95 * cm, fecha_texto)
            cv.drawRightString(an - MARGEN, al - 2.35 * cm, f"Folio {folio}")
        else:
            cv.setFillColor(_hex("#FFFFFF"))
            cv.setFont("Helvetica-Bold", 10)
            cv.drawString(MARGEN, al - 0.85 * cm, "Validación de Constancia de Situación Fiscal")
            cv.setFont("Helvetica", 8)
            cv.setFillColor(_hex(LAVANDA))
            cv.drawRightString(an - MARGEN, al - 0.85 * cm,
                               f"{d.get('rfc') or analisis.archivo[:40]} · Folio {folio}")
        # Pie
        cv.setStrokeColor(_hex(LINEA))
        cv.setLineWidth(0.6)
        cv.line(MARGEN, 1.1 * cm, an - MARGEN, 1.1 * cm)
        cv.setFont("Helvetica", 7)
        cv.setFillColor(_hex(GRIS))
        cv.drawString(MARGEN, 0.75 * cm, "Análisis automático · no sustituye la consulta al portal del SAT")
        cv.restoreState()

    doc = _Documento(ruta_salida, pagina, title=f"Validación CSF {d.get('rfc', '')}", subject=ver,
                     creator="Reportes y Herramientas")
    doc.build([NextPageTemplate("resto")] + el, canvasmaker=_CanvasNumerado)
    return ruta_salida
