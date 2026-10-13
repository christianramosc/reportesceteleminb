# -*- coding: utf-8 -*-
"""FICHA DE UNA PÁGINA (imagen PNG para WhatsApp o correo) — diseño 2

El PDF tiene 6 a 10 páginas: está bien para quien quiere el detalle, pero
la gerencia casi nunca lo abre en el teléfono. La ficha resume el reporte en
una sola imagen vertical, pensada para leerse en el celular:

    encabezado     banda azul con el periodo y, en el avance, la "carretera"
                   del mes: un auto que avanza según el día de corte
    tarjeta héroe  anillo de conversión + financiadas y monto
    dos cifras     las que faltan de la portada del PDF (GAP, pendientes...)
    pictograma     un auto por solicitud, del color de su estatus
                   (comparativo: una fila de autos por mes)
    equipo         cada asesor con su avatar, sus solicitudes y financiadas
    lo importante  hasta 3 puntos, con su icono, tomados de los focos y
                   conclusiones que ya escribe el reporte

Las cifras salen de los mismos módulos que el PDF (lateral.py,
conclusiones.py, estatus.py), así que la ficha y el reporte siempre dicen lo
mismo. Los iconos son los de Lucide que ya usa el PDF (iconos_mpl.py).

El ancho es fijo (1080 px, lo que WhatsApp muestra sin recomprimir de más) y
el alto se calcula según el contenido, para que nunca se corte.
"""

import html
import math
import re
import textwrap
from datetime import date

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

ANCHO_IN = 6.0             # 6 in × 180 dpi = 1080 px
DPI = 180
MARGEN = 0.32
ANCHO_UTIL = ANCHO_IN - 2 * MARGEN
PAD = 0.24                 # relleno interior de las tarjetas
SEP = 0.20                 # separación entre tarjetas

MAX_VINETAS = 3
MAX_VENDEDORES = 7


# =======================================================================
# Lienzo: coordenadas en pulgadas, medidas desde ARRIBA (y crece hacia abajo)
# =======================================================================
class _Lienzo:
    def __init__(self, alto):
        self.alto = alto
        self.fig = plt.figure(figsize=(ANCHO_IN, alto), dpi=DPI)
        self.fig.patch.set_facecolor(FONDO)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, ANCHO_IN)
        self.ax.set_ylim(alto, 0)
        self.ax.axis("off")

    def texto(self, x, y, s, tam=10, color=TINTA, peso="normal", ha="left", va="top", z=6, **kw):
        # parse_math=False: con dos "$" en el texto matplotlib lo toma como
        # fórmula ("$544,987 ... $272,493" salía en cursiva y sin signos).
        return self.ax.text(x, y, s, fontsize=tam, color=color, fontweight=peso, ha=ha, va=va,
                            family=FUENTE, zorder=z, parse_math=False, **kw)

    def rect(self, x, y, w, h, color, redondeo=0.0, z=2, alpha=1.0):
        if redondeo:
            p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={redondeo}",
                               fc=color, ec="none", zorder=z, alpha=alpha)
        else:
            p = Rectangle((x, y), w, h, fc=color, ec="none", zorder=z, alpha=alpha)
        self.ax.add_patch(p)

    def tarjeta(self, y, h, x=MARGEN, w=ANCHO_UTIL):
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
    # carrocería
    ax.add_patch(FancyBboxPatch(P(0.03, 0.20), 0.94 * w, 0.17 * w,
                                boxstyle=f"round,pad=0,rounding_size={0.07 * w}",
                                fc=color, ec="none", zorder=z))
    # cabina
    ax.add_patch(Polygon([P(0.20, 0.215), P(0.33, 0.06), P(0.64, 0.06), P(0.80, 0.215)],
                         closed=True, fc=color, ec=color, lw=0.6, joinstyle="round", zorder=z))
    # ventanas
    ax.add_patch(Polygon([P(0.28, 0.20), P(0.37, 0.10), P(0.48, 0.10), P(0.48, 0.20)],
                         closed=True, fc="white", ec="none", alpha=0.55, zorder=z + 0.1))
    ax.add_patch(Polygon([P(0.52, 0.20), P(0.52, 0.10), P(0.62, 0.10), P(0.71, 0.20)],
                         closed=True, fc="white", ec="none", alpha=0.55, zorder=z + 0.1))
    # llantas
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


def _icono_vineta(etiqueta):
    t = _h_normal(etiqueta or "")
    reglas = [(("gap",), "shield-check"), (("rechaz",), "trending-down"),
              (("conversion",), "trending-up"), (("volumen",), "chart-column"),
              (("cerrar", "dispersar", "pendiente", "abiert"), "hourglass"),
              (("fecha de corte", "corte"), "calendar-days"),
              (("vendedor", "equipo"), "users"), (("dato", "captura"), "clipboard-list")]
    for claves, nombre in reglas:
        if any(k in t for k in claves):
            return nombre
    return "triangle-alert"


def _h_normal(texto):
    import unicodedata
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _envolver(texto, ancho_in, tam):
    """Corta el texto según el ancho disponible (DejaVu ≈ 0.55 em por letra)."""
    por_linea = max(20, int(ancho_in / (tam / 72 * 0.56)))
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


def _monto_corto(v):
    return _lateral._monto_corto(v)


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


# =======================================================================
# Bloques (cada uno dibuja y devuelve su altura; con dibujar=False solo mide)
# =======================================================================
def _encabezado(lz, kicker, titulo, periodo, progreso, alto):
    ax = lz.ax
    lz.rect(0, 0, ANCHO_IN, alto, AZUL, z=0.5)
    # franjas diagonales y auto decorativo
    ax.add_patch(Polygon([(3.9, 0), (ANCHO_IN, 0), (ANCHO_IN, alto), (2.9, alto)],
                         fc=AZUL_2, ec="none", zorder=0.6))
    ax.add_patch(Polygon([(5.0, 0), (ANCHO_IN, 0), (ANCHO_IN, alto), (4.2, alto)],
                         fc=AZUL_3, ec="none", zorder=0.7))
    lz.icono("car", 3.55, -0.70, 2.75, "white", z=0.8, alpha=0.09, grosor=1.6)
    lz.rect(0, 0, ANCHO_IN, 0.07, ROJO, z=0.9)

    lz.texto(MARGEN, 0.30, kicker.upper(), tam=7.6, color="white", peso="bold", alpha=0.75)
    lz.texto(MARGEN, 0.52, titulo, tam=22, color="white", peso="bold")
    # chip con el periodo
    largo = 0.30 + len(periodo) * 9.5 / 72 * 0.56 + 0.18
    lz.rect(MARGEN, 1.08, largo, 0.36, "white", redondeo=0.18, z=3, alpha=0.14)
    lz.icono("calendar-days", MARGEN + 0.11, 1.16, 0.20, "white", z=7)
    lz.texto(MARGEN + 0.38, 1.26, periodo, tam=9.5, color="white", va="center")

    if progreso:
        dia, dias = progreso
        frac = min(max(dia / dias, 0), 1)
        y = 1.62
        lz.texto(MARGEN, y, f"Día {dia} de {dias}", tam=8.6, color="white", peso="bold")
        lz.texto(ANCHO_IN - MARGEN, y, f"quedan {dias - dia} días para el cierre", tam=8.6,
                 color="white", ha="right", alpha=0.8)
        yb = y + 0.42
        ancho = ANCHO_UTIL - 0.40
        lz.rect(MARGEN, yb, ancho, 0.10, "white", redondeo=0.05, z=3, alpha=0.18)
        lz.rect(MARGEN, yb, max(ancho * frac, 0.10), 0.10, ROJO, redondeo=0.05, z=3.5)
        # el auto avanza con el mes
        w = 0.46
        xa = MARGEN + ancho * frac - w * 0.75
        xa = min(max(xa, MARGEN - 0.05), ANCHO_IN - MARGEN - w)
        _auto(lz, xa, yb - w * 0.47, w, "white", z=5)
        # meta al final del camino
        lz.icono("circle-check", ANCHO_IN - MARGEN - 0.26, yb - 0.08, 0.26, "white", z=6, alpha=0.9)
    return alto


def _heroe(lz, y, conv_pct, fin, total, linea_monto, subtitulo, dibujar=True):
    h = 1.80
    if not dibujar:
        return h
    lz.tarjeta(y, h)
    cx, cy, r = MARGEN + PAD + 0.70, y + h / 2, 0.68
    lz.ax.add_patch(Wedge((cx, cy), r, 0, 360, width=0.16, fc=PISTA, ec="none", zorder=4))
    if conv_pct > 0:
        lz.ax.add_patch(Wedge((cx, cy), r, -90, -90 + 360 * min(conv_pct, 100) / 100, width=0.16,
                              fc=VINO, ec="none", zorder=5))
    lz.texto(cx, cy - 0.04, f"{conv_pct:.0f}%", tam=21, color=AZUL, peso="bold", ha="center",
             va="center")
    lz.texto(cx, cy + 0.27, "conversión", tam=7.6, color=TINTA_SEC, ha="center", va="center")

    x = cx + r + 0.35
    lz.texto(x, y + 0.26, f"{fin} de {total}", tam=24, color=TINTA, peso="bold")
    lz.texto(x, y + 0.70, subtitulo, tam=9.6, color=TINTA_SEC)
    if linea_monto:
        principal, secundaria = linea_monto
        lz.insignia("banknote", x + 0.19, y + 1.33, 0.19)
        lz.texto(x + 0.48, y + 1.12, principal, tam=11, color=TINTA, peso="bold")
        lz.texto(x + 0.48, y + 1.37, secundaria, tam=8.4, color=TINTA_SEC)
    return h


def _tarjetas(lz, y, cifras, dibujar=True):
    if not cifras:
        return 0
    h = 1.18
    if not dibujar:
        return h
    n = len(cifras)
    w = (ANCHO_UTIL - SEP * (n - 1)) / n
    for i, c in enumerate(cifras):
        x = MARGEN + i * (w + SEP)
        lz.tarjeta(y, h, x=x, w=w)
        alerta = c.get("alerta")
        nombre = _iconos_pdf.nombre_cifra(c["etiqueta"], alerta)
        lz.insignia(nombre, x + w - PAD - 0.24, y + PAD + 0.26, 0.24,
                    color=ROJO if alerta else AZUL, fondo=TINTE_ROJO if alerta else TINTE_AZUL)
        lz.texto(x + PAD, y + PAD + 0.02, c["etiqueta"], tam=6.9,
                 color=ROJO if alerta else TINTA_SEC, peso="bold")
        lz.texto(x + PAD, y + 0.44, c["valor"], tam=19, color=ROJO if alerta else AZUL, peso="bold")
        if alerta:
            # La alerta va en una etiqueta junto al valor (no solo en el color),
            # para no alargar el título y que no choque con el icono.
            t = lz.texto(x + PAD, y + 0.44, c["valor"], tam=19, color="none", peso="bold")
            caja = t.get_window_extent(renderer=lz.fig.canvas.get_renderer())
            xa = x + PAD + caja.width / DPI + 0.14       # ancho real del valor
            lz.rect(xa, y + 0.49, 0.64, 0.24, ROJO, redondeo=0.12, z=4)
            lz.texto(xa + 0.32, y + 0.61, "ALERTA", tam=6.6, color="white", peso="bold",
                     ha="center", va="center")
        lz.texto(x + PAD, y + 0.92, c.get("nota", ""), tam=7.4, color=TINTA_SEC)
    return h


def _titulo_tarjeta(lz, x, y, icono, titulo, nota=None):
    lz.insignia(icono, x + 0.17, y + 0.17, 0.17)
    lz.texto(x + 0.44, y + 0.17, titulo, tam=11, color=TINTA, peso="bold", va="center")
    if nota:
        lz.texto(ANCHO_IN - MARGEN - PAD, y + 0.17, nota, tam=7.6, color=TINTA_SEC, ha="right",
                 va="center")


def _pictograma(lz, y, conteo, dibujar=True):
    """Un auto por solicitud, del color de su estatus, más la leyenda."""
    total = int(conteo.sum())
    unidad = max(1, math.ceil(total / 100))           # más de 100: cada auto vale más
    autos = []
    for clave, n in conteo.items():
        autos += [clave] * math.ceil(int(n) / unidad)
    # Pocos autos se dibujan más grandes; muchos, más chicos.
    por_fila = 8 if len(autos) <= 16 else (10 if len(autos) <= 50 else 15)
    w = (ANCHO_UTIL - 2 * PAD) / por_fila
    w_auto = w * 0.86
    filas = math.ceil(len(autos) / por_fila)
    alto_autos = filas * w * 0.62
    # leyenda en dos columnas
    n_ley = len(conteo)
    alto_ley = math.ceil(n_ley / 2) * 0.30
    h = 0.62 + alto_autos + 0.18 + alto_ley + PAD - 0.12
    if not dibujar:
        return h
    lz.tarjeta(y, h)
    nota = f"cada auto = {unidad} solicitudes" if unidad > 1 else f"{total} solicitudes"
    _titulo_tarjeta(lz, MARGEN + PAD, y + PAD - 0.04, "car", "Cada auto es una solicitud", nota)
    y0 = y + 0.62
    for k, clave in enumerate(autos):
        f, c = divmod(k, por_fila)
        _auto(lz, MARGEN + PAD + c * w + (w - w_auto) / 2, y0 + f * w * 0.62, w_auto, _est.color(clave))
    yl = y0 + alto_autos + 0.18
    col_w = (ANCHO_UTIL - 2 * PAD) / 2
    for k, (clave, n) in enumerate(conteo.items()):
        f, c = divmod(k, 2)
        xl, yy = MARGEN + PAD + c * col_w, yl + f * 0.30
        lz.rect(xl, yy + 0.02, 0.16, 0.16, _est.color(clave), redondeo=0.04, z=4)
        lz.texto(xl + 0.26, yy + 0.10, _etq_leyenda(clave), tam=8.8, color=TINTA,
                 va="center")
        lz.texto(xl + col_w - 0.15, yy + 0.10, f"{int(n)}  ·  {n / total * 100:.0f}%", tam=8.8,
                 color=TINTA, peso="bold", ha="right", va="center")
    return h


def _pictograma_meses(lz, y, tabla_comp, dibujar=True):
    """Comparativo: una fila de autos por mes; los financiados en vino."""
    meses = list(tabla_comp.index)
    totales = tabla_comp["Total"].astype(int).tolist()
    fins = tabla_comp["Financiado"].astype(int).tolist()
    col_mes, col_pct = 0.75, 0.70
    disponible = ANCHO_UTIL - 2 * PAD - col_mes - col_pct
    unidad = max(1, math.ceil(max(totales + [1]) / 40))
    w = min(0.30, disponible / 14)
    por_fila = max(1, int(disponible / w))
    filas_mes = [max(1, math.ceil(math.ceil(t / unidad) / por_fila)) for t in totales]
    alto_fila = w * 0.62
    alto = sum(f * alto_fila + 0.16 for f in filas_mes)
    h = 0.62 + alto + 0.38 + PAD - 0.10
    if not dibujar:
        return h
    lz.tarjeta(y, h)
    nota = f"cada auto = {unidad} solicitudes" if unidad > 1 else "cada auto = 1 solicitud"
    _titulo_tarjeta(lz, MARGEN + PAD, y + PAD - 0.04, "car", "Financiadas por mes", nota)
    yy = y + 0.62
    for mes, t, f, nf in zip(meses, totales, fins, filas_mes):
        etiqueta = str(mes).title()
        partes = etiqueta.split()
        corto = partes[0][:3] + (f" {partes[1][2:]}" if len(partes) > 1 and len(partes[1]) == 4 else "")
        lz.texto(MARGEN + PAD, yy + alto_fila * nf / 2, corto, tam=9, color=TINTA, peso="bold",
                 va="center")
        n_autos, n_fin = math.ceil(t / unidad), math.ceil(f / unidad)
        for k in range(n_autos):
            fr, cc = divmod(k, por_fila)
            _auto(lz, MARGEN + PAD + col_mes + cc * w + w * 0.07, yy + fr * alto_fila, w * 0.86,
                  VINO if k < n_fin else GRIS_AUTO)
        lz.texto(ANCHO_IN - MARGEN - PAD, yy + alto_fila * nf / 2 - 0.07,
                 f"{(f / t * 100 if t else 0):.1f}%", tam=10, color=TINTA, peso="bold", ha="right",
                 va="center")
        lz.texto(ANCHO_IN - MARGEN - PAD, yy + alto_fila * nf / 2 + 0.12, f"{f} de {t}", tam=7.4,
                 color=TINTA_SEC, ha="right", va="center")
        yy += nf * alto_fila + 0.16
    yl = yy + 0.08
    _auto(lz, MARGEN + PAD, yl, 0.30, VINO)
    lz.texto(MARGEN + PAD + 0.38, yl + 0.08, "Financiada", tam=8.4, color=TINTA_SEC, va="center")
    _auto(lz, MARGEN + PAD + 1.50, yl, 0.30, GRIS_AUTO)
    lz.texto(MARGEN + PAD + 1.88, yl + 0.08, "Resto de las solicitudes", tam=8.4, color=TINTA_SEC,
             va="center")
    return h


_COLORES_AVATAR = [AZUL, "#5B7FD6", "#2F6F8F", "#6B6FA8", "#C9A227", "#8FB3C9", "#4B5563"]


def _equipo(lz, y, filas, titulo="El equipo", dibujar=True):
    if not filas:
        return 0
    alto_fila = 0.50
    h = 0.62 + len(filas) * alto_fila + PAD - 0.06
    if not dibujar:
        return h
    lz.tarjeta(y, h)
    _titulo_tarjeta(lz, MARGEN + PAD, y + PAD - 0.04, "users", titulo, "financiadas / solicitudes")
    max_tot = max(f[1] for f in filas)
    mejor = filas[0] if filas[0][2] > 0 and (len(filas) == 1 or filas[0][2] > filas[1][2]) else None
    x_barra = MARGEN + PAD + 2.30
    ancho_barra = ANCHO_UTIL - 2 * PAD - 2.30 - 0.70
    for k, (nombre, tot, fin) in enumerate(filas):
        cy = y + 0.62 + k * alto_fila + alto_fila / 2 - 0.04
        cx = MARGEN + PAD + 0.19
        lz.circulo(cx, cy, 0.19, _COLORES_AVATAR[k % len(_COLORES_AVATAR)], z=4)
        lz.texto(cx, cy, _iniciales(nombre), tam=7.6, color="white", peso="bold", ha="center",
                 va="center")
        lz.texto(cx + 0.30, cy, _h.nombre_corto(nombre), tam=8.8, color=TINTA, va="center")
        if mejor and nombre == mejor[0]:
            lz.icono("award", cx + 0.30 + len(_h.nombre_corto(nombre)) * 8.8 / 72 * 0.56 + 0.08,
                     cy - 0.11, 0.22, "#C9A227", z=7)
        lz.rect(x_barra, cy - 0.07, ancho_barra, 0.14, PISTA, redondeo=0.07, z=3)
        w_tot = ancho_barra * tot / max_tot
        lz.rect(x_barra, cy - 0.07, w_tot, 0.14, "#B8C2DA", redondeo=0.07, z=3.2)
        if fin:
            lz.rect(x_barra, cy - 0.07, max(ancho_barra * fin / max_tot, 0.14), 0.14, VINO,
                    redondeo=0.07, z=3.4)
        lz.texto(ANCHO_IN - MARGEN - PAD, cy, f"{fin} / {tot}", tam=9.2, color=TINTA, peso="bold",
                 ha="right", va="center")
    return h


def _importante(lz, y, vinetas, dibujar=True):
    if not vinetas:
        return 0
    ancho_texto = ANCHO_UTIL - 2 * PAD - 0.62
    bloques = [(e, c, _envolver(c, ancho_texto, 8.8)) for e, c in vinetas]
    alto_b = [(0.22 if e else 0) + len(l) * 0.185 + 0.20 for e, _, l in bloques]
    h = 0.62 + sum(alto_b) + PAD - 0.20
    if not dibujar:
        return h
    lz.tarjeta(y, h)
    _titulo_tarjeta(lz, MARGEN + PAD, y + PAD - 0.04, "list-checks", "Lo más importante")
    yy = y + 0.66
    for (etiqueta, _, lineas), alto in zip(bloques, alto_b):
        nombre = _icono_vineta(etiqueta)
        es_alerta = nombre in ("triangle-alert", "hourglass", "trending-down")
        lz.insignia(nombre, MARGEN + PAD + 0.20, yy + 0.18, 0.20,
                    color=ROJO if es_alerta else AZUL, fondo=TINTE_ROJO if es_alerta else TINTE_AZUL)
        x = MARGEN + PAD + 0.62
        ty = yy
        if etiqueta:
            lz.texto(x, ty, etiqueta.upper(), tam=7.4, color=ROJO if es_alerta else AZUL, peso="bold")
            ty += 0.22
        for linea in lineas:
            lz.texto(x, ty, linea, tam=8.8, color=TINTA)
            ty += 0.185
        yy += alto
    return h


def _pie(lz, y, analista):
    lz.rect(0, y, ANCHO_IN, 0.55, AZUL, z=1)
    lz.texto(MARGEN, y + 0.275, f"Elaborado por {analista}  ·  {date.today():%d/%m/%Y}", tam=7.6,
             color="white", va="center", alpha=0.85)
    lz.texto(ANCHO_IN - MARGEN, y + 0.275, "Detalle completo en el reporte PDF", tam=7.6,
             color="white", va="center", ha="right", alpha=0.85)
    return 0.55


# =======================================================================
# Composición
# =======================================================================
def _componer(ruta, encabezado, heroe, cifras, bloque_central, equipo, vinetas, analista):
    """encabezado: dict(kicker, titulo, periodo, progreso).
    bloque_central: función (lz, y, dibujar) -> alto."""
    alto_enc = 2.55 if encabezado.get("progreso") else 1.80
    solape = 0.30                     # la tarjeta héroe se monta sobre la banda azul
    bloques = [
        lambda lz, y, d: _heroe(lz, y, dibujar=d, **heroe),
        lambda lz, y, d: _tarjetas(lz, y, cifras, dibujar=d),
        bloque_central,
        lambda lz, y, d: _equipo(lz, y, equipo, dibujar=d),
        lambda lz, y, d: _importante(lz, y, vinetas[:MAX_VINETAS], dibujar=d),
    ]
    alturas = [b(None, 0, False) for b in bloques]
    alto = alto_enc - solape + sum(a + SEP for a in alturas if a) + 0.08 + 0.55
    lz = _Lienzo(alto)
    _encabezado(lz, alto=alto_enc, **encabezado)
    y = alto_enc - solape
    for b, a in zip(bloques, alturas):
        if a:
            b(lz, y, True)
            y += a + SEP
    _pie(lz, alto - 0.55, analista)
    return lz.guardar(ruta)


def _cifras_sin(cifras, quitar):
    # Comparación exacta: "CONVERSIÓN" no debe llevarse "MENOR CONVERSIÓN".
    return [c for c in cifras if c["etiqueta"] not in quitar]


# =======================================================================
# Fichas
# =======================================================================
def ficha_mensual(df, ruta_png, modo="cierre", periodo="", pdv="", analista="",
                  resumen=None, ctx=None, hoja=None):
    """Ficha del Resumen Mensual (modo="cierre") o del Avance Preliminar
    (modo="avance"). df es la bitácora ya limpia (con columna Categoria)."""
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

    linea_monto = None
    if cifra_monto:
        linea_monto = (f"{cifra_monto['valor']} financiado", cifra_monto["nota"])

    focos, conclusiones = _c.focos_y_conclusiones_mensual(df, modo, resumen=resumen,
                                                          ctx=ctx, hoja=hoja)
    conteo = _conteo_estatus(df)
    return _componer(
        ruta_png,
        encabezado=dict(kicker=f"Autoexpress Inbursa  ·  {pdv}", titulo=titulo, periodo=periodo,
                        progreso=progreso),
        heroe=dict(conv_pct=pct, fin=fin, total=total, linea_monto=linea_monto, subtitulo=subtitulo),
        cifras=cifras,
        bloque_central=lambda lz, y, d: _pictograma(lz, y, conteo, dibujar=d),
        equipo=_tabla_vendedores(df),
        vinetas=[_vineta(t) for t in focos + conclusiones],
        analista=analista,
    )


def ficha_comparativo(df_unico, tabla_comp, orden_meses, df_combinado, ruta_png,
                      pdv="", analista=""):
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
        ruta_png,
        encabezado=dict(kicker=f"Autoexpress Inbursa  ·  {pdv}", titulo="Comparativo mensual",
                        periodo=periodo, progreso=None),
        heroe=dict(conv_pct=pct, fin=fin, total=total,
                   linea_monto=(f"{monto['valor']} financiado", monto["nota"]) if monto else None,
                   subtitulo=f"solicitudes financiadas en {n} meses"),
        cifras=cifras,
        bloque_central=lambda lz, y, d: _pictograma_meses(lz, y, tabla_comp, dibujar=d),
        equipo=_tabla_vendedores(df_unico),
        vinetas=[_vineta(t) for t in lectura],
        analista=analista,
    )


def generar_ficha_segura(funcion, *args, **kwargs):
    """La ficha es un extra: si algo falla al dibujarla, se avisa en el
    detalle del proceso y el reporte principal se entrega igual."""
    try:
        return funcion(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        print(f"  Aviso: no se pudo generar la ficha de una página ({e}).")
        plt.close("all")
        return None
