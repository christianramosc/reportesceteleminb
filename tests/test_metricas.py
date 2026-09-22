# -*- coding: utf-8 -*-
"""Pruebas de herramientas/metricas.py (gráfica de GAP en financiados)."""
import pandas as pd

from herramientas import metricas as M


def _df(filas):
    return pd.DataFrame(filas, columns=["Nombre del Vendedor", "Categoria", "¿Tiene GAP?"])


def test_empate_en_conteo_se_desempata_por_porcentaje():
    df = _df([("Ana", "FINANCIADO", "SI")] * 3 + [("Ana", "FINANCIADO", "NO")] * 2 +
             [("Beto", "FINANCIADO", "SI")] * 3 + [("Beto", "FINANCIADO", "NO")] * 3)
    datos = M.gap_en_financiados_por_vendedor(df)
    # Orden ascendente para barras horizontales: el último queda arriba.
    assert list(datos.index) == ["Beto", "Ana"]


def test_valores_iguales_comparten_color():
    df = _df([("Ana", "FINANCIADO", "SI"), ("Ana", "FINANCIADO", "NO"),
              ("Beto", "FINANCIADO", "SI"), ("Beto", "FINANCIADO", "NO")])
    rangos, distintos = M.rango_de_valor(M.gap_en_financiados_por_vendedor(df))
    assert distintos == 1 and len(set(rangos)) == 1


def test_etiqueta_en_singular_y_plural():
    assert M.etiqueta_gap(1, 1, 100) == "1 de 1 financiado (100%)"
    assert M.etiqueta_gap(3, 5, 60) == "3 de 5 financiados (60%)"


def test_solo_cuenta_gap_en_financiados():
    df = _df([("Ana", "RECHAZADO", "SI")] * 4 + [("Ana", "FINANCIADO", "SI")])
    datos = M.gap_en_financiados_por_vendedor(df)
    assert int(datos.loc["Ana", "con_gap"]) == 1
    assert int(datos.loc["Ana", "financiados"]) == 1


def test_sin_gap_devuelve_vacio():
    assert M.gap_en_financiados_por_vendedor(_df([("Ana", "FINANCIADO", "NO")])).empty
