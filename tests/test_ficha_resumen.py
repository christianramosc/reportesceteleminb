# -*- coding: utf-8 -*-
"""Pruebas de la ficha de una página (PNG para WhatsApp)."""

import contextlib
import io

import pytest
from PIL import Image

from conftest import construir_bitacora
from herramientas import ficha_resumen as F
from herramientas import resumen_mensual_original as R


def _df(tmp_path, **kw):
    ruta = tmp_path / "b.xlsx"
    construir_bitacora(**kw).to_excel(ruta, index=False, sheet_name="SEPTIEMBRE 2026")
    with contextlib.redirect_stdout(io.StringIO()):
        df = R.limpiar_datos(R.cargar_archivo(ruta_local=str(ruta)))
        return df, R.resumen_general(df)


def test_vineta_separa_etiqueta_y_cuerpo():
    etiqueta, cuerpo = F._vineta("<b>GAP:</b> 2 de 4 créditos llevan GAP &amp; más.")
    assert etiqueta == "GAP"
    assert cuerpo == "2 de 4 créditos llevan GAP & más."
    assert F._vineta("sin etiqueta")[0] is None
    assert F._vineta("<b>Conversión:</b> el equipo")[1].startswith("El equipo")


@pytest.mark.parametrize("estatus", [None, ["FINANCIADO", "RECHAZADO"]])
def test_ancho_fijo_y_alto_segun_contenido(tmp_path, estatus):
    df, res = _df(tmp_path, estatus=estatus, n=40)
    ruta = F.ficha_mensual(df, str(tmp_path / "f.png"), periodo="Septiembre 2026",
                           pdv="PDV", analista="Analista", resumen=res)
    ancho, alto = Image.open(ruta).size
    assert ancho == 1080
    assert 1200 < alto < 3200


def test_con_todos_los_estatus_no_se_repite_color(tmp_path):
    df, _ = _df(tmp_path, n=60)
    F._conteo_estatus(df)
    colores = [F._est.color(c) for c in df["Categoria"].unique()]
    assert len(set(colores)) == len(colores)


def test_si_falla_no_tumba_el_reporte():
    def revienta(*_a, **_k):
        raise RuntimeError("sin datos")
    with contextlib.redirect_stdout(io.StringIO()) as salida:
        assert F.generar_ficha_segura(revienta) is None
    assert "no se pudo generar la ficha" in salida.getvalue()


def test_quitar_cifras_es_exacto():
    cifras = [{"etiqueta": "CONVERSIÓN"}, {"etiqueta": "MENOR CONVERSIÓN"}, {"etiqueta": "GAP EN FINANCIADOS"}]
    quedan = [c["etiqueta"] for c in F._cifras_sin(cifras, ["CONVERSIÓN"])]
    assert quedan == ["MENOR CONVERSIÓN", "GAP EN FINANCIADOS"]
