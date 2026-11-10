"""
Reporte PDF de "Validar CSF" — versión visual.

Paleta Midnight Black / Electric Blue / Cantaloupe Orange; cada estatus
(OK, AVISO, FALLA, INFO) lleva su propio color e ícono, así se entiende
también impreso en blanco y negro.

Página 1 (lo esencial en 10 segundos):
  - Encabezado negro con corte en diagonal; RFC, fecha y folio a la derecha.
  - Veredicto en un bloque sólido de su color, con el anillo de candados aprobados.
  - Cifras: candados técnicos, fallas, avisos y vigencia.
  - Barras por sección (cada una lleva al detalle con un clic).
  - Observaciones: solo lo que falló o pide revisión.
  - Datos de la constancia.
  - Validación en el SAT: los QR oficiales regenerados (escaneables desde la
    pantalla) y links clicables. Un QR que NO va al SAT no se dibuja ni se enlaza.
Páginas siguientes: el detalle de los 33 candados, con marcadores (índice
lateral del lector de PDF) por sección.

El PDF se arma dos veces: la primera solo cuenta las páginas para poder
escribir "Página X de Y" en la segunda sin romper los enlaces internos.
"""

import copy
import html
import io

from reportlab.graphics.shapes import Circle, Drawing, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import fechas as _fechas
from . import iconos as _iconos
from . import validar_csf as _v

# --- Paleta -----------------------------------------------------------------
# Midnight Black, Electric Blue y Cantaloupe Orange. El azul eléctrico
# (3.2:1 sobre blanco) y el naranja (2.7:1) no alcanzan para texto sobre
# blanco: van en el encabezado oscuro, iconos y franjas; los links usan un
# azul un poco más oscuro (5:1).
NEGRO = "#02070A"         # Midnight Black: encabezado y títulos
AZUL = "#0297DE"          # Electric Blue: iconos y franja
NARANJA = "#FC734D"       # Cantaloupe Orange: franja
ENLACE = "#0275B0"
TEXTO_SUAVE = "#A9B6BF"   # texto secundario sobre el negro (9.8:1)
TINTA = "#0F172A"
GRIS = "#64748B"
GRIS_CLARO = "#94A3B8"
LINEA = "#E2E8F0"
FONDO = "#F8FAFC"
# Estados en la familia de la paleta: OK azul, AVISO naranja, FALLA carmín.
# Todos con contraste >= 4.5:1 sobre blanco (también con texto blanco
# encima, en el bloque del veredicto), y AVISO y FALLA se distinguen por
# claridad, no solo por tono.
ESTADO = {  # estado -> (color fuerte, fondo suave, icono lucide, etiqueta)
    "OK": ("#0275B0", "#E3F3FB", "circle-check", "OK"),
    "AVISO": ("#C2501F", "#FFEDE5", "circle-alert", "AVISO"),
    "FALLA": ("#B3123A", "#FBE3E8", "circle-x", "FALLA"),
    "INFO": ("#5B6876", "#ECEFF2", "info", "INFO"),
}
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
                             textColor=colors.HexColor(NEGRO)),
        "cifra": ParagraphStyle("cifra", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=23),
        "ver": ParagraphStyle("ver", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21),
        "titulo_c": ParagraphStyle("tc", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12),
    }


# ===========================================================================
#  Piezas gráficas
# ===========================================================================
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
    ic = _ico(icono, 13, AZUL)
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
            # Un título con ancla ya define su destino (<a name> en el
            # párrafo, justo en el título); los demás marcan la página.
            clave = ancla or f"m{id(f)}"
            if not ancla:
                self.canv.bookmarkPage(clave)
            self.canv.addOutlineEntry(texto, clave, level=0)


# ===========================================================================
#  Reporte
# ===========================================================================
def _encabezado(cv, an, al, primera, analisis, d, fecha_texto):
    """Bloque negro con un corte en diagonal y dos franjas (azul y naranja).
    El RFC, la fecha y el folio quedan sobre blanco, a la derecha."""
    C = colors.HexColor
    alto = 2.3 * cm if primera else 1.35 * cm
    y = al - alto
    corte = an * 0.68
    arriba = corte + alto * 0.6          # dónde toca el corte el borde superior
    for color, puntos in ((NEGRO, [(0, al), (arriba, al), (corte, y), (0, y)]),
                          (AZUL, [(arriba, al), (arriba + 0.35 * cm, al), (corte + 0.35 * cm, y), (corte, y)]),
                          (NARANJA, [(arriba + 0.35 * cm, al), (arriba + 0.47 * cm, al),
                                     (corte + 0.47 * cm, y), (corte + 0.35 * cm, y)])):
        trazo = cv.beginPath()
        trazo.moveTo(*puntos[0])
        for punto in puntos[1:]:
            trazo.lineTo(*punto)
        trazo.close()
        cv.setFillColor(C(color))
        cv.drawPath(trazo, fill=1, stroke=0)

    x0, x1 = 1.5 * cm, an - 1.5 * cm
    titulo = "Validación de Constancia de Situación Fiscal"
    rfc = d.get("rfc") or ""
    if primera:
        cv.setFillColor(colors.white)
        cv.setFont("Helvetica-Bold", 14.5)
        cv.drawString(x0, y + alto - 0.82 * cm, titulo)
        cv.setFont("Helvetica", 8.5)
        cv.setFillColor(C(TEXTO_SUAVE))
        cv.drawString(x0, y + 0.48 * cm, f"Archivo: {analisis.archivo[:70]}")
        cv.setFillColor(C(NEGRO))
        cv.setFont("Helvetica-Bold", 9.5)
        cv.drawRightString(x1, y + alto - 0.82 * cm, rfc)
        cv.setFont("Helvetica", 8)
        cv.setFillColor(C(GRIS))
        cv.drawRightString(x1, y + 0.88 * cm, fecha_texto)
        cv.drawRightString(x1, y + 0.48 * cm, f"Folio {analisis.sha256[:10].upper()}")
    else:
        cv.setFillColor(colors.white)
        cv.setFont("Helvetica-Bold", 9.5)
        cv.drawString(x0, y + alto / 2 - 0.12 * cm, titulo)
        cv.setFont("Helvetica", 8)
        cv.setFillColor(C(GRIS))
        cv.drawRightString(x1, y + alto / 2 - 0.12 * cm, rfc or analisis.archivo[:40])


def _anillo_claro(aprobados, total, lado=3.0 * cm):
    """Anillo de candados en blanco, para dibujarlo sobre el color del veredicto."""
    d = Drawing(lado, lado)
    r = lado / 2 - 2
    grosor = lado * 0.12
    d.add(Wedge(lado / 2, lado / 2, r, 0, 360, radius1=r - grosor,
                fillColor=colors.Color(1, 1, 1, alpha=0.28), strokeColor=None))
    if total and aprobados:
        ini, fin = (0, 360) if aprobados >= total else (90 - 360 * aprobados / total, 90)
        d.add(Wedge(lado / 2, lado / 2, r, ini, fin, radius1=r - grosor, fillColor=colors.white, strokeColor=None))
    d.add(String(lado / 2, lado / 2 + 1, f"{aprobados}/{total}", fontName="Helvetica-Bold",
                 fontSize=lado * 0.17, fillColor=colors.white, textAnchor="middle"))
    d.add(String(lado / 2, lado / 2 - lado * 0.14, "candados", fontName="Helvetica",
                 fontSize=lado * 0.085, fillColor=colors.white, textAnchor="middle"))
    return d


def _veredicto(ver, c_ver, i_ver, frase, aprobados, total, nota_politicas, est):
    """Bloque sólido del color del veredicto: escudo en un círculo blanco,
    el veredicto en blanco y el anillo de candados."""
    texto = [Paragraph('<font size="7.5" color="#E6F1F8"><b>VEREDICTO DE AUTENTICIDAD</b></font>', est["base"]),
             Spacer(1, 3), Paragraph(f'<font color="#FFFFFF">{_esc(ver)}</font>', est["ver"]),
             Spacer(1, 3), Paragraph(f'<font color="#FFFFFF">{_esc(frase)}</font>', est["base"])]
    if nota_politicas:
        texto += [Spacer(1, 5), Paragraph(f'<font color="#FFFFFF">{nota_politicas}</font>', est["base"])]
    burbuja = Drawing(1.5 * cm, 1.5 * cm)
    burbuja.add(Circle(0.75 * cm, 0.75 * cm, 0.75 * cm, fillColor=colors.white, strokeColor=None))
    ic = _ico(i_ver, 26, c_ver)
    if ic is not None:
        ic.translate((1.5 * cm - ic.width) / 2, (1.5 * cm - ic.height) / 2)
        burbuja.add(ic)
    interior = Table([[burbuja, texto, _anillo_claro(aprobados, total)]],
                     colWidths=[1.9 * cm, ANCHO - 1.9 * cm - 3.3 * cm - 28, 3.3 * cm])
    interior.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "CENTER"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return _tarjeta(interior, fondo=c_ver, borde=c_ver, padding=14)


def generar(analisis, ruta_salida, fecha_texto=""):
    est = _estilos()
    d = analisis.datos or {}
    candados = analisis.candados
    ver = analisis.veredicto
    c_ver, _fondo, i_ver, frase = VEREDICTO.get(ver, (ESTADO["INFO"][0], FONDO, "shield-alert", ""))
    tecnicos = [c for c in candados if c.seccion < 4]
    aprobados = sum(c.estado in ("OK", "INFO") for c in tecnicos)
    n_fallas = sum(c.estado == "FALLA" for c in candados)
    n_avisos = sum(c.estado == "AVISO" for c in candados)
    emision = d.get("fecha_emision")
    dias = (_fechas.hoy() - emision).days if emision else None
    vigente = _v.vigente(dias)
    el = []

    # --- 1. Veredicto -------------------------------------------------------
    nota_politicas = None
    if ver in ("SIN INDICIOS DE ALTERACIÓN", "COPIA: DATOS COINCIDEN") and not analisis.cumple_politicas:
        nota_politicas = ("<b>Además, no cumple políticas</b> (vigencia o estatus): "
                          "pide al cliente una constancia reciente.")
    el += [_veredicto(ver, c_ver, i_ver, frase, aprobados, len(tecnicos), nota_politicas, est),
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
        cifra("Candados técnicos", f"{aprobados}/{len(tecnicos)}", NEGRO, "shield-check",
              "archivo, códigos y datos"),
        cifra("Fallas", n_fallas, ESTADO["FALLA"][0] if n_fallas else GRIS_CLARO, "circle-x",
              "indicios de alteración" if n_fallas else "ninguna"),
        cifra("Avisos", n_avisos, ESTADO["AVISO"][0] if n_avisos else GRIS_CLARO, "circle-alert",
              "revisar a mano" if n_avisos else "ninguno"),
        cifra("Emitida hace", "—" if dias is None else (f"{dias} días" if dias >= 0 else "en el futuro"),
              ESTADO["OK"][0] if vigente else ESTADO["FALLA"][0], "calendar-check",
              (f'<font color="{ESTADO["OK"][0] if vigente else ESTADO["FALLA"][0]}"><b>'
               f'{"Vigente" if vigente else "Vencida"}</b></font> · máximo {_v.DIAS_VIGENCIA} días') if dias is not None else ""),
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
        filas.append([_ico(icono, 12, AZUL) or "",
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
    # Sin QR leídos no hay nada que escanear: la instrucción de "escanea cada
    # QR" quedaba sobre una sección vacía. Se dice qué hacer en su lugar.
    urls_qr = analisis.urls_qr[:2]
    sat = [CondPageBreak(7 * cm if urls_qr else 3.5 * cm),
           _titulo("Valida en el portal del SAT", "qr-code", est), Spacer(1, 2)]
    if urls_qr:
        sat += [Paragraph("Escanea cada QR con el celular o haz clic en el link y compara lo que muestra el "
                          "SAT contra el documento.", est["chico"]), Spacer(1, 6)]
    else:
        sat += [Spacer(1, 4),
                _tarjeta(Paragraph(f'<font color="{ESTADO["AVISO"][0]}"><b>No se leyó ningún QR en el '
                                   'documento:</b></font> no hay enlace oficial con el que validarlo. '
                                   'Pide al cliente el PDF original descargado del portal del SAT.',
                                   est["base"]),
                         fondo=ESTADO["AVISO"][1], borde=ESTADO["AVISO"][1], barra=ESTADO["AVISO"][0],
                         padding=8),
                Spacer(1, 8)]
    celdas = []
    for i, url in enumerate(urls_qr, 1):
        oficial = url.startswith("https://siat.sat.gob.mx/")
        que = ("nombre, RFC, CURP, situación, régimen y domicilio" if i == 1 else "fecha y RFC de la cadena original")
        if oficial:
            img = _qr_imagen(url)
            cuerpo = [Paragraph(f"<b>QR {i} · {'cédula' if i == 1 else 'sello'}</b>", est["titulo_c"]),
                      Paragraph(f"Compara: {que}.", est["chico"]), Spacer(1, 4),
                      Paragraph(f'<a href="{_esc(url)}" color="{ENLACE}"><u>Abrir en siat.sat.gob.mx</u></a>',
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
        t = Table(filas, colWidths=[1.05 * cm, 4.45 * cm, 1.75 * cm, None])
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
    # "Página X de Y" necesita el total. Antes se guardaban las páginas y se
    # numeraban al final (un Canvas especial), pero así todos los enlaces y
    # el índice lateral apuntaban a la página 1. Ahora se arma dos veces: la
    # primera, en memoria, solo para contar las páginas.
    total = {"paginas": 0}

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
        if total["paginas"]:
            cv.drawRightString(an - 1.5 * cm, 0.85 * cm, f"Página {doc.page} de {total['paginas']}")
        cv.restoreState()

    historia = [NextPageTemplate("resto")] + el
    # reportlab modifica las piezas al acomodarlas: la pasada de conteo
    # trabaja sobre una copia.
    conteo = _Documento(io.BytesIO(), pagina)
    conteo.build(copy.deepcopy(historia))
    total["paginas"] = conteo.page
    doc = _Documento(ruta_salida, pagina, title=f"Validación CSF {d.get('rfc', '')}", subject=ver,
                     creator="Reportes y Herramientas")
    doc.build(historia)
    return ruta_salida
