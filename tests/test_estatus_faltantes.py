# -*- coding: utf-8 -*-
"""Regresión: un mes sin algún estatus (septiembre 2026 no tuvo APROBADAS)
hacía tronar el comparativo con KeyError: 'APROBADO'."""
import pandas as pd
import pytest

from herramientas import comparativo_mensual_original as comp
from herramientas import reporte_base as base
from herramientas import resumen_vendedor_original as vend


def _df(categorias):
    vendedores = ["Ana Lopez", "Beto Diaz"]
    return pd.DataFrame({"Nombre del Vendedor": [vendedores[i % 2] for i in range(len(categorias))],
                         "Categoria": categorias})


@pytest.mark.parametrize("categorias", [
    ["RECHAZADO", "FINANCIADO", "CONTRAPROPUESTA"],   # sin APROBADO (septiembre real)
    ["RECHAZADO", "APROBADO", "CONTRAPROPUESTA"],     # sin FINANCIADO
    ["RECHAZADO", "RECHAZADO"],                       # un solo estatus
])
@pytest.mark.parametrize("modulo", [comp, base, vend], ids=["comparativo", "mensuales", "individual"])
def test_tabla_por_vendedor_no_truena_si_falta_un_estatus(modulo, categorias):
    tabla = modulo.analisis_por_vendedor(_df(categorias))
    assert "% Financiado" in tabla.columns
