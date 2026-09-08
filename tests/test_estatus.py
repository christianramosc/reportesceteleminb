# -*- coding: utf-8 -*-
"""
Pruebas del catálogo de estatus (herramientas/estatus.py).

Es el archivo que más se toca: cada estatus nuevo se agrega ahí. También es
donde un error pasa más desapercibido, porque el reporte se genera igual —
solo que con las solicitudes contadas en la categoría equivocada.
"""

import pytest

from herramientas import estatus as est


# ---------------------------------------------------------------------------
# Clasificación: el texto del Excel -> la categoría correcta
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("texto, esperado", [
    # Variantes de mayúsculas, plurales y acentos que sí aparecen en la bitácora
    ("FINANCIADO", "FINANCIADO"),
    ("financiados", "FINANCIADO"),
    ("Financiada", "FINANCIADO"),
    ("  APROBADO  ", "APROBADO"),
    ("AUTORIZADO", "APROBADO"),
    ("Contra Propuesta", "CONTRAPROPUESTA"),
    ("EN REVISIÓN", "EN REVISION"),
    ("revision", "EN REVISION"),
    ("Documentacion Adicional", "DOCUMENTACION ADICIONAL"),
    ("DOCUMENTACIÓN ADICIONAL", "DOCUMENTACION ADICIONAL"),
    ("EN VALIDACION", "VALIDACION INTERNA"),
    ("Excepción", "EXCEPCIONES"),
    ("EN SONDEO", "SONDEO"),
    ("EN ANALISIS", "ANALISIS"),
    ("CANCELADOS", "CANCELADO"),
])
def test_clasifica_sinonimos(texto, esperado):
    assert est.clasificar_status(texto) == esperado


@pytest.mark.parametrize("texto", ["NO FINANCIABLE", "NO FINANCIADOS",
                                    "no financiada", "NO FINANCIAMIENTO"])
def test_no_financiable_no_se_confunde_con_financiado(texto):
    """El riesgo más caro del catálogo: que 'NO FINANCIADOS' caiga en
    FINANCIADO e infle la métrica principal del reporte."""
    assert est.clasificar_status(texto) == "NO FINANCIABLE"


def test_analisis_es_categoria_propia():
    """'ANALISIS' fue sinónimo de EN REVISION hasta que se volvió su propio
    estatus. Si alguien lo devuelve a los sinónimos, ANÁLISIS desaparece."""
    assert est.clasificar_status("ANALISIS") == "ANALISIS"
    assert est.clasificar_status("EN REVISION") == "EN REVISION"


@pytest.mark.parametrize("vacio", ["", "   ", "nan", "N/A", "-", None])
def test_celdas_vacias(vacio):
    assert est.clasificar_status(vacio) == est.CLAVE_SIN_ESTATUS


def test_estatus_desconocido_es_categoria_propia():
    """No debe caer en CONTRAPROPUESTA, que era el bug original."""
    assert est.clasificar_status("ALGO QUE NADIE ESPERA") == "ALGO QUE NADIE ESPERA"


# ---------------------------------------------------------------------------
# Invariantes del catálogo: lo que debe cumplirse al agregar un estatus
# ---------------------------------------------------------------------------
def test_claves_unicas():
    claves = [c.clave for c in est.CATALOGO]
    assert len(claves) == len(set(claves))


def test_ningun_sinonimo_repetido_entre_categorias():
    """Un sinónimo en dos categorías significa que una se come a la otra
    en silencio, según cuál quede primero en el catálogo."""
    visto = {}
    duplicados = []
    for categoria in est.CATALOGO:
        for sinonimo in categoria.sinonimos:
            if sinonimo in visto:
                duplicados.append(f"{sinonimo!r}: {visto[sinonimo]} y {categoria.clave}")
            visto[sinonimo] = categoria.clave
    assert not duplicados, "Sinónimos repetidos -> " + "; ".join(duplicados)


def test_colores_distinguibles():
    """Dos categorías con el mismo color son indistinguibles en la dona."""
    colores = [c.color.upper() for c in est.CATALOGO]
    assert len(colores) == len(set(colores))


def test_la_clave_es_su_propio_sinonimo():
    """Si no, el estatus escrito tal cual en el Excel no se reconoce."""
    for categoria in est.CATALOGO:
        assert categoria.clave in categoria.sinonimos, categoria.clave


def test_todas_tienen_grupo_valido():
    validos = {est.CERRADA_POSITIVA, est.ABIERTA, est.CERRADA_NEGATIVA}
    for categoria in est.CATALOGO:
        assert categoria.grupo in validos, categoria.clave


def test_no_financiable_no_cuenta_como_convertible():
    """NO FINANCIABLE, RECHAZADO y CANCELADO son cierres definitivos: no
    deben aparecer en 'aún pueden convertirse en FINANCIADAS'."""
    abiertas = est.claves_por_grupo(est.ABIERTA)
    for cerrada in ("NO FINANCIABLE", "RECHAZADO", "CANCELADO", "FINANCIADO"):
        assert cerrada not in abiertas


# ---------------------------------------------------------------------------
# Textos que arma el catálogo para los reportes
# ---------------------------------------------------------------------------
def test_frase_enumerada_no_grita_la_conjuncion():
    """El bug de 'EN REVISIÓN Y PENDIENTE y algunas RECHAZADAS'."""
    frase = est.frase_enumerada(["APROBADO", "PENDIENTE"], mayusculas=True)
    assert " y " in frase and " Y " not in frase


def test_frase_desglose_lleva_verbo():
    """Sin verbo, el Panorama general queda como una lista agramatical."""
    frase = est.frase_desglose({"FINANCIADO": 13, "APROBADO": 5}, 66)
    assert "quedaron" in frase and "están" in frase


def test_frase_desglose_con_total_cero():
    assert est.frase_desglose({}, 0) == ""


def test_esta_catalogado():
    assert est.esta_catalogado("FINANCIADO")
    assert not est.esta_catalogado("INVENTADO")


def test_registrar_categorias_es_idempotente():
    """La app corre en un proceso de larga vida: registrar dos veces el
    mismo estatus no debe duplicarlo en el orden de graficado."""
    antes = list(est.ORDEN_CATEGORIAS)
    est.registrar_categorias(["ESTATUS DE PRUEBA"])
    est.registrar_categorias(["ESTATUS DE PRUEBA"])
    assert est.ORDEN_CATEGORIAS.count("ESTATUS DE PRUEBA") == 1
    assert est.COLOR_CATEGORIA.get("ESTATUS DE PRUEBA")
    # deja el catálogo como estaba, para no afectar a las demás pruebas
    est.ORDEN_CATEGORIAS[:] = antes
    est.COLOR_CATEGORIA.pop("ESTATUS DE PRUEBA", None)
