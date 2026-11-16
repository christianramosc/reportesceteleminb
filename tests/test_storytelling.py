"""Criterios visuales y de narrativa (graficas.py y las acciones de portada)."""

import pandas as pd

from herramientas import conclusiones as C
from herramientas import graficas as G
from herramientas import hallazgos as H


def _df(filas):
    return pd.DataFrame(filas, columns=["Nombre del Vendedor", "Categoria", "¿Tiene GAP?",
                                        "Monto Total a Financiar"])


BASE = _df([("Ana Ruiz Lopez", "FINANCIADO", "SI", 300_000)] * 4
           + [("Ana Ruiz Lopez", "APROBADO", "NO", 250_000)] * 2
           + [("Luis Mora Diaz", "RECHAZADO", "SI", 200_000)] * 6
           + [("Luis Mora Diaz", "EN PROCESO", "NO", 200_000)] * 2
           + [("Casa", "CANCELADO", "NO", 100_000)])


def test_los_estatus_se_agrupan_en_cuatro():
    assert [G.grupo_de(c) for c in ("FINANCIADO", "APROBADO", "EN PROCESO", "RECHAZADO",
                                    "CANCELADO", "NO FINANCIABLE", "CONTRAPROPUESTA")] == \
        [G.FIN, G.APR, G.TRA, G.PER, G.PER, G.PER, G.TRA]
    conteo = G.conteo_por_grupo(BASE["Categoria"])
    assert list(conteo.index) == G.GRUPOS and conteo.sum() == len(BASE)


def test_el_rojo_no_es_color_de_ningun_grupo():
    """El rojo queda solo para alertas."""
    assert G.ROJO not in G.COLOR_GRUPO.values()


def test_todas_las_graficas_se_generan(tmp_path):
    funciones = [G.grafica_status, G.grafica_mezcla_cierre, G.grafica_vendedores,
                 G.grafica_vendedor_status, G.grafica_monto_por_vendedor,
                 G.grafica_gap_por_categoria, G.grafica_gap_por_vendedor_total,
                 G.grafica_gap_por_vendedor_y_status, G.grafica_gap_financiado_por_vendedor]
    for f in funciones:
        ruta = tmp_path / f"{f.__name__}.png"
        assert f(BASE, str(ruta)) and ruta.stat().st_size > 2000, f.__name__


def test_pendiente_necesita_dos_meses(tmp_path):
    df = pd.concat([BASE.assign(Mes="AGOSTO"), BASE.head(8).assign(Mes="SEPTIEMBRE")])
    assert G.grafica_pendiente_vendedores(df, ["AGOSTO", "SEPTIEMBRE"], str(tmp_path / "p.png"))
    assert G.grafica_pendiente_vendedores(df, ["AGOSTO"], str(tmp_path / "q.png")) is None


def test_las_acciones_nombran_cuantas_y_de_quien():
    acciones = C.acciones_mensual(BASE, "cierre")
    assert 1 <= len(acciones) <= C.MAX_ACCIONES
    assert acciones[0].startswith("<b>Dar seguimiento a las 4 solicitudes sin dispersar</b>")
    assert any("Luis Mora" in a for a in acciones)          # convierte 0% con 8 solicitudes
    assert "“Casa”" in C._accion_datos(BASE)                # captura genérica
    # Sin nada abierto ni pendiente no se inventan acciones.
    solo_fin = _df([("Ana Ruiz Lopez", "FINANCIADO", "SI", 1)] * 6)
    assert C.acciones_mensual(solo_fin, "cierre") == []


def test_idea_principal_con_y_sin_meta():
    texto = C.idea_principal_mensual(BASE, "cierre", periodo="Octubre 2026")
    assert texto.startswith("Octubre 2026: se financiaron <b>4 de 15 solicitudes (27%)</b>")
    assert "meta" not in texto
    assert "faltaron 2 créditos" in C.idea_principal_mensual(BASE, "cierre", meta_conversion=40)
    assert "faltan 2 créditos" in C.idea_principal_mensual(BASE, "avance", meta_conversion=40)


def test_titulares_nuevos():
    assert H.volumen_por_mes(["AGOSTO", "OCTUBRE"], [85, 110]) == \
        "Las solicitudes subieron 29% de Agosto a Octubre: de 85 a 110"
    assert H.volumen_por_mes(["AGOSTO", "OCTUBRE"], [100, 104]).startswith("Volumen estable")
    cambio = pd.Series({"Ana Ruiz Lopez": 10, "Luis Mora Diaz": -5, "Sofia Paz Cruz": 1})
    assert H.quien_subio_y_bajo(cambio) == "Ana Ruiz subió 10 solicitudes; Luis Mora bajó 5"
