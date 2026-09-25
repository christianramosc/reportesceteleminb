# -*- coding: utf-8 -*-
"""Iconos de la columna lateral y de las barras de sección.

Los SVG son de Lucide (https://lucide.dev), licencia ISC: uso libre con el
aviso de derechos, que va en iconos/LICENSE-lucide.txt. Van copiados en el
repositorio para que generar un reporte no dependa de descargar nada.

Se convierten a dibujo vectorial de ReportLab con svglib, así que se ven
nítidos a cualquier zoom. Si svglib no está instalado o falta un archivo, las
funciones devuelven None y el reporte se genera igual, sin ese icono: un
icono nunca debe impedir que salga un reporte.
"""

import copy
import os
import unicodedata

_CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iconos")
_CACHE = {}

# Reglas por palabra clave: la primera que coincide gana, así que el orden
# importa ("tasa de conversión" antes que otras; "monto" antes que
# "vendedor" para "Monto colocado por vendedor"; "distribución" antes que
# "tus solicitudes"). Cualquier título nuevo cae en el icono genérico.
_SECCIONES = [
    (("gap",), "shield-check"),
    (("foco", "atencion"), "triangle-alert"),
    (("lectura",), "book-open"),
    (("modelo", "vehiculo"), "car"),
    (("conversion",), "trending-up"),
    (("monto", "financier"), "banknote"),
    (("posicion",), "award"),
    (("vendedor", "equipo"), "users"),
    (("distribucion", "estatus", "panorama"), "chart-pie"),
    (("volumen", "categoria"), "chart-column"),
    (("tus solicitudes",), "list-checks"),
]
_SECCION_GENERICA = "layers"

_CIFRAS = [
    (("gap",), "shield-check"),
    (("menor conversion",), "trending-down"),
    (("conversion",), "trending-up"),
    (("monto",), "banknote"),
    (("sin dispersar", "pendiente"), "hourglass"),
    (("por cerrar",), "clipboard-list"),
    (("dias",), "calendar-days"),
    (("financiada",), "circle-check"),
    (("solicitud",), "file-text"),
]
_CIFRA_GENERICA = "layers"


def _normalizar(texto):
    sin_acentos = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")


def _buscar(texto, reglas, generico):
    t = _normalizar(texto)
    for claves, nombre in reglas:
        if any(k in t for k in claves):
            return nombre
    return generico


def nombre_seccion(titulo):
    return _buscar(titulo, _SECCIONES, _SECCION_GENERICA)


def nombre_cifra(etiqueta, alerta=False):
    nombre = _buscar(etiqueta, _CIFRAS, _CIFRA_GENERICA)
    # En alerta, el escudo cambia al que tiene signo de admiración.
    return "shield-alert" if (alerta and nombre == "shield-check") else nombre


def icono(nombre, tam, color):
    """Dibujo vectorial del icono, de `tam` puntos, en el color dado.
    Devuelve None si no se puede construir."""
    clave = (nombre, round(tam, 2), color)
    if clave not in _CACHE:
        _CACHE[clave] = _construir(nombre, tam, color)
    base = _CACHE[clave]
    # Copia: un mismo dibujo no debe colocarse en dos lugares del PDF.
    return copy.deepcopy(base) if base is not None else None


def _construir(nombre, tam, color):
    try:
        from io import BytesIO
        from svglib.svglib import svg2rlg
        with open(os.path.join(_CARPETA, f"{nombre}.svg"), encoding="utf-8") as f:
            svg = f.read().replace("currentColor", color)
        dibujo = svg2rlg(BytesIO(svg.encode("utf-8")))
        if dibujo is None or not dibujo.width:
            return None
        f = tam / dibujo.width
        dibujo.scale(f, f)
        dibujo.width *= f
        dibujo.height *= f
        return dibujo
    except Exception:
        return None
