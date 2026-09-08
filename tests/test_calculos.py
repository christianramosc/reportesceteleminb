# -*- coding: utf-8 -*-
"""
Pruebas de los cálculos: limpieza, resumen y tabla por vendedor.

Se usan DataFrames armados a mano con totales que se conocen de antemano,
para que la prueba falle si un cambio altera un número, no solo si truena.
"""

import io
import contextlib

import pandas as pd
import pytest

from herramientas import avance_preliminar_original as avance
from herramientas import estatus as est
from tests.conftest import construir_bitacora


def _silencioso(funcion, *args, **kwargs):
    """Los scripts imprimen mucho en consola; aquí estorba."""
    with contextlib.redirect_stdout(io.StringIO()):
        return funcion(*args, **kwargs)


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------
def test_limpiar_datos_asigna_categoria():
    df = _silencioso(avance.limpiar_datos, construir_bitacora(n=15))
    assert "Categoria" in df.columns
    assert df["Categoria"].notna().all()


def test_limpiar_datos_no_pierde_filas():
    """Ninguna solicitud debe desaparecer por su estatus."""
    crudo = construir_bitacora(n=45)
    df = _silencioso(avance.limpiar_datos, crudo)
    assert len(df) == len(crudo)


def test_variantes_del_mismo_estatus_se_agrupan():
    crudo = construir_bitacora(estatus=["FINANCIADO", "financiados", "FINANCIADA"], n=9)
    df = _silencioso(avance.limpiar_datos, crudo)
    assert (df["Categoria"] == "FINANCIADO").sum() == 9


# ---------------------------------------------------------------------------
# Resumen general
# ---------------------------------------------------------------------------
def test_conteos_suman_el_total():
    df = _silencioso(avance.limpiar_datos, construir_bitacora(n=60))
    r = _silencioso(avance.resumen_general, df)
    assert sum(r["conteo_categorias"].values()) == r["total"] == 60


def test_conteo_por_categoria_exacto():
    crudo = construir_bitacora(
        estatus=["FINANCIADO", "FINANCIADO", "RECHAZADO", "SONDEO"], n=12)
    df = _silencioso(avance.limpiar_datos, crudo)
    r = _silencioso(avance.resumen_general, df)
    assert r["conteo_categorias"] == {"FINANCIADO": 6, "SONDEO": 3, "RECHAZADO": 3}
    assert r["financiados"] == 6


def test_en_tramite_excluye_los_cierres_definitivos():
    """en_tramite alimenta la frase 'siguen abiertas'. Si se cuela un
    NO FINANCIABLE o un RECHAZADO, el reporte promete negocio que no existe."""
    crudo = construir_bitacora(
        estatus=["SONDEO", "ANALISIS", "NO FINANCIABLE", "RECHAZADO",
                 "CANCELADO", "FINANCIADO", "APROBADO"], n=21)
    df = _silencioso(avance.limpiar_datos, crudo)
    r = _silencioso(avance.resumen_general, df)
    # solo SONDEO (3) y ANALISIS (3); APROBADO se reporta aparte
    assert r["en_tramite"] == 6


def test_sin_columna_status_no_truena():
    crudo = construir_bitacora(n=10).drop(columns=["STATUS"])
    df = _silencioso(avance.limpiar_datos, crudo)
    r = _silencioso(avance.resumen_general, df)
    assert r["total"] == 10


# ---------------------------------------------------------------------------
# Tabla por vendedor
# ---------------------------------------------------------------------------
def test_tabla_vendedor_cuadra_con_el_total():
    df = _silencioso(avance.limpiar_datos, construir_bitacora(n=60))
    tabla = _silencioso(avance.analisis_por_vendedor, df)
    assert tabla["Total"].sum() == 60


def test_tabla_vendedor_solo_trae_categorias_presentes():
    """Con 14 estatus posibles, la tabla no debe llenarse de columnas en cero."""
    crudo = construir_bitacora(estatus=["FINANCIADO", "RECHAZADO"], n=20)
    df = _silencioso(avance.limpiar_datos, crudo)
    tabla = _silencioso(avance.analisis_por_vendedor, df)
    presentes = [c for c in est.ORDEN_CATEGORIAS if c in tabla.columns]
    assert presentes == ["FINANCIADO", "RECHAZADO"]


def test_sin_aprobados_no_truena():
    """Si un mes no hubo ninguna APROBADA, esa columna no existe: el
    % de aprobación debe salir en 0, no reventar."""
    crudo = construir_bitacora(estatus=["RECHAZADO"], n=8)
    df = _silencioso(avance.limpiar_datos, crudo)
    tabla = _silencioso(avance.analisis_por_vendedor, df)
    assert (tabla["% Aprobación"] == 0).all()
