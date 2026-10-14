# -*- coding: utf-8 -*-
"""Fecha local (México) y nombres cortos de archivos."""

from datetime import datetime, timezone

import pytest

from herramientas import fechas, nombres_archivo as N


def test_seis_de_la_tarde_en_mexico_sigue_siendo_el_mismo_dia(monkeypatch):
    """13/oct 18:00 en Colima = 14/oct 00:00 UTC. El reporte debe decir 13."""
    class RelojDelServidor(datetime):
        @classmethod
        def now(cls, tz=None):
            utc = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)
            return utc.astimezone(tz) if tz else utc.replace(tzinfo=None)

    monkeypatch.setattr(fechas, "datetime", RelojDelServidor)
    assert fechas.ahora() == datetime(2026, 10, 13, 18, 0)
    assert fechas.hoy().day == 13


@pytest.mark.parametrize("texto, esperado", [
    ("OCTUBRE 2026", "Oct26"), ("Septiembre 2026", "Sep26"), ("JULIO", "Jul"),
    ("SEPTIEMBRE_FINAL", "Sep"), ("Hoja1", "Hoja1"),
])
def test_periodo_corto(texto, esperado):
    assert N.periodo_corto(texto) == esperado


def test_rango_corto():
    assert N.rango_corto(["JUNIO 2026", "JULIO 2026", "SEPTIEMBRE 2026"]) == "Jun-Sep26"
    assert N.rango_corto(["DICIEMBRE 2025", "FEBRERO 2026"]) == "Dic25-Feb26"
    assert N.rango_corto(["JUNIO 2026"]) == "Jun26"


def test_nombre_seguro_para_windows():
    assert N.seguro('Ana "La" Ruiz: 1/2') == "Ana La Ruiz 12"
    assert N.seguro("Jessica Elizabeth Machuca Roque - Septiembre 2026") == \
        "Jessica Elizabeth Machuca Roque - Septiembre 2026"
