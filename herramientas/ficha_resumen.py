# -*- coding: utf-8 -*-
"""FICHA DE UNA PÁGINA (imagen PNG) — para WhatsApp y para correo

El PDF tiene 6 a 10 páginas: está bien para quien quiere el detalle, pero
la gerencia casi nunca lo abre. La ficha resume el reporte en una sola
imagen, en dos formatos:

  WhatsApp  1080 px de ancho, una sola columna: se lee en el celular
            deslizando hacia abajo.
  Correo    1200 px de ancho, en dos columnas y menos alta: se pega en el
            cuerpo del mensaje y se lee completa en la pantalla de la
            computadora. El PNG lleva 180 ppp, así que Outlook y Word la
            muestran a unos 670 px, el ancho normal de un correo.

Ambas tienen los mismos bloques:

    encabezado     banda azul con el periodo y, en el avance, la "carretera"
                   del mes: un auto que avanza según el día de corte
    tarjeta héroe  anillo de conversión + financiadas y monto
    cifras         las que faltan de la portada del PDF (GAP, pendientes...)
    pictograma     un auto por solicitud, del color de su estatus
                   (comparativo: una fila de autos por mes)
    equipo         cada asesor con su avatar, sus solicitudes y financiadas
    lo importante  hasta 3 puntos, con su icono, tomados de los focos y
                   conclusiones que ya escribe el reporte

Las cifras salen de los mismos módulos que el PDF (lateral.py,
conclusiones.py, estatus.py), así que la ficha y el reporte siempre dicen lo
mismo. Los iconos son los de Lucide que ya usa el PDF (iconos_mpl.py).

Cada bloque recibe su posición y su ancho, así que el mismo código arma
la columna única de WhatsApp y las dos columnas del correo. El alto de la
imagen se calcula según el contenido, para que nunca se corte.
"""

import html
import math
import re
import textwrap
import unicodedata
from datetime import date
try:
    from . import fechas as _fechas   # hora de México, no la del servidor
except ImportError:  # ejecución suelta (Colab)
    import fechas as _fechas

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle, Wedge

try:
    from . import conclusiones as _c
    from . import estatus as _est
    from . import hallazgos as _h
    from . import iconos as _iconos_pdf      # reglas para elegir icono por etiqueta
    from . import lateral as _lateral
    from .iconos_mpl import dibujar_icono
except ImportError:  # ejecución suelta (Colab)
    import conclusiones as _c
    import estatus as _est
    import hallazgos as _h
    import iconos as _iconos_pdf
    import lateral as _lateral
    from iconos_mpl import dibujar_icono


# =======================================================================
# Estilo — para cambiar el look, normalmente basta con tocar este bloque
# =======================================================================
# DejaVu Sans viene con matplotlib: se ve igual en Colab, en tu máquina y en
# Streamlit Cloud (una fuente que no esté instalada cambiaría el acomodo).
FUENTE = "DejaVu Sans"

AZUL = "#191970"           # azul Inbursa
AZUL_2 = "#24247F"         # franjas decorativas del encabezado
AZUL_3 = "#2E2E8F"
ROJO = "#E4002B"           # rojo MG (alertas, progreso del mes)
VINO = "#7A0019"           # financiado
TINTA = "#1F2937"
TINTA_SEC = "#6B7280"
FONDO = "#EEF1F7"          # fondo de la página
TARJETA = "#FFFFFF"
SOMBRA = "#DCE1EC"
PISTA = "#E7EAF2"          # fondo del anillo y de las barras
TINTE_AZUL = "#E3E6F5"     # fondo de los iconos
TINTE_ROJO = "#FDE3E8"
GRIS_AUTO = "#CDD3DF"      # autos "resto" en el comparativo
LLANTA = "#1F2937"

DPI = 180
PAD = 0.24                 # relleno interior de las tarjetas
SEP = 0.20                 # separación entre tarjetas

# Formatos: ancho total y margen (pulgadas). 6.0 in × 180 ppp = 1080 px.
FORMATOS = {
    "whatsapp": {"ancho": 6.0, "margen": 0.32},
    "correo": {"ancho": 6.67, "margen": 0.30},
}

MAX_VINETAS = 3
MAX_VENDEDORES = 7

_COLORES_AVATAR = [AZUL, "#5B7FD6", "#2F6F8F", "#6B6FA8", "#C9A227", "#8FB3C9", "#4B5563"]


# =======================================================================
# Lienzo: coordenadas en pulgadas, medidas desde ARRIBA (y crece hacia abajo)
# =======================================================================
class _Lienzo:
    def __init__(self, ancho, alto):
        self.ancho, self.alto = ancho, alto
        self.fig = plt.figure(figsize=(ancho, alto), dpi=DPI)
        self.fig.patch.set_facecolor(FONDO)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, ancho)
        self.ax.set_ylim(alto, 0)
        self.ax.axis("off")

    def texto(self, x, y, s, tam=10, color=TINTA, peso="normal", ha="left", va="top", z=6, **kw):
        # parse_math=False: con dos "$" en el texto matplotlib lo toma como
        # fórmula ("$544,987 ... $272,493" salía en cursiva y sin signos).
        return self.ax.text(x, y, s, fontsize=tam, color=color, fontweight=peso, ha=ha, va=va,
                            family=FUENTE, zorder=z, parse_math=False, **kw)

    def ancho_texto(self, s, tam, peso="normal"):
        """Ancho real (pulgadas) que ocupará un texto."""
        t = self.texto(0, 0, s, tam=tam, peso=peso, color="none")
        w = t.get_window_extent(renderer=self.fig.canvas.get_renderer()).width / DPI
        t.remove()
        return w

    def rect(self, x, y, w, h, color, redondeo=0.0, z=2, alpha=1.0):
        if redondeo:
            p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={redondeo}",
                               fc=color, ec="none", zorder=z, alpha=alpha)
        else:
            p = Rectangle((x, y), w, h, fc=color, ec="none", zorder=z, alpha=alpha)
        self.ax.add_patch(p)

    def tarjeta(self, x, y, w, h):
        self.rect(x + 0.015, y + 0.035, w, h, SOMBRA, redondeo=0.13, z=1)
        self.rect(x, y, w, h, TARJETA, redondeo=0.13, z=2)

    def circulo(self, cx, cy, r, color, z=4, alpha=1.0):
        self.ax.add_patch(Circle((cx, cy), r, fc=color, ec="none", zorder=z, alpha=alpha))

    def icono(self, nombre, x, y, tam, color, z=7, alpha=1.0, grosor=2.0):
        dibujar_icono(self.ax, nombre, x, y, tam, color, grosor=grosor, zorder=z, alpha=alpha)

    def insignia(self, nombre, cx, cy, r, color=AZUL, fondo=TINTE_AZUL):
        """Icono dentro de un círculo de color suave."""
        self.circulo(cx, cy, r, fondo, z=4)
        tam = r * 1.15
        self.icono(nombre, cx - tam / 2, cy - tam / 2, tam, color)

    def guardar(self, ruta):
        self.fig.savefig(ruta, dpi=DPI, facecolor=FONDO)
        plt.close(self.fig)
        return ruta


def _auto(lz, x, y, w, color, z=5):
    """Silueta de auto genérica (no es de ninguna marca), rellena.
    (x, y) = esquina superior izquierda; alto = 0.48 × ancho."""
    ax = lz.ax
    P = lambda u, v: (x + u * w, y + v * w)
    ax.add_patch(FancyBboxPatch(P(0.03, 0.20), 0.94 * w, 0.17 * w,
                                boxstyle=f"round,pad=0,rounding_size={0.07 * w}",
                                fc=color, ec="none", zorder=z))
    ax.add_patch(Polygon([P(0.20, 0.215), P(0.33, 0.06), P(0.64, 0.06), P(0.80, 0.215)],
                         closed=True, fc=color, ec=color, lw=0.6, joinstyle="round", zorder=z))
    ax.add_patch(Polygon([P(0.28, 0.20), P(0.37, 0.10), P(0.48, 0.10), P(0.48, 0.20)],
                         closed=True, fc="white", ec="none", alpha=0.55, zorder=z + 0.1))
    ax.add_patch(Polygon([P(0.52, 0.20), P(0.52, 0.10), P(0.62, 0.10), P(0.71, 0.20)],
                         closed=True, fc="white", ec="none", alpha=0.55, zorder=z + 0.1))
    for u in (0.27, 0.73):
        ax.add_patch(Circle(P(u, 0.385), 0.095 * w, fc=LLANTA, ec="white", lw=0.8, zorder=z + 0.2))
        ax.add_patch(Circle(P(u, 0.385), 0.035 * w, fc="#E5E7EB", ec="none", zorder=z + 0.3))


# =======================================================================
# Utilidades de datos y texto
# =======================================================================
def _vineta(texto_html):
    """'<b>GAP:</b> 2 de 4 ...' -> ('GAP', '2 de 4 ...')."""
    m = re.match(r"\s*<b>(.*?)</b>\s*(.*)", texto_html, flags=re.S)
    etiqueta, cuerpo = (m.group(1), m.group(2)) if m else (None, texto_html)
    limpiar = lambda t: html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()
    etiqueta = limpiar(etiqueta).rstrip(":").strip() if etiqueta else None
    cuerpo = limpiar(cuerpo)
    if cuerpo:
        cuerpo = cuerpo[0].upper() + cuerpo[1:]
    return etiqueta, cuerpo


def _h_normal(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _icono_vineta(etiqueta):
    t = _h_normal(etiqueta or "")
    reglas = [(("gap",), "shield-check"), (("rechaz", "enganche"), "trending-down"),
              (("conversion",), "trending-up"), (("volumen",), "chart-column"),
              (("cerrar", "dispersar", "pendiente", "abiert"), "hourglass"),
              (("fecha de corte", "corte"), "calendar-days"),
              (("vendedor", "equipo"), "users"), (("dato", "captura"), "clipboard-list")]
    for claves, nombre in reglas:
        if any(k in t for k in claves):
            return nombre
    return "triangle-alert"


def _envolver(texto, ancho_in, tam):
    """Corta el texto según el ancho disponible (DejaVu ≈ 0.56 em por letra)."""
    por_linea = max(18, int(ancho_in / (tam / 72 * 0.56)))
    return textwrap.wrap(texto, por_linea) or [""]


def _conteo_estatus(df):
    conteo = df["Categoria"].value_counts()
    orden = [c for c in _est.ORDEN_CATEGORIAS if c in conteo.index]
    orden += [c for c in conteo.index if c not in orden]
    _est.asignar_colores(df["Categoria"])
    return conteo.reindex(orden)


def _etq_leyenda(clave):
    """Nombre del estatus para la leyenda; los largos usan la versión corta
    del catálogo ("Documentación adicional" -> "Docum. adicional")."""
    nombre = _est.etiqueta(clave)
    if len(nombre) <= 18:
        return nombre
    corta = _est.etiqueta_corta(clave).replace("-<br/>", "").replace("<br/>", " ")
    return corta if len(corta) < len(nombre) else nombre[:17] + "…"


def _iniciales(nombre):
    p = str(nombre).split()
    if not p:
        return "?"
    segundo = p[-2] if len(p) >= 3 else (p[-1] if len(p) == 2 else "")
    return (p[0][0] + (segundo[:1] or "")).upper()


def _tabla_vendedores(df):
    col_v = "Nombre del Vendedor"
    if col_v not in df.columns or "Categoria" not in df.columns or df.empty:
        return []
    personas, _ = _h.solo_personas(df)
    if personas.empty:
        return []
    g = personas.groupby(col_v)["Categoria"]
    filas = [(v, int(len(s)), int((s == "FINANCIADO").sum())) for v, s in g]
    filas.sort(key=lambda f: (-f[2], -f[1], f[0]))
    return filas[:MAX_VENDEDORES]


def _cifras_sin(cifras, quitar):
    # Comparación exacta: "CONVERSIÓN" no debe llevarse "MENOR CONVERSIÓN".
    return [c for c in cifras if c["etiqueta"] not in quitar]


# =======================================================================
# Encabezado y pie (ocupan todo el ancho)
# =======================================================================
def _encabezado(lz, m, kicker, titulo, periodo, progreso, alto):
    ax, W = lz.ax, lz.ancho
    lz.rect(0, 0, W, alto, AZUL, z=0.5)
    ax.add_patch(Polygon([(W - 2.1, 0), (W, 0), (W, alto), (W - 3.1, alto)],
                         fc=AZUL_2, ec="none", zorder=0.6))
    ax.add_patch(Polygon([(W - 1.0, 0), (W, 0), (W, alto), (W - 1.8, alto)],
                         fc=AZUL_3, ec="none", zorder=0.7))
    lz.icono("car", W - 2.45, -0.70, 2.75, "white", z=0.8, alpha=0.09, grosor=1.6)
    lz.rect(0, 0, W, 0.07, ROJO, z=0.9)

    lz.texto(m, 0.30, kicker.upper(), tam=7.6, color="white", peso="bold", alpha=0.75)
    lz.texto(m, 0.52, titulo, tam=22, color="white", peso="bold")
    largo = 0.38 + lz.ancho_texto(periodo, 9.5) + 0.20
    lz.rect(m, 1.08, largo, 0.36, "white", redondeo=0.18, z=3, alpha=0.14)
    lz.icono("calendar-days", m + 0.11, 1.16, 0.20, "white", z=7)
    lz.texto(m + 0.38, 1.26, periodo, tam=9.5, color="white", va="center")

    if progreso:
        dia, dias = progreso
        frac = min(max(dia / dias, 0), 1)
        y = 1.62
        lz.texto(m, y, f"Día {dia} de {dias}", tam=8.6, color="white", peso="bold")
        lz.texto(W - m, y, f"quedan {dias - dia} días para el cierre", tam=8.6,
                 color="white", ha="right", alpha=0.8)
        yb = y + 0.42
        ancho = W - 2 * m - 0.40
        lz.rect(m, yb, ancho, 0.10, "white", redondeo=0.05, z=3, alpha=0.18)
        lz.rect(m, yb, max(ancho * frac, 0.10), 0.10, ROJO, redondeo=0.05, z=3.5)
        w = 0.46                                       # el auto avanza con el mes
        xa = min(max(m + ancho * frac - w * 0.75, m - 0.05), W - m - w)
        _auto(lz, xa, yb - w * 0.47, w, "white", z=5)
        lz.icono("circle-check", W - m - 0.26, yb - 0.08, 0.26, "white", z=6, alpha=0.9)
    return alto


def _pie(lz, m, y, analista):
    W = lz.ancho
    lz.rect(0, y, W, 0.55, AZUL, z=1)
    lz.texto(m, y + 0.275, f"Elaborado por {analista}  ·  {_fechas.hoy():%d/%m/%Y}", tam=7.6,
             color="white", va="center", alpha=0.85)
    lz.texto(W - m, y + 0.275, "Detalle completo en el reporte PDF", tam=7.6,
             color="white", va="center", ha="right", alpha=0.85)


# =======================================================================
# Bloques. Firma común: bloque(lz, x, y, w, h_min, dibujar) -> alto.
# Con dibujar=False solo calculan su alto (lz puede ser None). h_min estira
# la tarjeta para igualarla con la de al lado en el formato de correo.
# =======================================================================
def _titulo_tarjeta(lz, x, y, w, icono, titulo, nota=None):
    lz.insignia(icono, x + PAD + 0.17, y + PAD + 0.13, 0.17)
    lz.texto(x + PAD + 0.44, y + PAD + 0.13, titulo, tam=11, color=TINTA, peso="bold", va="center")
    if nota:
        lz.texto(x + w - PAD, y + PAD + 0.13, nota, tam=7.6, color=TINTA_SEC, ha="right",
                 va="center")


def _heroe(lz, x, y, w, h_min, dibujar, conv_pct, fin, total, linea_monto, subtitulo):
    compacto = w < 4.5
    r = 0.58 if compacto else 0.68
    texto_x = PAD + 2 * r + 0.28
    ancho_txt = w - texto_x - PAD
    tam_sub = 8.6 if compacto else 9.2
    sub = _envolver(subtitulo, ancho_txt, tam_sub)
    # alto del bloque de texto: cifra grande + subtítulo + renglón del monto
    bloque = 0.46 + 0.17 * len(sub) + (0.62 if linea_monto else 0)
    h = max(bloque + 2 * PAD + 0.10, 2 * r + 2 * PAD + 0.10, h_min)
    if not dibujar:
        return h
    lz.tarjeta(x, y, w, h)
    cx, cy = x + PAD + r, y + h / 2
    lz.ax.add_patch(Wedge((cx, cy), r, 0, 360, width=0.15, fc=PISTA, ec="none", zorder=4))
    if conv_pct > 0:
        lz.ax.add_patch(Wedge((cx, cy), r, -90, -90 + 360 * min(conv_pct, 100) / 100, width=0.15,
                              fc=VINO, ec="none", zorder=5))
    lz.texto(cx, cy - 0.04, f"{conv_pct:.0f}%", tam=16 if compacto else 21, color=AZUL, peso="bold",
             ha="center", va="center")
    lz.texto(cx, cy + (0.21 if compacto else 0.25), "conversión", tam=6.6 if compacto else 7.4,
             color=TINTA_SEC, ha="center", va="center")

    tx = x + texto_x
    y0 = y + (h - bloque) / 2                       # bloque de texto centrado
    lz.texto(tx, y0, f"{fin} de {total}", tam=22 if compacto else 24, color=TINTA, peso="bold")
    yy = y0 + 0.46
    for linea in sub:
        lz.texto(tx, yy, linea, tam=tam_sub, color=TINTA_SEC)
        yy += 0.17
    if linea_monto:
        principal, secundaria = linea_monto
        yy += 0.14
        r_i = 0.15 if compacto else 0.18
        sangria = 2 * r_i + 0.10
        lz.insignia("banknote", tx + r_i, yy + 0.20, r_i)
        lz.texto(tx + sangria, yy, principal, tam=9.4 if compacto else 10.5, color=TINTA, peso="bold")
        lz.texto(tx + sangria, yy + 0.24, secundaria, tam=7.8 if compacto else 8.2, color=TINTA_SEC)
    return h


def _cifra(lz, c, x, y, w, h, compacta):
    """Una tarjeta de cifra. Compacta = icono a la izquierda (correo)."""
    lz.tarjeta(x, y, w, h)
    alerta = c.get("alerta")
    color = ROJO if alerta else AZUL
    nombre = _iconos_pdf.nombre_cifra(c["etiqueta"], alerta)
    if compacta:
        # En la tarjeta angosta, la etiqueta ALERTA ocupa el lugar del icono.
        if not alerta:
            lz.insignia(nombre, x + w - PAD - 0.17, y + PAD + 0.15, 0.17, color=color,
                        fondo=TINTE_AZUL)
        tx, y0 = x + PAD, y + (h - 0.76) / 2          # bloque de 0.76 in centrado
        lz.texto(tx, y0, c["etiqueta"], tam=6.7, color=ROJO if alerta else TINTA_SEC, peso="bold")
        lz.texto(tx, y0 + 0.19, c["valor"], tam=16, color=color, peso="bold")
        valor_y, valor_tam = y0 + 0.19, 16
        lz.texto(tx, y0 + 0.62, c.get("nota", ""), tam=7.2, color=TINTA_SEC)
    else:
        lz.insignia(nombre, x + w - PAD - 0.24, y + PAD + 0.26, 0.24, color=color,
                    fondo=TINTE_ROJO if alerta else TINTE_AZUL)
        tx = x + PAD
        lz.texto(tx, y + PAD + 0.02, c["etiqueta"], tam=6.9, color=ROJO if alerta else TINTA_SEC,
                 peso="bold")
        lz.texto(tx, y + 0.44, c["valor"], tam=19, color=color, peso="bold")
        valor_y, valor_tam = y + 0.44, 19
        lz.texto(tx, y + 0.92, c.get("nota", ""), tam=7.4, color=TINTA_SEC)
    if alerta:
        # La alerta va en una etiqueta junto al valor (no solo en el color).
        xa = tx + lz.ancho_texto(c["valor"], valor_tam, "bold") + 0.12
        alto_p = 0.22
        yp = valor_y + valor_tam / 72 * 0.62 - alto_p / 2
        lz.rect(xa, yp, 0.60, alto_p, ROJO, redondeo=0.11, z=4)
        lz.texto(xa + 0.30, yp + alto_p / 2, "ALERTA", tam=6.3, color="white", peso="bold",
                 ha="center", va="center")


def _cifras(lz, x, y, w, h_min, dibujar, cifras, apiladas):
    if not cifras:
        return 0
    n = len(cifras)
    if apiladas:                       # correo: una sobre otra, junto al héroe
        h_una = 1.00
        h = max(n * h_una + (n - 1) * SEP, h_min)
        if dibujar:
            h_una = (h - (n - 1) * SEP) / n
            for i, c in enumerate(cifras):
                _cifra(lz, c, x, y + i * (h_una + SEP), w, h_una, compacta=True)
        return h
    h = max(1.18, h_min)               # WhatsApp: en fila
    if dibujar:
        wc = (w - SEP * (n - 1)) / n
        for i, c in enumerate(cifras):
            _cifra(lz, c, x + i * (wc + SEP), y, wc, h, compacta=False)
    return h


def _pictograma(lz, x, y, w, h_min, dibujar, conteo):
    """Un auto por solicitud, del color de su estatus, más la leyenda."""
    total = int(conteo.sum())
    unidad = max(1, math.ceil(total / 100))           # más de 100: cada auto vale más
    autos = []
    for clave, n in conteo.items():
        autos += [clave] * math.ceil(int(n) / unidad)
    interior = w - 2 * PAD
    base = 8 if len(autos) <= 16 else (10 if len(autos) <= 50 else 15)
    por_fila = max(6, round(base * interior / 4.88))  # 4.88 = interior en WhatsApp
    paso = interior / por_fila
    filas = math.ceil(len(autos) / por_fila)
    alto_autos = filas * paso * 0.62
    # Tantas columnas como quepan con el nombre más largo + "12  ·  45%".
    largo = max(len(_etq_leyenda(c)) for c in conteo.index) * 8.6 / 72 * 0.58 + 0.26 + 0.85
    columnas = max(1, min(3, int(interior // largo)))
    alto_ley = math.ceil(len(conteo) / columnas) * 0.30
    h = max(0.62 + alto_autos + 0.18 + alto_ley + PAD - 0.12, h_min)
    if not dibujar:
        return h
    lz.tarjeta(x, y, w, h)
    if w < 4.5:      # columna angosta (correo): título corto para que no choque con la nota
        titulo = f"Cada auto = {unidad} solicitudes" if unidad > 1 else "Cada auto = 1 solicitud"
        nota = None
    else:
        titulo = "Cada auto es una solicitud"
        nota = f"cada auto = {unidad} solicitudes" if unidad > 1 else f"{total} solicitudes"
    _titulo_tarjeta(lz, x, y - 0.04, w, "car", titulo, nota)
    y0 = y + 0.62
    for k, clave in enumerate(autos):
        f, c = divmod(k, por_fila)
        _auto(lz, x + PAD + c * paso + paso * 0.07, y0 + f * paso * 0.62, paso * 0.86,
              _est.color(clave))
    yl = y0 + alto_autos + 0.18
    col_w = interior / columnas
    for k, (clave, n) in enumerate(conteo.items()):
        f, c = divmod(k, columnas)
        xl, yy = x + PAD + c * col_w, yl + f * 0.30
        lz.rect(xl, yy + 0.02, 0.16, 0.16, _est.color(clave), redondeo=0.04, z=4)
        lz.texto(xl + 0.26, yy + 0.10, _etq_leyenda(clave), tam=8.6, color=TINTA, va="center")
        lz.texto(xl + col_w - 0.18, yy + 0.10, f"{int(n)}  ·  {n / total * 100:.0f}%", tam=8.6,
                 color=TINTA, peso="bold", ha="right", va="center")
    return h


def _pictograma_meses(lz, x, y, w, h_min, dibujar, tabla_comp):
    """Comparativo: una fila de autos por mes; los financiados en vino."""
    meses = list(tabla_comp.index)
    totales = tabla_comp["Total"].astype(int).tolist()
    fins = tabla_comp["Financiado"].astype(int).tolist()
    col_mes, col_pct = 0.75, 0.70
    disponible = w - 2 * PAD - col_mes - col_pct
    unidad = max(1, math.ceil(max(totales + [1]) / 40))
    paso = min(0.30, disponible / 14)
    por_fila = max(1, int(disponible / paso))
    filas_mes = [max(1, math.ceil(math.ceil(t / unidad) / por_fila)) for t in totales]
    alto_fila = paso * 0.62
    alto = sum(f * alto_fila + 0.16 for f in filas_mes)
    h = max(0.62 + alto + 0.38 + PAD - 0.10, h_min)
    if not dibujar:
        return h
    lz.tarjeta(x, y, w, h)
    nota = f"cada auto = {unidad} solicitudes" if unidad > 1 else "cada auto = 1 solicitud"
    _titulo_tarjeta(lz, x, y - 0.04, w, "car", "Financiadas por mes", nota)
    yy = y + 0.62
    for mes, t, f, nf in zip(meses, totales, fins, filas_mes):
        partes = str(mes).title().split()
        corto = partes[0][:3] + (f" {partes[1][2:]}" if len(partes) > 1 and len(partes[1]) == 4 else "")
        lz.texto(x + PAD, yy + alto_fila * nf / 2, corto, tam=9, color=TINTA, peso="bold", va="center")
        n_autos, n_fin = math.ceil(t / unidad), math.ceil(f / unidad)
        for k in range(n_autos):
            fr, cc = divmod(k, por_fila)
            _auto(lz, x + PAD + col_mes + cc * paso + paso * 0.07, yy + fr * alto_fila, paso * 0.86,
                  VINO if k < n_fin else GRIS_AUTO)
        lz.texto(x + w - PAD, yy + alto_fila * nf / 2 - 0.07, f"{(f / t * 100 if t else 0):.1f}%",
                 tam=10, color=TINTA, peso="bold", ha="right", va="center")
        lz.texto(x + w - PAD, yy + alto_fila * nf / 2 + 0.12, f"{f} de {t}", tam=7.4,
                 color=TINTA_SEC, ha="right", va="center")
        yy += nf * alto_fila + 0.16
    yl = yy + 0.08
    _auto(lz, x + PAD, yl, 0.30, VINO)
    lz.texto(x + PAD + 0.38, yl + 0.08, "Financiada", tam=8.4, color=TINTA_SEC, va="center")
    _auto(lz, x + PAD + 1.50, yl, 0.30, GRIS_AUTO)
    lz.texto(x + PAD + 1.88, yl + 0.08, "Resto de las solicitudes", tam=8.4, color=TINTA_SEC,
             va="center")
    return h


def _equipo(lz, x, y, w, h_min, dibujar, filas, titulo="El equipo"):
    if not filas:
        return 0
    angosto = w < 4.5                       # correo: barra debajo del nombre
    alto_fila = 0.52 if angosto else 0.50
    h = max(0.62 + len(filas) * alto_fila + PAD - 0.06, h_min)
    if not dibujar:
        return h
    lz.tarjeta(x, y, w, h)
    _titulo_tarjeta(lz, x, y - 0.04, w, "users", titulo,
                    "financiadas / solicitudes" if not angosto else "fin. / solic.")
    max_tot = max(f[1] for f in filas)
    mejor = filas[0] if filas[0][2] > 0 and (len(filas) == 1 or filas[0][2] > filas[1][2]) else None
    for k, (nombre, tot, fin) in enumerate(filas):
        cy = y + 0.62 + k * alto_fila + alto_fila / 2 - 0.04
        cx = x + PAD + 0.19
        lz.circulo(cx, cy, 0.19, _COLORES_AVATAR[k % len(_COLORES_AVATAR)], z=4)
        lz.texto(cx, cy, _iniciales(nombre), tam=7.6, color="white", peso="bold", ha="center",
                 va="center")
        corto = _h.nombre_corto(nombre)
        if angosto:
            ny, x_barra, by = cy - 0.10, cx + 0.30, cy + 0.10
            ancho_barra = x + w - PAD - 0.62 - x_barra
            alto_barra = 0.10
        else:
            ny, x_barra, by = cy, x + PAD + 2.30, cy
            ancho_barra = w - 2 * PAD - 2.30 - 0.70
            alto_barra = 0.14
        # Si el nombre no cabe antes de la cifra, se deja solo el primer nombre.
        limite = (x + w - PAD - 0.70) - (cx + 0.30) - (0.30 if mejor and nombre == mejor[0] else 0)
        if lz.ancho_texto(corto, 8.8) > limite:
            corto = corto.split()[0]
        lz.texto(cx + 0.30, ny, corto, tam=8.6 if angosto else 8.8, color=TINTA, va="center")
        if mejor and nombre == mejor[0]:
            lz.icono("award", cx + 0.30 + lz.ancho_texto(corto, 8.8) + 0.06, ny - 0.11, 0.22,
                     "#C9A227", z=7)
        lz.rect(x_barra, by - alto_barra / 2, ancho_barra, alto_barra, PISTA,
                redondeo=alto_barra / 2, z=3)
        lz.rect(x_barra, by - alto_barra / 2, ancho_barra * tot / max_tot, alto_barra, "#B8C2DA",
                redondeo=alto_barra / 2, z=3.2)
        if fin:
            lz.rect(x_barra, by - alto_barra / 2, max(ancho_barra * fin / max_tot, alto_barra),
                    alto_barra, VINO, redondeo=alto_barra / 2, z=3.4)
        lz.texto(x + w - PAD, cy, f"{fin} / {tot}", tam=9.2, color=TINTA, peso="bold",
                 ha="right", va="center")
    return h


def _importante(lz, x, y, w, h_min, dibujar, vinetas):
    if not vinetas:
        return 0
    ancho_texto = w - 2 * PAD - 0.62
    bloques = [(_envolver(e.upper(), ancho_texto, 7.6) if e else [], c, _envolver(c, ancho_texto, 8.6))
               for e, c in vinetas]
    alto_b = [len(e) * 0.19 + (0.03 if e else 0) + len(l) * 0.18 + 0.20 for e, _, l in bloques]
    h = max(0.62 + sum(alto_b) + PAD - 0.20, h_min)
    if not dibujar:
        return h
    lz.tarjeta(x, y, w, h)
    _titulo_tarjeta(lz, x, y - 0.04, w, "list-checks", "Lo más importante")
    yy = y + 0.66
    for (etiqueta, _, lineas), alto in zip(bloques, alto_b):
        nombre = _icono_vineta(" ".join(etiqueta))
        es_alerta = nombre in ("triangle-alert", "hourglass", "trending-down")
        lz.insignia(nombre, x + PAD + 0.20, yy + 0.18, 0.20,
                    color=ROJO if es_alerta else AZUL, fondo=TINTE_ROJO if es_alerta else TINTE_AZUL)
        tx, ty = x + PAD + 0.62, yy
        for renglon in etiqueta:
            lz.texto(tx, ty, renglon, tam=7.3, color=ROJO if es_alerta else AZUL, peso="bold")
            ty += 0.19
        if etiqueta:
            ty += 0.03
        for linea in lineas:
            lz.texto(tx, ty, linea, tam=8.6, color=TINTA)
            ty += 0.18
        yy += alto
    return h


# =======================================================================
# Composición
# =======================================================================
def _componer(ruta, formato, encabezado, heroe, cifras, central, equipo, vinetas, analista,
              central_ancho_completo=False):
    """Arma la ficha por filas. Cada fila es una lista de (bloque, fracción
    del ancho); los bloques de una misma fila se igualan en alto."""
    cfg = FORMATOS[formato]
    W, m = cfg["ancho"], cfg["margen"]
    util = W - 2 * m

    b_heroe = lambda lz, x, y, w, hm, d: _heroe(lz, x, y, w, hm, d, **heroe)
    b_equipo = lambda lz, x, y, w, hm, d: _equipo(lz, x, y, w, hm, d, equipo)
    b_imp = lambda lz, x, y, w, hm, d: _importante(lz, x, y, w, hm, d, vinetas[:MAX_VINETAS])
    if formato == "correo":
        b_cifras = lambda lz, x, y, w, hm, d: _cifras(lz, x, y, w, hm, d, cifras, apiladas=True)
        filas = [[(b_heroe, 0.64), (b_cifras, 0.36)]]
        if central_ancho_completo:          # comparativo: las filas de autos por mes
            filas += [[(central, 1.0)], [(b_equipo, 1.0)]]
        else:
            filas += [[(central, 0.55), (b_equipo, 0.45)]]
        filas += [[(b_imp, 1.0)]]
    else:
        b_cifras = lambda lz, x, y, w, hm, d: _cifras(lz, x, y, w, hm, d, cifras, apiladas=False)
        filas = [[(b_heroe, 1.0)], [(b_cifras, 1.0)], [(central, 1.0)], [(b_equipo, 1.0)],
                 [(b_imp, 1.0)]]

    def geometria(fila):
        activos = [(b, f) for b, f in fila if b(None, 0, 0, f * util, 0, False)]
        if not activos:
            return []
        if len(activos) == 1:                     # si falta su pareja, ocupa todo el ancho
            return [(activos[0][0], m, util)]
        libre = util - SEP * (len(activos) - 1)
        total_f = sum(f for _, f in activos)
        out, x = [], m
        for b, f in activos:
            w = libre * f / total_f
            out.append((b, x, w))
            x += w + SEP
        return out

    geo = [geometria(f) for f in filas]
    altos = [max((b(None, x, 0, w, 0, False) for b, x, w in g), default=0) for g in geo]

    alto_enc = 2.55 if encabezado.get("progreso") else 1.80
    solape = 0.30                     # la primera tarjeta se monta sobre la banda azul
    alto = alto_enc - solape + sum(a + SEP for a in altos if a) + 0.08 + 0.55
    lz = _Lienzo(W, alto)
    _encabezado(lz, m, alto=alto_enc, **encabezado)
    y = alto_enc - solape
    for g, a in zip(geo, altos):
        if not a:
            continue
        for b, x, w in g:
            b(lz, x, y, w, a, True)
        y += a + SEP
    _pie(lz, m, alto - 0.55, analista)
    return lz.guardar(ruta)


# =======================================================================
# Fichas
# =======================================================================
def ficha_mensual(df, ruta_png, modo="cierre", periodo="", pdv="", analista="",
                  resumen=None, ctx=None, hoja=None, formato="whatsapp"):
    """Ficha del Resumen Mensual (modo="cierre") o del Avance Preliminar
    (modo="avance"). df es la bitácora ya limpia (con columna Categoria).
    formato: "whatsapp" o "correo"."""
    fin, total, pct = _lateral._conversion(df)
    cifra_monto = _lateral._cifra_monto(df)

    progreso = None
    if modo == "avance":
        cifras = _lateral.cifras_avance(df, ctx=ctx, hoja=hoja)
        dias = next((c for c in cifras if c["etiqueta"] == "DÍAS RESTANTES"), None)
        if ctx and dias and not dias.get("alerta"):
            progreso = (ctx["dia_actual"], ctx["dias_en_mes"])
        quitar = ["SOLICITUDES", "FINANCIADAS"] + (["DÍAS RESTANTES"] if progreso else [])
        titulo, subtitulo = "Avance del mes", "solicitudes ya financiadas"
    else:
        cifras = _lateral.cifras_resumen(df)
        quitar = ["SOLICITUDES", "CONVERSIÓN", "MONTO FINANCIADO"]
        titulo, subtitulo = "Resumen del mes", "solicitudes financiadas"
    cifras = _cifras_sin(cifras, quitar)[:3]

    linea_monto = (f"{cifra_monto['valor']} financiado", cifra_monto["nota"]) if cifra_monto else None
    focos, conclusiones = _c.focos_y_conclusiones_mensual(df, modo, resumen=resumen,
                                                          ctx=ctx, hoja=hoja)
    conteo = _conteo_estatus(df)
    return _componer(
        ruta_png, formato,
        encabezado=dict(kicker=f"Autoexpress Inbursa  ·  {pdv}", titulo=titulo, periodo=periodo,
                        progreso=progreso),
        heroe=dict(conv_pct=pct, fin=fin, total=total, linea_monto=linea_monto, subtitulo=subtitulo),
        cifras=cifras,
        central=lambda lz, x, y, w, hm, d: _pictograma(lz, x, y, w, hm, d, conteo),
        equipo=_tabla_vendedores(df),
        vinetas=[_vineta(t) for t in focos + conclusiones],
        analista=analista,
    )


def ficha_comparativo(df_unico, tabla_comp, orden_meses, df_combinado, ruta_png,
                      pdv="", analista="", formato="whatsapp"):
    """Ficha del Comparativo Mensual. df_unico: un renglón por folio
    (folios.consolidar); df_combinado: todas las filas de todos los meses."""
    n = len(orden_meses)
    fin, total, pct = _lateral._conversion(df_unico)
    cifras = _lateral.cifras_comparativo(df_unico, tabla_comp, n)
    monto = next((c for c in cifras if c["etiqueta"] == "MONTO FINANCIADO"), None)
    cifras = _cifras_sin(cifras, ["SOLICITUDES", "CONVERSIÓN", "MONTO FINANCIADO"])[:3]
    lectura, _ = _c.lectura_y_conclusiones_comparativo(tabla_comp, orden_meses, df_combinado)
    meses = [str(m).title() for m in orden_meses]
    periodo = meses[0] if n == 1 else f"{meses[0]} a {meses[-1]}"
    return _componer(
        ruta_png, formato,
        encabezado=dict(kicker=f"Autoexpress Inbursa  ·  {pdv}", titulo="Comparativo mensual",
                        periodo=periodo, progreso=None),
        heroe=dict(conv_pct=pct, fin=fin, total=total,
                   linea_monto=(f"{monto['valor']} financiado", monto["nota"]) if monto else None,
                   subtitulo=f"solicitudes financiadas en {n} meses"),
        cifras=cifras,
        central=lambda lz, x, y, w, hm, d: _pictograma_meses(lz, x, y, w, hm, d, tabla_comp),
        equipo=_tabla_vendedores(df_unico),
        vinetas=[_vineta(t) for t in lectura],
        analista=analista,
        central_ancho_completo=True,
    )


def fichas_ambos_formatos(funcion, ruta_base, *args, **kwargs):
    """Genera la ficha de WhatsApp y la de correo. ruta_base sin extensión.
    Devuelve las rutas que sí se pudieron generar."""
    rutas = []
    for formato, sufijo in (("whatsapp", "WhatsApp"), ("correo", "Correo")):
        r = generar_ficha_segura(funcion, *args, ruta_png=f"{ruta_base}_{sufijo}.png",
                                 formato=formato, **kwargs)
        if r:
            rutas.append(r)
    return rutas


def generar_ficha_segura(funcion, *args, **kwargs):
    """La ficha es un extra: si algo falla al dibujarla, se avisa en el
    detalle del proceso y el reporte principal se entrega igual."""
    try:
        return funcion(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        print(f"  Aviso: no se pudo generar la ficha de una página ({e}).")
        plt.close("all")
        return None
