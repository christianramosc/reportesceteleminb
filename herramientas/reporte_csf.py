# -*- coding: utf-8 -*-
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

from reportlab.graphics.shapes import Drawing, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)

try:
    from . import iconos as _iconos
except ImportError:  # ejecución suelta
    _iconos = None

# --- Paleta -----------------------------------------------------------------
AZUL = "#191970"        # azul Inbursa
ROJO_MG = "#C8102E"     # acento MG
TINTA = "#0F172A"
GRIS = "#64748B"
GRIS_CLARO = "#94A3B8"
LINEA = "#E2E8F0"
FONDO = "#F8FAFC"
ESTADO = {  # estado -> (color fuerte, fondo suave, icono lucide, etiqueta)
    "OK": ("#15803D", "#DCFCE7", "circle-check", "OK"),
    "AVISO": ("#B45309", "#FEF3C7", "circle-alert", "AVISO"),
    "FALLA": ("#B91C1C", "#FEE2E2", "circle-x", "FALLA"),
    "INFO": ("#475569", "#E2E8F0", "info", "INFO"),
}
VEREDICTO = {  # veredicto -> (color, fondo, icono, frase)
    "SIN INDICIOS DE ALTERACIÓN": ("#15803D", "#F0FDF4", "shield-check",
                                   "Pasó los candados técnicos. Valida los QR en el SAT antes de usarla."),
    "REVISAR MANUALMENTE": ("#B45309", "#FFFBEB", "shield-alert",
                            "Hay avisos con explicación legítima posible. Confírmalos en el QR del SAT."),
    "ALTERADA / NO CONFIABLE": ("#B91C1C", "#FEF2F2", "shield-x",
                                "Hay indicios de alteración. No la uses para el expediente."),
    "NO VERIFICABLE": ("#B91C1C", "#FEF2F2", "shield-x",
                       "Es una foto o captura: no se puede validar. Pide el PDF original del SAT."),
}
SECCIONES = {1: ("Archivo y estructura", "file-search"), 2: ("Códigos QR y de barras", "qr-code"),
             3: ("Coherencia de datos", "fingerprint"), 4: ("Políticas de la financiera", "calendar-check")}

ANCHO = letter[0] - 3.0 * cm      # ancho útil (márgenes de 1.5 cm)


def _esc(t):
    return html.escape(str(t if t is not None else ""))


def _ico(nombre, tam, color):
    if _iconos is None:
        return None
    return _iconos.icono(nombre, tam, color)


def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.8, leading=12, textColor=colors.HexColor(TINTA))
    return {
        "base": base,
        "chico": ParagraphStyle("chico", parent=base, fontSize=7.6, leading=10, textColor=colors.HexColor(GRIS)),
        "etq": ParagraphStyle("etq", parent=base, fontSize=7, leading=9, textColor=colors.HexColor(GRIS)),
        "valor": ParagraphStyle("valor", parent=base, fontName="Helvetica-Bold", fontSize=9.2, leading=12),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                             textColor=colors.HexColor(AZUL)),
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
    escudo = _ico(i_ver, 34, c_ver)
    texto = [Paragraph('<font size="7.5" color="#64748B">VEREDICTO DE AUTENTICIDAD</font>', est["base"]),
             Spacer(1, 3),
             Paragraph(f'<font color="{c_ver}">{_esc(ver)}</font>', est["ver"]),
             Spacer(1, 3), Paragraph(_esc(frase), est["base"])]
    if ver == "SIN INDICIOS DE ALTERACIÓN" and not analisis.cumple_politicas:
        texto += [Spacer(1, 4), Paragraph(
            '<font color="#B45309"><b>Auténtica, pero no cumple políticas</b> (vigencia o estatus): '
            'pide al cliente una constancia reciente.</font>', est["base"])]
    interior = Table([[escudo or "", texto, _anillo(aprobados, len(tecnicos), c_ver)]],
                     colWidths=[1.6 * cm, ANCHO - 1.6 * cm - 3.3 * cm - 0.36 * cm - 24, 3.3 * cm])
    interior.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "CENTER"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    el += [_tarjeta(interior, fondo=f_ver, borde=c_ver, barra=c_ver, padding=12), Spacer(1, 10)]

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
        cifra("Candados técnicos", f"{aprobados}/{len(tecnicos)}", AZUL, "shield-check",
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
        el += [CondPageBreak(5 * cm), _titulo("Datos de la constancia", "user", est), Spacer(1, 6),
               _tarjeta(t, fondo=FONDO, padding=10), Spacer(1, 12)]

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
                      Paragraph(f'<a href="{_esc(url)}" color="#1D4ED8"><u>Abrir en siat.sat.gob.mx</u></a>',
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
        alto_banda = 2.3 * cm if primera else 1.35 * cm
        cv.setFillColor(colors.HexColor(AZUL))
        cv.rect(0, al - alto_banda, an, alto_banda, fill=1, stroke=0)
        cv.setFillColor(colors.HexColor(ROJO_MG))
        cv.rect(0, al - alto_banda - 0.09 * cm, an, 0.09 * cm, fill=1, stroke=0)
        cv.setFillColor(colors.white)
        if primera:
            cv.setFont("Helvetica-Bold", 15)
            cv.drawString(1.5 * cm, al - 1.05 * cm, "Validación de Constancia de Situación Fiscal")
            cv.setFont("Helvetica", 8.5)
            cv.setFillColor(colors.HexColor("#C7D2FE"))
            cv.drawString(1.5 * cm, al - 1.6 * cm, f"Archivo: {analisis.archivo[:80]}")
            cv.drawString(1.5 * cm, al - 2.0 * cm, "Autoexpress Inbursa · MG Financial Services")
            cv.setFillColor(colors.white)
            cv.setFont("Helvetica-Bold", 9)
            cv.drawRightString(an - 1.5 * cm, al - 1.05 * cm, d.get("rfc") or "")
            cv.setFont("Helvetica", 8)
            cv.setFillColor(colors.HexColor("#C7D2FE"))
            cv.drawRightString(an - 1.5 * cm, al - 1.6 * cm, fecha_texto)
            cv.drawRightString(an - 1.5 * cm, al - 2.0 * cm, f"Folio {analisis.sha256[:10].upper()}")
        else:
            cv.setFont("Helvetica-Bold", 10)
            cv.drawString(1.5 * cm, al - 0.85 * cm, "Validación de Constancia de Situación Fiscal")
            cv.setFont("Helvetica", 8)
            cv.drawRightString(an - 1.5 * cm, al - 0.85 * cm, f"{d.get('rfc') or analisis.archivo[:40]}")
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
