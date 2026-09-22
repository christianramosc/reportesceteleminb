# -*- coding: utf-8 -*-
"""Cálculos que comparten varias gráficas de distintos reportes.

Existe para que dos reportes que dibujan "lo mismo" no calculen cada uno a
su manera: el Avance/Resumen (vía reporte_base.py) y el Comparativo tienen
cada uno su propia función de gráfica, pero los números salen de aquí.
"""

import pandas as pd

COL_VEND = "Nombre del Vendedor"
COL_CAT = "Categoria"
COL_GAP = "¿Tiene GAP?"


def gap_en_financiados_por_vendedor(df):
    """Por vendedor: créditos financiados con GAP, total de financiados y %.

    Devuelve un DataFrame con columnas con_gap, financiados, pct, ordenado de
    menor a mayor para una gráfica de barras horizontales (el primero queda
    abajo). Solo incluye a quien colocó al menos un GAP.

    El orden desempata por porcentaje: si dos vendedores tienen 3 GAP, arriba
    queda el que los logró con menos créditos (3 de 5 antes que 3 de 6).
    """
    if not {COL_VEND, COL_CAT, COL_GAP}.issubset(df.columns):
        return pd.DataFrame(columns=["con_gap", "financiados", "pct"])

    fin = df[df[COL_CAT] == "FINANCIADO"]
    financiados = fin[COL_VEND].value_counts()
    con_gap = fin[fin[COL_GAP] == "SI"][COL_VEND].value_counts()
    if con_gap.empty:
        return pd.DataFrame(columns=["con_gap", "financiados", "pct"])

    tabla = pd.DataFrame({"con_gap": con_gap,
                          "financiados": financiados.reindex(con_gap.index)})
    tabla["pct"] = tabla["con_gap"] / tabla["financiados"] * 100
    return tabla.sort_values(["con_gap", "pct"], ascending=True)


def etiqueta_gap(con_gap, financiados, pct):
    """"3 de 5 financiados (60%)", "1 de 1 financiado (100%)".

    Sustituye al "¡Felicidades, <nombre>!" que llevaba la gráfica: en vez de
    premiar a quien tiene más, da el dato que permite juzgarlo. Así se ve,
    por ejemplo, que un empate en 3 no es igual si uno lo logró en 5
    créditos y el otro en 6.
    """
    financiados = int(financiados)
    palabra = "financiado" if financiados == 1 else "financiados"
    return f"{int(con_gap)} de {financiados} {palabra} ({pct:.0f}%)"


def rango_de_valor(datos):
    """Posición de cada fila entre los valores DISTINTOS (0 = el menor).

    Sirve para colorear por valor y no por posición: con un degradado
    asignado por renglón, dos vendedores con exactamente lo mismo (1 de 2,
    50%) salían uno vino oscuro y otro rosa claro, sugiriendo una diferencia
    que no existe. Devuelve (rangos, cuántos valores distintos hay).
    """
    claves = list(zip(datos["con_gap"].astype(int), datos["pct"].round(6)))
    unicas = sorted(set(claves))
    return [unicas.index(k) for k in claves], len(unicas)
