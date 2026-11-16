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


def test_idea_principal():
    texto = C.idea_principal_mensual(BASE, "cierre", periodo="Octubre 2026")
    assert texto.startswith("Octubre 2026: se financiaron <b>4 de 15 solicitudes (27%)</b>")
    assert "meta" not in texto


def test_titulares_nuevos():
    assert H.volumen_por_mes(["AGOSTO", "OCTUBRE"], [85, 110]) == \
        "Las solicitudes subieron 29% de Agosto a Octubre: de 85 a 110"
    assert H.volumen_por_mes(["AGOSTO", "OCTUBRE"], [100, 104]).startswith("Volumen estable")
    cambio = pd.Series({"Ana Ruiz Lopez": 10, "Luis Mora Diaz": -5, "Sofia Paz Cruz": 1})
    assert H.quien_subio_y_bajo(cambio) == "Ana Ruiz subió 10 solicitudes; Luis Mora bajó 5"


# ---------------------------------------------------------------------------
# Con bitácoras reales (16 a 28 solicitudes al mes, casi todos los vendedores
# con menos de 5): las barras no pierden el color y los grupos se llaman como
# los estatus que el mes trae.
# ---------------------------------------------------------------------------
CHICA = _df([("Carla Cardenas Ahumada", "FINANCIADO", "SI", 300_000),
             ("Carla Cardenas Ahumada", "RECHAZADO", "SI", 200_000),
             ("Jessica Machuca Roque", "FINANCIADO", "SI", 250_000),
             ("Jessica Machuca Roque", "FINANCIADO", "NO", 250_000),
             ("Suzanne Guerra Rivera", "CONTRAPROPUESTA", "NO", 200_000),
             ("Suzanne Guerra Rivera", "APROBADO", "SI", 200_000)])


def _colores_de_barras(funcion, df, tmp_path, monkeypatch):
    import matplotlib.colors as mc
    vistos = []
    original = G._guardar

    def espia(fig, ruta):
        for ax in fig.axes:
            vistos.extend(mc.to_hex(p.get_facecolor()).upper() for p in ax.patches)
        return original(fig, ruta)
    monkeypatch.setattr(G, "_guardar", espia)
    assert funcion(df, str(tmp_path / "g.png"))
    return vistos


def test_gap_conserva_el_color_con_pocos_casos(tmp_path, monkeypatch):
    """Antes, con menos de 5 solicitudes por vendedor todas las barras de GAP
    salían en gris."""
    for funcion in (G.grafica_gap_por_vendedor_total, G.grafica_gap_financiado_por_vendedor,
                    G.grafica_gap_por_categoria):
        colores = _colores_de_barras(funcion, CHICA, tmp_path, monkeypatch)
        assert G.AZUL.upper() in colores, funcion.__name__
        assert G.ROJO.upper() not in colores, funcion.__name__     # pocos casos: sin alerta


def test_los_grupos_se_llaman_como_los_estatus_del_mes():
    etiquetas = G.etiquetas_grupos(CHICA["Categoria"])
    assert etiquetas[G.TRA] == "Contrapropuesta" and etiquetas[G.PER] == "Rechazado"
    assert G.nota_grupos(CHICA["Categoria"]) == ""          # nada genérico que explicar

    varios = pd.Series(["FINANCIADO", "CONTRAPROPUESTA", "EN PROCESO", "RECHAZADO", "CANCELADO"])
    etiquetas = G.etiquetas_grupos(varios)
    assert etiquetas[G.TRA] == "En trámite" and etiquetas[G.PER] == "No procedió"
    nota = G.nota_grupos(varios)
    assert "«En trámite»" in nota and "Contrapropuesta y En proceso" in nota
    assert "«No procedió»" in nota and "Rechazado y Cancelado" in nota


def test_las_acciones_dicen_que_paso_con_lo_que_no_procedio():
    solo_rechazos = _df([("Ana Ruiz Lopez", "RECHAZADO", "NO", 1)] * 6
                        + [("Ana Ruiz Lopez", "FINANCIADO", "SI", 1)] * 6)
    assert "6 de 12 fueron rechazadas (50%)" in C._accion_perdidas(solo_rechazos)
    mezcla = _df([("Ana Ruiz Lopez", "RECHAZADO", "NO", 1)] * 4
                 + [("Ana Ruiz Lopez", "CANCELADO", "NO", 1)] * 2
                 + [("Ana Ruiz Lopez", "FINANCIADO", "SI", 1)] * 6)
    assert "no procedieron (50%): 4 rechazadas y 2 canceladas" in C._accion_perdidas(mezcla)


def test_avance_con_corte_de_otro_mes_no_habla_de_fin_de_mes():
    assert "antes de fin de mes" in C.acciones_mensual(BASE, "avance")[0]
    assert "antes de fin de mes" not in C.acciones_mensual(BASE, "avance", corte_coherente=False)[0]
