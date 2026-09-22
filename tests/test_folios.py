# -*- coding: utf-8 -*-
"""Pruebas de herramientas/folios.py: folios que aparecen en varios meses."""
import pandas as pd

from herramientas import folios as F

ORDEN = ["JUNIO", "JULIO", "AGOSTO"]


def _df(filas):
    """filas: (folio, mes, categoria, vendedor, monto)."""
    return pd.DataFrame(filas, columns=["Folio CCK", "Mes", "Categoria",
                                        "Nombre del Vendedor", "Monto Total a Financiar"])


def test_folio_aprobado_y_luego_financiado_cuenta_una_vez():
    df = _df([("100", "JUNIO", "APROBADO", "Ana Lopez", 300),
              ("100", "JULIO", "FINANCIADO", "Ana Lopez", 300),
              ("200", "JULIO", "RECHAZADO", "Beto Diaz", 250)])
    unico, res = F.consolidar(df, ORDEN)
    assert len(unico) == 2
    fila = unico[unico["Folio CCK"] == "100"].iloc[0]
    assert fila["Categoria"] == "FINANCIADO"   # último estatus
    assert fila["Mes"] == "JUNIO"              # mes de captura
    assert len(res["cruces"]) == 1


def test_folio_que_tarda_dos_meses():
    df = _df([("100", "JUNIO", "APROBADO", "Ana Lopez", 300),
              ("100", "JULIO", "APROBADO", "Ana Lopez", 300),
              ("100", "AGOSTO", "FINANCIADO", "Ana Lopez", 300)])
    unico, res = F.consolidar(df, ORDEN)
    assert len(unico) == 1
    cruce = res["cruces"].iloc[0]
    assert cruce["Mes de captura"] == "JUNIO"
    assert cruce["Mes del último estatus"] == "AGOSTO"


def test_formatos_distintos_del_mismo_folio():
    df = _df([(17665240, "JUNIO", "APROBADO", "Ana Lopez", 1),
              ("17665240.0", "JULIO", "FINANCIADO", "Ana Lopez", 1),
              (" 17665240 ", "AGOSTO", "FINANCIADO", "Ana Lopez", 1)])
    assert len(F.consolidar(df, ORDEN)[0]) == 1


def test_orden_de_meses_no_depende_del_orden_de_las_filas():
    """Si el archivo de julio se carga antes que el de junio, el mes de
    captura debe seguir siendo junio."""
    df = _df([("100", "JULIO", "FINANCIADO", "Ana Lopez", 300),
              ("100", "JUNIO", "APROBADO", "Ana Lopez", 300)])
    unico, _ = F.consolidar(df, ORDEN)
    assert unico.iloc[0]["Mes"] == "JUNIO"
    assert unico.iloc[0]["Categoria"] == "FINANCIADO"


def test_financiado_en_dos_meses_se_advierte():
    df = _df([("100", "JUNIO", "FINANCIADO", "Ana Lopez", 300),
              ("100", "JULIO", "FINANCIADO", "Ana Lopez", 300)])
    _, res = F.consolidar(df, ORDEN)
    assert res["financiado_doble"] == ["100"]
    assert any("Revisa estos folios" in t for t in F.texto_aviso(res))


def test_filas_sin_folio_se_conservan():
    df = _df([(None, "JUNIO", "APROBADO", "Ana Lopez", 1),
              (float("nan"), "JULIO", "APROBADO", "Ana Lopez", 1),
              ("", "JULIO", "APROBADO", "Ana Lopez", 1)])
    assert len(F.consolidar(df, ORDEN)[0]) == 3


def test_sin_cruces_no_hay_aviso():
    df = _df([("100", "JUNIO", "APROBADO", "Ana Lopez", 1),
              ("200", "JULIO", "FINANCIADO", "Ana Lopez", 1)])
    _, res = F.consolidar(df, ORDEN)
    assert F.texto_aviso(res) == []


def test_consolidar_es_idempotente():
    df = _df([("100", "JUNIO", "APROBADO", "Ana Lopez", 1),
              ("100", "JULIO", "FINANCIADO", "Ana Lopez", 1)])
    unico, _ = F.consolidar(df, ORDEN)
    otra_vez, res = F.consolidar(unico, ORDEN)
    assert len(otra_vez) == len(unico) and res["cruces"].empty


def test_anotar_conserva_todas_las_filas_y_marca_la_vigente():
    df = _df([("100", "JUNIO", "APROBADO", "Ana Lopez", 1),
              ("100", "JULIO", "FINANCIADO", "Ana Lopez", 1),
              ("200", "JULIO", "RECHAZADO", "Beto Diaz", 1)])
    anot = F.anotar(df, ORDEN)
    assert len(anot) == 3
    assert anot["Cuenta en periodo"].tolist() == ["NO", "SI", "SI"]
    assert anot["Mes de captura"].tolist() == ["JUNIO", "JUNIO", "JULIO"]
