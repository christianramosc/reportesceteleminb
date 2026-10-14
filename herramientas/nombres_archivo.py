# -*- coding: utf-8 -*-
"""Nombres cortos para los archivos que se descargan.

Antes: "Avance_Preliminar_Datos_20261013_0000.xlsx" (largo, y la hora
siempre salía 0000). Ahora el nombre dice QUÉ es y DE QUÉ PERIODO:

    Avance_Oct26_corte13-10.pdf        Resumen_Jul26.pdf
    Avance_Oct26_corte13-10_datos.xlsx Comparativo_Jun-Sep26.pdf
    Avance_Oct26_corte13-10_WhatsApp.png
    Vendedores_Sep26.zip  ->  "Jessica Elizabeth Machuca Roque - Septiembre 2026.pdf"
    Bitacora_Oct26_al_13-10-2026.xlsx   (fecha en que se generó)

El periodo se toma del nombre de la hoja de la bitácora ("OCTUBRE 2026").
"""

import re
import unicodedata

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _normal(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return t.lower()


def mes_anio(texto):
    """'SEPTIEMBRE 2026' -> (9, 2026); sin año -> (9, None); nada -> (None, None)."""
    t = _normal(texto)
    mes = next((i + 1 for i, m in enumerate(MESES) if m in t), None)
    if mes is None:     # abreviado: "sep26", "Sep 2026"
        mes = next((i + 1 for i, c in enumerate(CORTOS) if re.search(rf"\b{c.lower()}", t)), None)
    m = re.search(r"(20\d{2})", t)
    return mes, (int(m.group(1)) if m else None)


def seguro(nombre):
    """Quita los caracteres que Windows no acepta en un nombre de archivo."""
    nombre = re.sub(r'[\\/:*?"<>|]+', "", str(nombre))
    return re.sub(r"\s+", " ", nombre).strip() or "archivo"


def periodo_corto(texto):
    """'OCTUBRE 2026' -> 'Oct26'. Si no se reconoce el mes, el texto limpio."""
    mes, anio = mes_anio(texto)
    if mes is None:
        return seguro(texto).replace(" ", "")[:20] or "Periodo"
    return CORTOS[mes - 1] + (str(anio)[2:] if anio else "")


def periodo_largo(texto):
    """'OCTUBRE 2026' -> 'Octubre 2026'."""
    mes, anio = mes_anio(texto)
    if mes is None:
        return seguro(texto).title()
    return MESES[mes - 1].title() + (f" {anio}" if anio else "")


def rango_corto(textos):
    """['JUNIO 2026', ..., 'SEPTIEMBRE 2026'] -> 'Jun-Sep26';
    años distintos -> 'Dic25-Feb26'; un solo mes -> 'Jun26'."""
    textos = list(textos)
    if not textos:
        return "Periodo"
    if len(textos) == 1:
        return periodo_corto(textos[0])
    (m1, a1), (m2, a2) = mes_anio(textos[0]), mes_anio(textos[-1])
    if m1 is None or m2 is None:
        return f"{periodo_corto(textos[0])}-{periodo_corto(textos[-1])}"
    if a1 == a2:
        return f"{CORTOS[m1 - 1]}-{CORTOS[m2 - 1]}" + (str(a2)[2:] if a2 else "")
    return f"{periodo_corto(textos[0])}-{periodo_corto(textos[-1])}"
