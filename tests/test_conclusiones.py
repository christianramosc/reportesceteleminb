# -*- coding: utf-8 -*-
"""Pruebas de herramientas/conclusiones.py.

Cada prueba protege una de las reglas del docstring de ese módulo. Si una
falla, casi seguro alguien reintrodujo uno de los vicios que se corrigieron:
textos repetidos, "mejores" por ruido, promedios mal ponderados o fechas de
corte que no corresponden a los datos.
"""
import datetime
import re

import pandas as pd
import pytest

from herramientas import conclusiones as C


def _bitacora(filas):
    """filas: lista de (vendedor, categoria, gap, monto)."""
    return pd.DataFrame(filas, columns=["Nombre del Vendedor", "Categoria",
                                        "¿Tiene GAP?", "Monto Total a Financiar"])


def _sin_etiquetas(t):
    return re.sub(r"</?b>", "", t)


@pytest.fixture
def mes():
    filas = []
    filas += [("Ana Lopez Ruiz", "FINANCIADO", "SI", 300000)] * 3
    filas += [("Ana Lopez Ruiz", "RECHAZADO", "SI", 280000)] * 3
    filas += [("Beto Diaz Mora", "FINANCIADO", "NO", 310000)] * 1
    filas += [("Beto Diaz Mora", "APROBADO", "NO", 320000)] * 4
    filas += [("Beto Diaz Mora", "RECHAZADO", "SI", 290000)] * 3
    filas += [("Casa", "FINANCIADO", "NO", 250000)] * 1
    return _bitacora(filas)


# ---------------------------------------------------------------- mensual
def test_focos_y_conclusiones_no_comparten_textos(mes):
    focos, conclusiones = C.focos_y_conclusiones_mensual(mes, "cierre")
    assert not set(focos) & set(conclusiones)


def test_plural_en_espanol():
    assert C._n(11, "solicitud") == "11 solicitudes"
    assert C._n(1, "solicitud") == "1 solicitud"
    assert C._n(4, "día") == "4 días"


def test_pendientes_dicen_monto_y_quien_los_tiene(mes):
    focos, _ = C.focos_y_conclusiones_mensual(mes, "cierre")
    pendientes = next(f for f in focos if "Sin dispersar" in f)
    assert "$" in pendientes
    assert "Beto Diaz Mora" in pendientes


def test_vendedor_no_persona_se_senala(mes):
    focos, _ = C.focos_y_conclusiones_mensual(mes, "cierre")
    assert any("Casa" in f and "Vendedor por revisar" in f for f in focos)


def test_casa_no_entra_en_la_comparacion_de_tasas(mes):
    """Una captura genérica no compite con las personas, aunque tenga
    volumen suficiente. A Casa se le dan 6 solicitudes, todas financiadas:
    sin el filtro de nombre de persona, saldría como 'mejor conversión'.
    (Con 1 sola solicitud la prueba no servía: el mínimo de 5 ya la excluía
    por otro lado, y quitar el filtro no la hacía fallar.)"""
    con_volumen = pd.concat([mes, _bitacora([("Casa", "FINANCIADO", "NO", 1)] * 5)],
                            ignore_index=True)
    _, conclusiones = C.focos_y_conclusiones_mensual(con_volumen, "cierre")
    conv = next(c for c in conclusiones if "Conversión" in c)
    assert "Casa" not in conv


def test_avance_con_fecha_de_otro_mes_advierte_y_no_habla_de_dias(mes):
    ctx = {"fecha_corte": datetime.date(2026, 9, 20), "dia_actual": 20,
           "dias_en_mes": 30, "dias_restantes": 10}
    focos, _ = C.focos_y_conclusiones_mensual(mes, "avance", ctx=ctx, hoja="JULIO 2026")
    assert "fecha de corte" in _sin_etiquetas(focos[0]).lower()
    assert not any("fin de mes" in f for f in focos)


def test_avance_con_fecha_coherente_no_advierte(mes):
    ctx = {"fecha_corte": datetime.date(2026, 7, 20), "dia_actual": 20,
           "dias_en_mes": 31, "dias_restantes": 11}
    focos, _ = C.focos_y_conclusiones_mensual(mes, "avance", ctx=ctx, hoja="JULIO 2026")
    assert not any("Revisa la fecha de corte" in f for f in focos)


def test_sin_columnas_no_truena():
    df = pd.DataFrame({"Otra": [1, 2, 3]})
    focos, conclusiones = C.focos_y_conclusiones_mensual(df, "cierre")
    assert conclusiones  # mensaje de datos insuficientes, no excepción


# ------------------------------------------------------------ comparativo
def _tabla(totales, financiados, rechazados):
    meses = ["Junio", "Julio", "Agosto"][:len(totales)]
    t = pd.DataFrame({"Total": totales, "Financiado": financiados,
                      "Rechazado": rechazados}, index=meses)
    t["% Financiado"] = t["Financiado"] / t["Total"] * 100
    return t


def test_volumen_con_diferencia_minima_se_reporta_estable():
    tabla = _tabla([27, 26, 28], [6, 6, 5], [12, 9, 17])
    lectura, _ = C.lectura_y_conclusiones_comparativo(
        tabla, ["JUNIO", "JULIO", "AGOSTO"], pd.DataFrame())
    volumen = next(t for t in lectura if "olumen" in t)
    assert "estable" in volumen.lower()


def test_caida_de_conversion_se_explica_con_el_rechazo():
    tabla = _tabla([27, 26, 28], [6, 6, 5], [12, 9, 17])
    lectura, _ = C.lectura_y_conclusiones_comparativo(
        tabla, ["JUNIO", "JULIO", "AGOSTO"], pd.DataFrame())
    conv = next(t for t in lectura if "Conversión" in t)
    assert "Agosto" in conv and "rechazo" in conv.lower()


def test_lectura_y_conclusiones_no_se_repiten():
    tabla = _tabla([27, 26, 28], [6, 6, 5], [12, 9, 17])
    df = _bitacora([("Ana Lopez Ruiz", "FINANCIADO", "SI", 1)] * 5 +
                   [("Beto Diaz Mora", "RECHAZADO", "NO", 1)] * 5)
    df["Mes"] = ["JUNIO"] * 3 + ["AGOSTO"] * 2 + ["JUNIO"] * 5
    lectura, conclusiones = C.lectura_y_conclusiones_comparativo(
        tabla, ["JUNIO", "JULIO", "AGOSTO"], df)
    assert not set(lectura) & set(conclusiones)


# ------------------------------------------------------------ individual
def test_individual_compara_contra_la_conversion_real_del_equipo(mes):
    """Equipo: 5 financiados de 15 = 33%. El promedio simple de tasas
    (50%, 12.5%, 100%) daría 54%: esa es la cifra que NO debe aparecer."""
    texto = " ".join(C.conclusiones_vendedor(mes, "Ana Lopez Ruiz"))
    assert "(33%)" in texto
    assert "54%" not in texto


def test_individual_con_pocas_solicitudes_advierte():
    df = _bitacora([("Ana Lopez Ruiz", "FINANCIADO", "SI", 1)] * 2 +
                   [("Beto Diaz Mora", "RECHAZADO", "NO", 1)] * 8)
    texto = _sin_etiquetas(" ".join(C.conclusiones_vendedor(df, "Ana Lopez Ruiz")))
    assert "no es una comparación justa" in texto


# ------------------------------------------ GAP: 100% esperado, 50% alerta
def _limpio(t):
    return re.sub(r"<[^>]+>", "", t)


def _mensaje_gap(filas_vendedor, vendedor="Ana Lopez Ruiz"):
    """filas_vendedor: (categoria, gap). Se agrega un compañero para que el
    equipo tenga más de una persona."""
    filas = [(vendedor, cat, gap, 1) for cat, gap in filas_vendedor]
    filas += [("Beto Diaz Mora", "FINANCIADO", "SI", 1)] * 3
    return _limpio(C.conclusiones_vendedor(_bitacora(filas), vendedor)[0])


def test_gap_va_primero_y_es_un_solo_mensaje():
    filas = [("Ana Lopez Ruiz", "FINANCIADO", "NO", 1)] * 3 + \
            [("Beto Diaz Mora", "FINANCIADO", "SI", 1)] * 3
    concl = [_limpio(c) for c in C.conclusiones_vendedor(_bitacora(filas), "Ana Lopez Ruiz")]
    assert "GAP" in concl[0]
    assert sum("GAP" in c for c in concl) == 1


def test_ningun_mensaje_habla_de_meta():
    """El 50% es umbral de alerta, no meta: presentarlo como meta hacía que
    quien llegaba a la mitad leyera que ya había cumplido."""
    casos = [
        [("RECHAZADO", "NO")] * 4,                                  # alerta
        [("FINANCIADO", "NO")] + [("RECHAZADO", "SI")] * 5,         # alerta en financiados
        [("RECHAZADO", "SI")] + [("RECHAZADO", "NO")] * 3,          # oportunidad
        [("FINANCIADO", "SI"), ("FINANCIADO", "NO")],               # la mitad
        [("FINANCIADO", "SI")] * 3,                                 # completo
    ]
    for filas in casos:
        msg = _mensaje_gap(filas).lower()
        assert "meta" not in msg and "cumpl" not in msg, msg


def test_cero_gap_en_solicitudes_es_alerta():
    msg = _mensaje_gap([("RECHAZADO", "NO")] * 4)
    assert msg.startswith("Alerta de GAP")
    assert "ninguna de tus 4 solicitudes" in msg and "todas lo lleven" in msg


def test_ofrece_gap_pero_lo_pierde_en_financiados():
    msg = _mensaje_gap([("FINANCIADO", "NO")] + [("RECHAZADO", "SI")] * 5)
    assert msg.startswith("Alerta de GAP")
    assert "0 de 1" in msg and "entre la solicitud y la dispersión" in msg


def test_financiados_bajo_la_mitad_con_varios_creditos():
    msg = _mensaje_gap([("FINANCIADO", "SI")] + [("FINANCIADO", "NO")] * 2)
    assert msg.startswith("Alerta de GAP")
    assert "solo 1 de tus 3 créditos financiados lleva GAP (33%)" in msg


def test_incumple_las_dos_condiciones_en_un_solo_mensaje():
    msg = _mensaje_gap([("FINANCIADO", "NO")] * 2 + [("RECHAZADO", "NO")] * 2)
    assert msg.startswith("Alerta de GAP") and "tampoco" in msg


def test_oportunidad_cuenta_lo_que_falta_contra_el_total():
    """1 de 4: faltan 3 para que todas lo lleven (no 1 para llegar a la mitad)."""
    msg = _mensaje_gap([("RECHAZADO", "SI")] + [("RECHAZADO", "NO")] * 3)
    assert msg.startswith("Oportunidad en GAP")
    assert "Alerta" not in msg and "a 3 les faltó" in msg


def test_exactamente_la_mitad_no_es_alerta_ni_se_presenta_como_logro():
    msg = _mensaje_gap([("FINANCIADO", "SI"), ("FINANCIADO", "NO")])
    assert msg.startswith("GAP:")
    assert "a 1 le faltó" in msg


def test_todas_con_gap_es_gap_completo():
    msg = _mensaje_gap([("FINANCIADO", "SI")] * 2 + [("RECHAZADO", "SI")])
    assert msg.startswith("GAP completo")


def test_sin_financiados_lo_dice():
    msg = _mensaje_gap([("RECHAZADO", "SI"), ("APROBADO", "NO")])
    assert "Aún no tienes créditos financiados" in msg


def test_captura_generica_no_recibe_alerta():
    filas = [("Casa", "FINANCIADO", "NO", 1)] + [("Beto Diaz Mora", "FINANCIADO", "SI", 1)] * 3
    msg = _limpio(C.conclusiones_vendedor(_bitacora(filas), "Casa")[0])
    assert "Alerta" not in msg


def test_el_umbral_es_un_solo_parametro(monkeypatch):
    """Si el umbral de alerta cambia a 60%, con mover UMBRAL_ALERTA_GAP basta."""
    monkeypatch.setattr(C, "UMBRAL_ALERTA_GAP", 60.0)
    msg = _mensaje_gap([("FINANCIADO", "SI"), ("FINANCIADO", "NO")])   # 50%
    assert msg.startswith("Alerta de GAP")


def test_columna_lateral_cuenta_lo_que_falta():
    from herramientas import lateral as L
    df = _bitacora([("Ana Lopez Ruiz", "FINANCIADO", "SI", 1)] * 2 +
                   [("Ana Lopez Ruiz", "FINANCIADO", "NO", 1)] * 4)
    gap = [c for c in L.cifras_resumen(df) if "GAP" in c["etiqueta"]][0]
    assert gap["nota"] == "4 sin GAP de 6 créditos" and gap["alerta"]
    assert "meta" not in gap["nota"]
