# -*- coding: utf-8 -*-
"""
Genera la GUÍA VISUAL para armar el ZIP mensual (una página, para imprimir
o mandar por chat a los compañeros).

La guía se dibuja A PARTIR DEL CATÁLOGO REAL (herramientas/estatus.py) y de
las reglas reales de herramientas/bitacora_zip.py, así que cuando se agregue
un estatus nuevo basta con volver a correr esto:

    python -m herramientas.guia_zip

y la guía sale actualizada, con el mismo color que ese estatus tiene en las
gráficas de los reportes.
"""

import os
import unicodedata

from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as rl_canvas

try:
    from . import estatus as est
except ImportError:  # ejecución suelta
    import estatus as est


INBURSA_AZUL = "#191970"
MG_ROJO = "#E4002B"
GRIS_OSCURO = "#2B2B2B"
GRIS_TEXTO = "#6B7280"
GRIS_LINEA = "#E3E5E9"
GRIS_FONDO = "#F6F7F9"
VERDE_OK = "#166534"

ANCHO, ALTO = letter


def _sin_acentos(texto):
    return (unicodedata.normalize("NFKD", texto)
            .encode("ascii", "ignore").decode("utf-8"))


def nombre_de_carpeta(clave):
    """Cómo debe llamarse la carpeta en el ZIP para ese estatus.

    Se usa la clave del catálogo sin acentos: es lo que bitacora_zip.py
    normaliza y lo que estatus.py reconoce después en el Excel.
    """
    return _sin_acentos(clave)


def _texto(c, x, y, texto, fuente="Helvetica", tam=9, color=GRIS_OSCURO):
    c.setFont(fuente, tam)
    c.setFillColor(rl_colors.HexColor(color))
    c.drawString(x, y, texto)


def _caja(c, x, y, ancho, alto, relleno=None, borde=GRIS_LINEA, radio=3):
    if relleno:
        c.setFillColor(rl_colors.HexColor(relleno))
    c.setStrokeColor(rl_colors.HexColor(borde))
    c.setLineWidth(0.7)
    c.roundRect(x, y, ancho, alto, radio, fill=1 if relleno else 0, stroke=1)


def dibujar(ruta_salida):
    c = rl_canvas.Canvas(ruta_salida, pagesize=letter)

    # ── Encabezado ──────────────────────────────────────────────────────
    c.setFillColor(rl_colors.HexColor(INBURSA_AZUL))
    c.rect(0, ALTO - 0.16 * cm, ANCHO, 0.16 * cm, fill=1, stroke=0)
    c.setFillColor(rl_colors.HexColor(MG_ROJO))
    c.rect(1.5 * cm, ALTO - 1.5 * cm, 0.26 * cm, 0.26 * cm, fill=1, stroke=0)
    _texto(c, 1.95 * cm, ALTO - 1.45 * cm, "AUTOEXPRESS INBURSA",
           "Helvetica-Bold", 11, INBURSA_AZUL)
    _texto(c, 1.95 * cm, ALTO - 1.85 * cm,
           "Cómo armar el ZIP mensual de la bitácora  ·  MG Colima",
           "Helvetica", 9, GRIS_TEXTO)

    y = ALTO - 2.6 * cm
    c.setStrokeColor(rl_colors.HexColor(GRIS_LINEA))
    c.line(1.5 * cm, y, ANCHO - 1.5 * cm, y)

    # ── Paso 1: el árbol del ZIP ────────────────────────────────────────
    y -= 0.85 * cm
    _texto(c, 1.5 * cm, y, "1.  Estructura del ZIP", "Helvetica-Bold", 12, MG_ROJO)

    y -= 0.55 * cm
    alto_caja = 3.5 * cm
    _caja(c, 1.5 * cm, y - alto_caja, 9.2 * cm, alto_caja, GRIS_FONDO)

    arbol = [
        ("JUNIO 2026.zip", 0, INBURSA_AZUL, "Helvetica-Bold"),
        ("JUNIO 2026/", 1, INBURSA_AZUL, "Helvetica-Bold"),
        ("FINANCIADOS/", 2, GRIS_OSCURO, "Helvetica"),
        ("Solicitud_CCK1001.pdf", 3, GRIS_TEXTO, "Helvetica"),
        ("Amortizacion_CCK1001.pdf", 3, GRIS_TEXTO, "Helvetica"),
        ("APROBADOS/", 2, GRIS_OSCURO, "Helvetica"),
        ("...una carpeta por estatus", 2, GRIS_TEXTO, "Helvetica-Oblique"),
    ]
    yy = y - 0.6 * cm
    for etiqueta, nivel, color, fuente in arbol:
        _texto(c, 1.9 * cm + nivel * 0.55 * cm, yy, etiqueta, fuente, 8.2, color)
        yy -= 0.44 * cm

    # Nota al lado del árbol
    _caja(c, 11.1 * cm, y - alto_caja, 8.0 * cm, alto_caja, "#EEF0F8")
    notas = [
        ("El nombre del ZIP define el mes", "Helvetica-Bold"),
        ("de la hoja del Excel. Escríbelo", "Helvetica"),
        ("como MES AÑO (ej. JUNIO 2026).", "Helvetica"),
        ("", "Helvetica"),
        ("El emparejado de Solicitud con", "Helvetica-Bold"),
        ("Amortización NO usa el nombre del", "Helvetica"),
        ("archivo: usa el Folio CCK que viene", "Helvetica"),
        ("dentro del PDF.", "Helvetica"),
    ]
    yy = y - 0.6 * cm
    for linea, fuente in notas:
        _texto(c, 11.5 * cm, yy, linea, fuente, 8.2, GRIS_OSCURO)
        yy -= 0.4 * cm

    y -= alto_caja + 0.9 * cm

    # ── Paso 2: las carpetas posibles ───────────────────────────────────
    _texto(c, 1.5 * cm, y, "2.  Las 14 carpetas posibles (usa solo las que tengas)",
           "Helvetica-Bold", 12, MG_ROJO)
    y -= 0.3 * cm
    _texto(c, 1.5 * cm, y - 0.22 * cm,
           "El color es el mismo que ese estatus tiene en las gráficas del reporte.",
           "Helvetica-Oblique", 8, GRIS_TEXTO)

    y -= 0.95 * cm
    grupos = [
        ("CERRADAS — el negocio ya se concretó", est.CERRADA_POSITIVA),
        ("ABIERTAS — todavía pueden convertirse en financiadas", est.ABIERTA),
        ("CERRADAS — el negocio se cayó", est.CERRADA_NEGATIVA),
    ]
    for titulo, grupo in grupos:
        _texto(c, 1.5 * cm, y, titulo, "Helvetica-Bold", 8.5, GRIS_TEXTO)
        y -= 0.5 * cm
        claves = [cat.clave for cat in est.CATALOGO if cat.grupo == grupo]
        x = 1.5 * cm
        for clave in claves:
            carpeta = nombre_de_carpeta(clave)
            ancho_chip = max(2.5 * cm, (len(carpeta) * 0.16 + 0.75) * cm)
            if x + ancho_chip > ANCHO - 1.5 * cm:
                x = 1.5 * cm
                y -= 0.72 * cm
            _caja(c, x, y - 0.12 * cm, ancho_chip, 0.6 * cm, "#FFFFFF")
            c.setFillColor(rl_colors.HexColor(est.color(clave)))
            c.rect(x + 0.14 * cm, y - 0.02 * cm, 0.2 * cm, 0.4 * cm, fill=1, stroke=0)
            _texto(c, x + 0.48 * cm, y + 0.08 * cm, carpeta, "Helvetica", 7.6, GRIS_OSCURO)
            x += ancho_chip + 0.18 * cm
        y -= 1.0 * cm

    # ── Paso 3: reglas dentro de cada carpeta ───────────────────────────
    _texto(c, 1.5 * cm, y, "3.  Qué va DENTRO de cada carpeta", "Helvetica-Bold", 12, MG_ROJO)
    y -= 0.75 * cm

    reglas = [
        ("Solo archivos .PDF, sueltos", "Nada de subcarpetas dentro de la carpeta de estatus."),
        ("El nombre debe decir qué es", "Que contenga la palabra Solicitud o Amortizacion."),
        ("Los dos PDF de cada cliente", "La Solicitud trae los datos; la Amortización, el vehículo y montos."),
    ]
    for titulo, detalle in reglas:
        c.setFillColor(rl_colors.HexColor(VERDE_OK))
        c.circle(1.65 * cm, y + 0.1 * cm, 0.09 * cm, fill=1, stroke=0)
        _texto(c, 1.95 * cm, y, titulo, "Helvetica-Bold", 9, GRIS_OSCURO)
        _texto(c, 1.95 * cm, y - 0.36 * cm, detalle, "Helvetica", 8.2, GRIS_TEXTO)
        y -= 0.95 * cm

    # ── Paso 4: qué saca el sistema de cada PDF ─────────────────────────
    y -= 0.1 * cm
    _texto(c, 1.5 * cm, y, "4.  Qué saca el sistema de cada PDF", "Helvetica-Bold", 12, MG_ROJO)
    y -= 0.65 * cm

    alto_col = 2.75 * cm
    ancho_col = (ANCHO - 3 * cm - 0.4 * cm) / 2
    for i, (titulo, campos) in enumerate([
        ("De la SOLICITUD", ["Folio CCK  (es la llave)", "Nombre completo y fecha de nacimiento",
                              "Teléfono y correo", "Nombre del vendedor"]),
        ("De la AMORTIZACIÓN", ["Folio CCK  (es la llave)", "Vehículo, marca y año",
                                 "Precio, enganche y plazo", "Tasa, mensualidad y seguro GAP"]),
    ]):
        x = 1.5 * cm + i * (ancho_col + 0.4 * cm)
        _caja(c, x, y - alto_col, ancho_col, alto_col, GRIS_FONDO)
        _texto(c, x + 0.35 * cm, y - 0.55 * cm, titulo, "Helvetica-Bold", 9, INBURSA_AZUL)
        yy = y - 1.05 * cm
        for campo in campos:
            c.setFillColor(rl_colors.HexColor(GRIS_TEXTO))
            c.circle(x + 0.45 * cm, yy + 0.09 * cm, 0.05 * cm, fill=1, stroke=0)
            _texto(c, x + 0.68 * cm, yy, campo, "Helvetica", 8, GRIS_OSCURO)
            yy -= 0.44 * cm
    y -= alto_col + 0.85 * cm

    # ── Paso 5: los tres errores que NO avisan ──────────────────────────
    alto_err = 3.3 * cm
    _caja(c, 1.5 * cm, y - alto_err, ANCHO - 3 * cm, alto_err, "#FBE7E9", MG_ROJO)
    _texto(c, 1.85 * cm, y - 0.68 * cm,
           "Cuidado: estos tres errores NO dan ningún aviso — el cliente simplemente no aparece",
           "Helvetica-Bold", 9.5, MG_ROJO)

    errores = [
        "Un PDF dentro de una subcarpeta  →  no se lee (solo se buscan PDFs sueltos).",
        "Un nombre como reporte_123.pdf  →  se ignora (no dice Solicitud ni Amortizacion).",
        "Un archivo .docx, .jpg o un PDF escaneado como imagen  →  no se puede leer.",
    ]
    yy = y - 1.3 * cm
    for e in errores:
        c.setFillColor(rl_colors.HexColor(MG_ROJO))
        c.rect(1.95 * cm, yy - 0.03 * cm, 0.14 * cm, 0.14 * cm, fill=1, stroke=0)
        _texto(c, 2.3 * cm, yy, e, "Helvetica", 8.4, GRIS_OSCURO)
        yy -= 0.5 * cm

    _texto(c, 1.95 * cm, yy - 0.05 * cm,
           "Antes de subirlo: la suma de PDFs de todas las carpetas debe ser el doble de tus "
           "clientes del mes.",
           "Helvetica-Bold", 8.4, VERDE_OK)

    # ── Pie ─────────────────────────────────────────────────────────────
    c.setStrokeColor(rl_colors.HexColor(GRIS_LINEA))
    c.line(1.5 * cm, 1.35 * cm, ANCHO - 1.5 * cm, 1.35 * cm)
    _texto(c, 1.5 * cm, 0.95 * cm,
           "Si aparece un estatus que no está en esta lista, crea igual su carpeta: "
           "el sistema lo toma y le asigna un color automático.",
           "Helvetica", 7.8, GRIS_TEXTO)

    c.showPage()
    c.save()
    return ruta_salida


if __name__ == "__main__":
    salida = os.path.join(os.getcwd(), "Guia_armado_ZIP.pdf")
    print("Guía generada:", dibujar(salida))
