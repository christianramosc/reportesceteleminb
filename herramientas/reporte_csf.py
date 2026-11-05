"""
Reporte PDF de "Validar CSF" — formato de dictamen.

Formal y en blanco y negro: membrete con filetes, títulos en serif, tablas
con líneas finas y el color SOLO donde dice algo (veredicto, OK / AVISO /
FALLA, vigencia). Así se imprime bien en blanco y negro y el color, cuando
aparece, llama la atención por una razón.

Página 1 (lo esencial):
  1. Resultado: veredicto, candados aprobados, fallas, avisos y vigencia.
  2. Resumen por sección (cada sección lleva a su detalle con un clic).
  3. Observaciones: solo lo que falló o pide revisión.
  4. Validación en el portal del SAT: los QR oficiales regenerados
     (escaneables desde la pantalla) y sus links. Un QR que NO va al SAT
     no se dibuja ni se enlaza.
Páginas siguientes: 5. el detalle de los 33 candados, con marcadores
(índice lateral del lector de PDF) por sección.

No lleva casillas, firmas ni datos de quién revisa: es el resultado de
un análisis automático, no un formulario.
"""

import html
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)

# --- Paleta -----------------------------------------------------------------
# Del documento: blanco, negro y grises neutros.
NEGRO = "#111111"
GRIS = "#5A5A5A"          # texto secundario (6.9:1 sobre blanco)
GRIS_CLARO = "#8C8C8C"    # notas pequeñas
LINEA = "#CFCFCF"         # líneas finas de tablas
# Con significado: NO se cambian por estética.
ESTADO = {  # estado -> (color del texto, fondo suave del renglón)
    "OK": ("#15803D", "#DCFCE7"),
    "AVISO": ("#B45309", "#FEF3C7"),
    "FALLA": ("#B91C1C", "#FEE2E2"),
    "INFO": ("#475569", "#E2E8F0"),
}
VEREDICTO = {  # veredicto -> (color, frase)
    "SIN INDICIOS DE ALTERACIÓN": ("#15803D",
                                   "Pasó los candados técnicos. Valida los QR en el SAT antes de usarla."),
    "REVISAR MANUALMENTE": ("#B45309",
                            "Hay avisos con explicación legítima posible. Confírmalos en el QR del SAT."),
    "ALTERADA / NO CONFIABLE": ("#B91C1C",
                                "Hay indicios de alteración. No la uses para el expediente."),
    "COPIA: DATOS COINCIDEN": ("#1D4ED8",
                               "Copia (escaneo o foto): los códigos y los datos legibles coinciden, pero por ser copia NO se puede comprobar que no se alteró antes de escanearse. Valida el QR en el SAT o pide el PDF original."),
    "COPIA: REVISAR A MANO": ("#B45309",
                              "Copia (escaneo o foto): algo no se alcanzó a leer o quedó dudoso. Revisa los avisos y valida el QR en el SAT, o pide el PDF original."),
    "NO VERIFICABLE": ("#B91C1C",
                       "No verificable: no se pudo leer ningún código de la copia. Pide el PDF original del SAT."),
}
SECCIONES = {1: "Archivo y estructura del PDF", 2: "Códigos QR y código de barras",
             3: "Coherencia de los datos fiscales", 4: "Políticas de la financiera"}

MARGEN = 2.0 * cm
ANCHO = letter[0] - 2 * MARGEN      # ancho útil


def _esc(t):
    return html.escape(str(t if t is not None else ""))


def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.8, leading=12.2,
                          textColor=colors.HexColor(NEGRO))
    return {
        "base": base,
        "chico": ParagraphStyle("chico", parent=base, fontSize=7.6, leading=10, textColor=colors.HexColor(GRIS)),
        "etq": ParagraphStyle("etq", parent=base, fontSize=6.6, leading=8.5, textColor=colors.HexColor(GRIS)),
        "valor": ParagraphStyle("valor", parent=base, fontName="Helvetica-Bold", fontSize=9, leading=11.5),
        "titulo": ParagraphStyle("titulo", parent=base, fontName="Times-Bold", fontSize=23, leading=26),
        "subtitulo": ParagraphStyle("subtitulo", parent=base, fontName="Times-Italic", fontSize=11, leading=14,
                                    textColor=colors.HexColor(GRIS)),
        "h1": ParagraphStyle("h1", parent=base, fontName="Times-Bold", fontSize=13.5, leading=17),
        "h2": ParagraphStyle("h2", parent=base, fontName="Times-Bold", fontSize=11, leading=14),
        "ver": ParagraphStyle("ver", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18),
        "cifra": ParagraphStyle("cifra", parent=base, fontName="Times-Bold", fontSize=20, leading=22,
                                alignment=TA_CENTER),
        "cifra_etq": ParagraphStyle("cifra_etq", parent=base, fontSize=6.6, leading=8.5, alignment=TA_CENTER,
                                    textColor=colors.HexColor(GRIS)),
        "th": ParagraphStyle("th", parent=base, fontName="Helvetica-Bold", fontSize=7, leading=9,
                             textColor=colors.HexColor(NEGRO)),
        "der": ParagraphStyle("der", parent=base, alignment=TA_RIGHT),
    }


def _estado(estado, est, tam=7.4):
    """El estado como palabra en su color: OK, AVISO, FALLA, INFO."""
    color = ESTADO[estado][0]
    return Paragraph(f'<font color="{color}"><b>{estado}</b></font>',
                     ParagraphStyle("e", parent=est["base"], fontSize=tam, leading=tam + 2.5))


def _sin_relleno(extra=()):
    return TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"), *extra])


def _seccion(numero, texto, est, ancla=None):
    """Título de sección numerado, con un filete fino debajo."""
    p = Paragraph((f'<a name="{ancla}"/>' if ancla else "") + f"{numero}.&nbsp;&nbsp;{_esc(texto)}", est["h1"])
    t = Table([[p]], colWidths=[ANCHO])
    t.setStyle(_sin_relleno([("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor(NEGRO)),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    t._marcador = (f"{numero}. {texto}", ancla)      # índice lateral del lector de PDF
    return t


def _tabla(filas, anchos, est, encabezado=None, tintes=()):
    """Tabla formal: encabezado en negritas con filete negro, renglones con
    línea gris fina. `tintes` = [(renglón, color de fondo), ...]."""
    datos = ([[Paragraph(_esc(h).upper(), est["th"]) for h in encabezado]] if encabezado else []) + filas
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
              ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
              ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINEA))]
    if encabezado:
        estilo += [("LINEABOVE", (0, 0), (-1, 0), 0.9, colors.HexColor(NEGRO)),
                   ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(NEGRO)),
                   ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 4)]
    desfase = 1 if encabezado else 0
    for i, color in tintes:
        estilo.append(("BACKGROUND", (0, i + desfase), (-1, i + desfase), colors.HexColor(color)))
    t = Table(datos, colWidths=anchos, repeatRows=1 if encabezado else 0)
    t.setStyle(TableStyle(estilo))
    return t


def _qr_imagen(url, lado=2.6 * cm):
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
#  Documento: membrete, pie con "Página X de Y" e índice lateral
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
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor(GRIS))
            self.drawRightString(letter[0] - MARGEN, 1.15 * cm, f"Página {self._pageNumber} de {total}")
            super().showPage()
        super().save()


class _Documento(BaseDocTemplate):
    def __init__(self, ruta, al_dibujar, **kw):
        super().__init__(ruta, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN,
                         topMargin=2.35 * cm, bottomMargin=2.0 * cm, **kw)
        an, al = letter
        self.addPageTemplates([PageTemplate(
            "pagina", [Frame(MARGEN, 2.0 * cm, an - 2 * MARGEN, al - 2.35 * cm - 2.0 * cm, id="f")],
            onPage=al_dibujar)])

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
    c_ver, frase = VEREDICTO.get(ver, (ESTADO["INFO"][0], ""))
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
    vigente = dias is not None and 0 <= dias <= 30
    folio = analisis.sha256[:10].upper()
    el = []

    # --- Título e identificación ------------------------------------------
    el += [Paragraph("Dictamen de validación", est["titulo"]),
           Paragraph("Constancia de Situación Fiscal · análisis de autenticidad", est["subtitulo"]),
           Spacer(1, 12)]

    moral = d.get("tipo") == "moral"
    tipo = {"fisica": "Persona física", "moral": "Persona moral"}.get(d.get("tipo"), "—")
    ident = [
        ("Contribuyente", d.get("nombre_completo")), ("RFC", d.get("rfc")),
        ("CURP", d.get("curp") or ("No aplica" if moral else None)), ("Tipo", tipo),
        ("Estatus en el padrón", d.get("estatus")), ("Emisión", d.get("emision_texto")),
        ("Archivo analizado", analisis.archivo), ("Fecha del análisis", fecha_texto),
    ]

    def celda(etq, valor):
        return [Paragraph(_esc(etq).upper(), est["etq"]), Paragraph(_esc(valor or "—"), est["valor"])]
    mitad = ANCHO / 2
    renglones = [[celda(*ident[i]), celda(*ident[i + 1])] for i in range(0, len(ident), 2)]
    t = Table(renglones, colWidths=[mitad, mitad])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEABOVE", (0, 0), (-1, 0), 0.9, colors.HexColor(NEGRO)),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINEA)),
                           ("LINEBELOW", (0, -1), (-1, -1), 0.9, colors.HexColor(NEGRO)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el += [t, Spacer(1, 18)]

    # --- 1. Resultado ---------------------------------------------------------
    texto = [Paragraph("VEREDICTO DE AUTENTICIDAD", est["etq"]), Spacer(1, 3),
             Paragraph(f'<font color="{c_ver}">{_esc(ver)}</font>', est["ver"]), Spacer(1, 4),
             Paragraph(_esc(frase), est["base"])]
    if ver in ("SIN INDICIOS DE ALTERACIÓN", "COPIA: DATOS COINCIDEN") and not analisis.cumple_politicas:
        texto += [Spacer(1, 4), Paragraph(
            f'<font color="{ESTADO["AVISO"][0]}"><b>Además, no cumple políticas</b> (vigencia o estatus): '
            'pide al cliente una constancia reciente.</font>', est["base"])]

    def cifra(valor, etq, color=NEGRO):
        return [Paragraph(f'<font color="{color}">{_esc(valor)}</font>', est["cifra"]), Spacer(1, 2),
                Paragraph(_esc(etq).upper().replace("\n", "<br/>"), est["cifra_etq"])]
    if dias is not None:
        vigencia = cifra(dias, "Días\nvigente" if vigente else "Días\nvencida",
                         ESTADO["OK"][0] if vigente else ESTADO["FALLA"][0])
    else:
        vigencia = cifra("—", "Emisión")
    cifras = Table([[
        cifra(f"{aprobados}/{len(tecnicos)}", "Candados técnicos"),
        cifra(n_fallas, "Fallas", ESTADO["FALLA"][0] if n_fallas else NEGRO),
        cifra(n_avisos, "Avisos", ESTADO["AVISO"][0] if n_avisos else NEGRO),
        vigencia,
    ]], colWidths=[2.0 * cm] * 4)
    cifras.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LINEBEFORE", (1, 0), (-1, -1), 0.4, colors.HexColor(LINEA)),
                                ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    ancho_cifras = 4 * 2.0 * cm
    caja = Table([["", texto, cifras]], colWidths=[0.16 * cm, ANCHO - 0.16 * cm - ancho_cifras, ancho_cifras])
    caja.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor(NEGRO)),
                              ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(c_ver)),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0),
                              ("LEFTPADDING", (1, 0), (1, 0), 12), ("RIGHTPADDING", (1, 0), (1, 0), 10),
                              ("TOPPADDING", (0, 0), (-1, -1), 11), ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
                              ("LINEBEFORE", (2, 0), (2, 0), 0.4, colors.HexColor(LINEA))]))
    el += [KeepTogether([_seccion(1, "Resultado", est), Spacer(1, 8), caja]), Spacer(1, 18)]

    # --- 2. Resumen por sección ----------------------------------------------
    def num(n, estado=None):
        color = ESTADO[estado][0] if (estado and n) else (NEGRO if n else GRIS_CLARO)
        return Paragraph(f'<font color="{color}">{n}</font>', est["der"])

    filas = []
    for sec, nombre in SECCIONES.items():
        lista = [c for c in candados if c.seccion == sec]
        if not lista:
            continue
        cuenta = {e: sum(c.estado == e for c in lista) for e in ESTADO}
        if cuenta["FALLA"]:
            resultado = f'<font color="{ESTADO["FALLA"][0]}"><b>Con fallas</b></font>'
        elif cuenta["AVISO"]:
            resultado = f'<font color="{ESTADO["AVISO"][0]}"><b>Con avisos</b></font>'
        else:
            resultado = f'<font color="{ESTADO["OK"][0]}"><b>En orden</b></font>'
        filas.append([Paragraph(f'<a href="#sec{sec}" color="{NEGRO}">{sec}. {_esc(nombre)}</a>', est["base"]),
                      num(len(lista)), num(cuenta["OK"] + cuenta["INFO"]),
                      num(cuenta["AVISO"], "AVISO"), num(cuenta["FALLA"], "FALLA"),
                      Paragraph(resultado, est["base"])])
    el += [KeepTogether([_seccion(2, "Resumen por sección", est), Spacer(1, 8),
                         _tabla(filas, [6.6 * cm, 1.9 * cm, 2.0 * cm, 1.6 * cm, 1.6 * cm, None], est,
                                encabezado=["Sección", "Candados", "Aprobados", "Avisos", "Fallas", "Resultado"]),
                         Spacer(1, 3),
                         Paragraph("Haz clic en una sección para ir a su detalle.", est["chico"])]),
           Spacer(1, 18)]

    # --- 3. Observaciones -----------------------------------------------------
    obs = [c for c in candados if c.estado in ("FALLA", "AVISO")]
    obs.sort(key=lambda c: (c.estado != "FALLA", c.seccion))
    el += [_seccion(3, "Observaciones", est), Spacer(1, 8)]
    if obs:
        filas = [[Paragraph(str(i), est["chico"]), Paragraph(_esc(c.clave), est["chico"]),
                  _estado(c.estado, est),
                  [Paragraph(f"<b>{_esc(c.titulo)}</b>", est["base"]), Paragraph(_esc(c.detalle), est["base"])]]
                 for i, c in enumerate(obs, 1)]
        el.append(_tabla(filas, [0.7 * cm, 1.3 * cm, 1.6 * cm, None], est,
                         encabezado=["#", "Clave", "Estado", "Hallazgo"]))
    else:
        el.append(Paragraph(f'<font color="{ESTADO["OK"][0]}"><b>Sin observaciones:</b></font> '
                            'todos los candados pasaron.', est["base"]))
    el.append(Spacer(1, 18))

    # --- 4. Validación en el SAT ------------------------------------------------
    sat = [CondPageBreak(6.5 * cm), _seccion(4, "Validación en el portal del SAT", est), Spacer(1, 6),
           Paragraph("Escanea cada QR con el celular o abre su link y compara lo que muestra el SAT contra "
                     "el documento.", est["chico"]), Spacer(1, 8)]
    celdas = []
    for i, url in enumerate(analisis.urls_qr[:2], 1):
        oficial = url.startswith("https://siat.sat.gob.mx/")
        que = ("nombre, RFC, CURP, situación, régimen y domicilio" if i == 1 else "fecha y RFC de la cadena original")
        if oficial:
            cuerpo = [Paragraph(f"<b>QR {i} · {'cédula' if i == 1 else 'sello'}</b>", est["base"]), Spacer(1, 2),
                      Paragraph(f"Compara: {que}.", est["chico"]), Spacer(1, 5),
                      Paragraph(f'<a href="{_esc(url)}" color="{NEGRO}"><u>Abrir en siat.sat.gob.mx</u></a>',
                                est["base"])]
            interior = Table([[_qr_imagen(url) or "", cuerpo]], colWidths=[2.8 * cm, None])
            interior.setStyle(_sin_relleno([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            borde = NEGRO
        else:
            rojo = ESTADO["FALLA"][0]
            interior = [Paragraph(f'<font color="{rojo}"><b>QR {i}: página NO oficial</b></font>', est["base"]),
                        Spacer(1, 2),
                        Paragraph("Lleva a una página que no es del SAT. No la abras ni la uses para validar:",
                                  est["chico"]),
                        Paragraph(f'<font color="{rojo}">{_esc(url[:90])}</font>', est["chico"])]
            borde = rojo
        caja_qr = Table([[interior]], colWidths=[(ANCHO - 12) / 2])
        caja_qr.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(borde)),
                                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                     ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        celdas.append(caja_qr)
    if celdas:
        fila = Table([celdas + ([""] if len(celdas) == 1 else [])],
                     colWidths=[(ANCHO - 12) / 2 + 12, (ANCHO - 12) / 2])
        fila.setStyle(_sin_relleno())
        sat.append(fila)
    else:
        sat.append(Paragraph("No se leyó ningún QR del documento.", est["base"]))
    el += [KeepTogether(sat), Spacer(1, 20)]

    # --- 5. Detalle de los candados ------------------------------------------
    el += [CondPageBreak(8 * cm), _seccion(5, "Detalle de los candados", est), Spacer(1, 4),
           Paragraph("OK: se cumple · AVISO: revisar a mano · FALLA: indicio de alteración · INFO: dato "
                     "informativo.", est["chico"]), Spacer(1, 6)]
    for sec, nombre in SECCIONES.items():
        lista = [c for c in candados if c.seccion == sec]
        if not lista:
            continue
        filas, tintes = [], []
        for i, c in enumerate(lista):
            det = _esc(c.detalle)
            if c.previene:
                det += f'<br/><font color="{GRIS_CLARO}" size="7">Previene: {_esc(c.previene)}</font>'
            filas.append([Paragraph(_esc(c.clave), est["chico"]), Paragraph(f"<b>{_esc(c.titulo)}</b>", est["base"]),
                          _estado(c.estado, est), Paragraph(det, est["base"])])
            if c.estado in ("FALLA", "AVISO"):
                tintes.append((i, ESTADO[c.estado][1]))
        titulo = Paragraph(f'<a name="sec{sec}"/>5.{sec}&nbsp;&nbsp;{_esc(nombre)}', est["h2"])
        titulo_t = Table([[titulo]], colWidths=[ANCHO])
        titulo_t.setStyle(_sin_relleno([("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        titulo_t._marcador = (f"5.{sec} {nombre}", f"sec{sec}")
        el += [CondPageBreak(3.5 * cm), titulo_t,
               _tabla(filas, [1.3 * cm, 4.3 * cm, 1.5 * cm, None], est,
                      encabezado=["Clave", "Candado", "Estado", "Hallazgo"], tintes=tintes),
               Spacer(1, 14)]

    el += [Spacer(1, 4),
           Paragraph("Este dictamen revisa candados técnicos del archivo y no sustituye la consulta al portal "
                     "del SAT. Huella SHA-256 del archivo revisado:", est["chico"]),
           Paragraph(f'<font name="Courier" size="7">{analisis.sha256}</font>', est["chico"])]

    # --- Membrete y pie --------------------------------------------------------
    def pagina(cv, doc):
        cv.saveState()
        an, al = letter
        y = al - 1.55 * cm
        cv.setFillColor(colors.HexColor(NEGRO))
        cv.setFont("Helvetica-Bold", 7.5)
        cv.drawString(MARGEN, y + 0.22 * cm, "VALIDACIÓN DE CONSTANCIA DE SITUACIÓN FISCAL")
        cv.setFont("Helvetica", 7.5)
        cv.setFillColor(colors.HexColor(GRIS))
        cv.drawRightString(an - MARGEN, y + 0.22 * cm,
                           " · ".join(x for x in (d.get("rfc"), f"Folio {folio}") if x))
        cv.setStrokeColor(colors.HexColor(NEGRO))
        cv.setLineWidth(1.4)
        cv.line(MARGEN, y, an - MARGEN, y)
        cv.setLineWidth(0.4)
        cv.line(MARGEN, y - 0.08 * cm, an - MARGEN, y - 0.08 * cm)
        # Pie
        cv.setStrokeColor(colors.HexColor(LINEA))
        cv.line(MARGEN, 1.5 * cm, an - MARGEN, 1.5 * cm)
        cv.setFont("Helvetica", 7)
        cv.setFillColor(colors.HexColor(GRIS))
        cv.drawString(MARGEN, 1.15 * cm, "Análisis automático · no sustituye la consulta al portal del SAT")
        cv.restoreState()

    doc = _Documento(ruta_salida, pagina, title=f"Validación CSF {d.get('rfc', '')}", subject=ver,
                     creator="Reportes y Herramientas")
    doc.build([NextPageTemplate("pagina")] + el, canvasmaker=_CanvasNumerado)
    return ruta_salida
