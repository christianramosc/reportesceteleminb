# -*- coding: utf-8 -*-
"""Dibuja los iconos de Lucide (carpeta iconos/) directamente en matplotlib.

iconos.py los convierte para ReportLab (PDF) con svglib. La ficha PNG se
dibuja con matplotlib, así que aquí se interpreta el SVG a mano: los iconos
de Lucide solo usan path, circle, rect y line, todos con trazo y sin
relleno, así que basta con un intérprete pequeño. No agrega dependencias.

Uso:
    dibujar_icono(ax, "car", x, y, tam, color, grosor=2)
donde (x, y) es la esquina superior izquierda en coordenadas del eje con la
y hacia ABAJO (como el lienzo de la ficha) y tam es el lado del cuadro.
"""

import math
import os
import re
import xml.etree.ElementTree as ET

import numpy as np
from matplotlib.patches import Circle, PathPatch
from matplotlib.path import Path

_CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iconos")
_CACHE = {}

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


# =======================================================================
# Interprete de "d"
# =======================================================================
def _tokens(d):
    """Comandos y números, respetando que en los arcos las banderas pueden
    venir pegadas ("a2 2 0 0022 17" = rx ry rot 0 0 22 17)."""
    salida = []
    i, n = 0, len(d)
    comando = None
    argn = 0
    while i < n:
        c = d[i]
        if c.isalpha():
            comando = c
            argn = 0
            salida.append(c)
            i += 1
            continue
        if c in " ,\n\t":
            i += 1
            continue
        # banderas de arco: un solo dígito 0/1
        if comando in ("a", "A") and argn % 7 in (3, 4) and c in "01":
            salida.append(float(c))
            argn += 1
            i += 1
            continue
        m = re.match(_NUM, d[i:])
        if not m:
            i += 1
            continue
        salida.append(float(m.group(0)))
        argn += 1
        i += len(m.group(0))
    return salida


def _arco_a_bezier(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """Arco elíptico SVG -> lista de curvas cúbicas [(c1, c2, p), ...]."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [((x1, y1), (x2, y2), (x2, y2))]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coef = math.sqrt(max(num / den, 0)) if den else 0
    if fa == fs:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    partes = max(1, int(math.ceil(abs(dt) / (math.pi / 2))))
    delta = dt / partes
    k = 4 / 3 * math.tan(delta / 4)
    curvas = []
    t = t1
    for _ in range(partes):
        c1, s1 = math.cos(t), math.sin(t)
        c2, s2 = math.cos(t + delta), math.sin(t + delta)
        p1 = (c1 - k * s1, s1 + k * c1)
        p2 = (c2 + k * s2, s2 - k * c2)
        p3 = (c2, s2)
        pts = []
        for ex, ey in (p1, p2, p3):
            ex, ey = ex * rx, ey * ry
            pts.append((cp * ex - sp * ey + cx, sp * ex + cp * ey + cy))
        curvas.append(tuple(pts))
        t += delta
    return curvas


def _path_d(d):
    """'d' de SVG -> (vertices, codigos) de matplotlib."""
    tk = _tokens(d)
    v, c = [], []
    x = y = 0.0
    sx = sy = 0.0
    ult_ctrl = None
    i = 0
    cmd = None
    while i < len(tk):
        if isinstance(tk[i], str):
            cmd = tk[i]
            i += 1
            if cmd in "zZ":
                v.append((sx, sy))
                c.append(Path.CLOSEPOLY)
                x, y = sx, sy
                ult_ctrl = None
                continue
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if C == "M":
            x, y = tk[i] + ox, tk[i + 1] + oy
            i += 2
            v.append((x, y))
            c.append(Path.MOVETO)
            sx, sy = x, y
            cmd = "l" if rel else "L"     # pares siguientes = lineto
            ult_ctrl = None
        elif C == "L":
            x, y = tk[i] + ox, tk[i + 1] + oy
            i += 2
            v.append((x, y))
            c.append(Path.LINETO)
            ult_ctrl = None
        elif C == "H":
            x = tk[i] + (ox if rel else 0)
            i += 1
            v.append((x, y))
            c.append(Path.LINETO)
            ult_ctrl = None
        elif C == "V":
            y = tk[i] + (oy if rel else 0)
            i += 1
            v.append((x, y))
            c.append(Path.LINETO)
            ult_ctrl = None
        elif C in ("C", "S"):
            if C == "C":
                x1, y1 = tk[i] + ox, tk[i + 1] + oy
                i += 2
            else:
                x1, y1 = (2 * x - ult_ctrl[0], 2 * y - ult_ctrl[1]) if ult_ctrl else (x, y)
            x2, y2 = tk[i] + ox, tk[i + 1] + oy
            xe, ye = tk[i + 2] + ox, tk[i + 3] + oy
            i += 4
            v += [(x1, y1), (x2, y2), (xe, ye)]
            c += [Path.CURVE4] * 3
            ult_ctrl = (x2, y2)
            x, y = xe, ye
        elif C == "A":
            rx, ry, rot, fa, fs = tk[i:i + 5]
            xe, ye = tk[i + 5] + ox, tk[i + 6] + oy
            i += 7
            for p1, p2, p3 in _arco_a_bezier(x, y, rx, ry, rot, int(fa), int(fs), xe, ye):
                v += [p1, p2, p3]
                c += [Path.CURVE4] * 3
            x, y = xe, ye
            ult_ctrl = None
        else:   # comando no soportado: se ignora su número
            i += 1
    return v, c


def _circulo(cx, cy, r):
    p = Path.circle((cx, cy), r)
    return list(map(tuple, p.vertices)), list(p.codes)


def _rect(x, y, w, h, rx=0, ry=None):
    ry = rx if ry is None else ry
    if not rx:
        return ([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)],
                [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY])
    d = (f"M{x + rx} {y}H{x + w - rx}A{rx} {ry} 0 0 1 {x + w} {y + ry}V{y + h - ry}"
         f"A{rx} {ry} 0 0 1 {x + w - rx} {y + h}H{x + rx}A{rx} {ry} 0 0 1 {x} {y + h - ry}"
         f"V{y + ry}A{rx} {ry} 0 0 1 {x + rx} {y}Z")
    return _path_d(d)


def cargar(nombre):
    """Lista de (vertices, codigos) en coordenadas del viewBox 24x24."""
    if nombre in _CACHE:
        return _CACHE[nombre]
    ruta = os.path.join(_CARPETA, f"{nombre}.svg")
    raiz = ET.parse(ruta).getroot()
    piezas = []
    for el in raiz.iter():
        tag = el.tag.split("}")[-1]
        a = el.attrib
        f = lambda k, d=0.0: float(a.get(k, d))
        if tag == "path":
            piezas.append(_path_d(a["d"]))
        elif tag == "circle":
            piezas.append(_circulo(f("cx"), f("cy"), f("r")))
        elif tag == "rect":
            piezas.append(_rect(f("x"), f("y"), f("width"), f("height"), f("rx"),
                                f("ry") if "ry" in a else None))
        elif tag == "line":
            piezas.append(([(f("x1"), f("y1")), (f("x2"), f("y2"))], [Path.MOVETO, Path.LINETO]))
    _CACHE[nombre] = piezas
    return piezas


def dibujar_icono(ax, nombre, x, y, tam, color, grosor=2.0, zorder=5, alpha=1.0):
    """Dibuja el icono en el cuadro (x, y, tam, tam), con y hacia abajo.

    El grosor sigue la proporción de Lucide (2 unidades de 24) y se
    convierte a puntos según el tamaño real del icono en la figura.
    Devuelve False si el icono no existe (la ficha sigue sin él).
    """
    try:
        piezas = cargar(nombre)
    except (OSError, ET.ParseError, KeyError):
        return False
    escala = tam / 24.0
    # pulgadas por unidad de datos en x -> puntos de trazo
    fig = ax.figure
    ancho_px = ax.get_window_extent().width
    x0, x1 = ax.get_xlim()
    pulg_por_unidad = ancho_px / fig.dpi / abs(x1 - x0)
    lw = grosor * escala * pulg_por_unidad * 72
    for vertices, codigos in piezas:
        for sub_v, sub_c in _subtrazos(vertices, codigos):
            pts = np.array(sub_v, dtype=float)
            # Lucide dibuja los puntos como trazos de 0.01 ("M12 16h.01") que
            # dependen de la punta redonda; matplotlib no la dibuja en un
            # trazo casi nulo, así que se ponen como círculos rellenos.
            if np.ptp(pts[:, 0]) < 0.05 and np.ptp(pts[:, 1]) < 0.05:
                cx, cy = pts[0] * escala + np.array([x, y])
                ax.add_patch(Circle((cx, cy), grosor / 2 * escala, fc=color, ec="none",
                                    zorder=zorder, alpha=alpha))
                continue
            pts = pts * escala + np.array([x, y])
            ax.add_patch(PathPatch(Path(pts, sub_c), fill=False, edgecolor=color, lw=lw,
                                   capstyle="round", joinstyle="round", zorder=zorder, alpha=alpha))
    return True


def _subtrazos(vertices, codigos):
    """Separa una pieza en subtrazos (cada MOVETO empieza uno)."""
    actual_v, actual_c = [], []
    for v, c in zip(vertices, codigos):
        if c == Path.MOVETO and actual_v:
            yield actual_v, actual_c
            actual_v, actual_c = [], []
        actual_v.append(v)
        actual_c.append(c)
    if actual_v:
        yield actual_v, actual_c
