"""
Regresiones de la revisión de los PDF (noviembre 2026).

Cada prueba corresponde a un defecto que se vio en un PDF generado:
cifras que no cuadraban, textos dañados o páginas mal partidas. Los
reportes se generan UNA vez por módulo con una bitácora "difícil" (GAP
capturado como "Sí", solicitudes sin vendedor, un nombre con & y < >) y
todas las pruebas leen esos mismos archivos.
"""

import contextlib
import io
import zipfile

import numpy as np
import pandas as pd
import pdfplumber
import pytest
from reportlab.lib.styles import ParagraphStyle

from conftest import construir_bitacora
from herramientas import REGISTRO, pdf_util
from herramientas import comparativo_mensual_original as comp
from herramientas import reporte_base as base
from herramientas import resumen_vendedor_original as vend

RARO = "M&M Autos <Flotillas>"
REPORTES = ["avance_preliminar", "resumen_mensual", "comparativo_mensual"]


def _bitacora_dificil():
    df = construir_bitacora(n=60)
    df["¿Tiene GAP?"] = df["¿Tiene GAP?"].replace({"SI": "Sí"})      # con acento
    df.loc[df.index % 4 == 0, "Nombre del Vendedor"] = RARO          # & y < >
    df.loc[[1, 5, 9, 13, 17, 21], "Nombre del Vendedor"] = np.nan    # sin vendedor
    return df


def _ejecutar(identificador, ruta, destino):
    herramienta = next(h for h in REGISTRO if h.id == identificador)
    comparativo = identificador == "comparativo_mensual"
    entradas = [ruta, ruta] if comparativo else [ruta]
    opciones = {"nombres_meses": ["SEPTIEMBRE 2026", "OCTUBRE 2026"]} if comparativo else {}
    with contextlib.redirect_stdout(io.StringIO()):
        return herramienta.ejecutar(entradas, carpeta_salida=str(destino), **opciones)


def _leer(ruta_pdf):
    """(textos por página, metadatos)."""
    with pdfplumber.open(ruta_pdf) as pdf:
        return [p.extract_text() or "" for p in pdf.pages], dict(pdf.metadata)


@pytest.fixture(scope="module")
def generados(tmp_path_factory):
    """{reporte: (textos por página, metadatos)} de la bitácora difícil."""
    carpeta = tmp_path_factory.mktemp("mejoras")
    ruta = carpeta / "bitacora.xlsx"
    _bitacora_dificil().to_excel(ruta, index=False, sheet_name="OCTUBRE 2026")
    salida = {}
    for identificador in REPORTES:
        rutas = _ejecutar(identificador, str(ruta), carpeta / identificador)
        salida[identificador] = _leer(next(r for r in rutas if r.endswith(".pdf")))
    rutas = _ejecutar("resumen_vendedor", str(ruta), carpeta / "resumen_vendedor")
    salida["_zip_vendedores"] = next(r for r in rutas if r.endswith(".zip"))
    return salida


# ---------------------------------------------------------------------------
# 1. GAP capturado con acento
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("limpiar", [base.limpiar_datos, comp.limpiar_datos, vend.limpiar_datos],
                         ids=["mensuales", "comparativo", "individual"])
def test_gap_con_acento_cuenta_como_gap(limpiar):
    """"Sí" se contaba como SIN GAP en tres de los cuatro reportes: la
    portada marcaba 0% de GAP en rojo."""
    crudo = construir_bitacora(n=20)
    crudo["¿Tiene GAP?"] = ["Sí", "sí ", "SI", "si", "No"] * 4
    with contextlib.redirect_stdout(io.StringIO()):
        df = limpiar(crudo)
    assert set(df["¿Tiene GAP?"]) == {"SI", "NO"}
    assert int((df["¿Tiene GAP?"] == "SI").sum()) == 16


def test_gap_con_acento_llega_a_la_portada(generados):
    for identificador in REPORTES:
        portada = generados[identificador][0][0]
        assert "GAP EN FINANCIADOS" in portada
        assert "8 sin GAP de 8" not in portada, f"{identificador}: el GAP volvió a salir en 0"


# ---------------------------------------------------------------------------
# 2. Solicitudes sin vendedor
# ---------------------------------------------------------------------------
def test_solicitudes_sin_vendedor_no_desaparecen_del_total():
    """Antes la portada decía 60 solicitudes y TOTAL EQUIPO sumaba 54."""
    with contextlib.redirect_stdout(io.StringIO()):
        df = base.limpiar_datos(_bitacora_dificil())
        tabla = base.analisis_por_vendedor(df)
    assert int(tabla["Total"].sum()) == len(df) == 60
    assert int(tabla.loc[base.SIN_VENDEDOR, "Total"]) == 6
    # ...pero no cuenta como una persona más del equipo.
    assert base.contar_vendedores(tabla) == len(tabla) - 1


def test_el_pdf_avisa_de_las_solicitudes_sin_vendedor(generados):
    texto = "\n".join(generados["resumen_mensual"][0])
    assert "TOTAL EQUIPO 60" in texto
    assert "6 solicitudes no traen vendedor capturado" in texto


def test_sin_vendedor_no_genera_reporte_individual(generados):
    with zipfile.ZipFile(generados["_zip_vendedores"]) as zf:
        nombres = zf.namelist()
    assert not any(base.SIN_VENDEDOR in n for n in nombres)


# ---------------------------------------------------------------------------
# 3. Nombres con & y < >
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("texto, esperado", [
    ("M&M Autos <Flotillas>", "M&amp;M Autos &lt;Flotillas&gt;"),
    ("<b>A&B</b>&nbsp;x", "<b>A&amp;B</b>&nbsp;x"),
    ('<font color="#191970"><b>3</b></font> de 5<br/>', '<font color="#191970"><b>3</b></font> de 5<br/>'),
    ("sin nada raro", "sin nada raro"),
])
def test_marcado_seguro(texto, esperado):
    assert pdf_util.marcado_seguro(texto) == esperado
    assert pdf_util.marcado_seguro(esperado) == esperado      # idempotente


def test_nombre_con_ampersand_sale_completo_en_los_parrafos(generados):
    """Salía "M&M; Autos" y se perdía "<Flotillas>"."""
    for identificador in REPORTES:
        texto = "\n".join(generados[identificador][0])
        assert "M&M;" not in texto, identificador
    resumen = "\n".join(generados["resumen_mensual"][0])
    assert f"{RARO} (" in resumen.replace("\n", " ")       # mención dentro de un párrafo


# ---------------------------------------------------------------------------
# 4. Excel sin solicitudes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("identificador", REPORTES + ["resumen_vendedor"])
def test_excel_sin_filas_da_un_mensaje_claro(identificador, tmp_path):
    """Antes: "max() iterable argument is empty"."""
    ruta = tmp_path / "0_vacia.xlsx"
    construir_bitacora(n=4).head(0).to_excel(ruta, index=False, sheet_name="OCTUBRE 2026")
    with pytest.raises(ValueError, match="'vacia.xlsx' no trae ninguna solicitud"):
        _ejecutar(identificador, str(ruta), tmp_path / "salida")


# ---------------------------------------------------------------------------
# 5, 11 y 12. Maquetación
# ---------------------------------------------------------------------------
def _renglones_de_cuerpo(texto_pagina):
    return [r for r in texto_pagina.split("\n")
            if r.strip() and "Elaborado por" not in r and not r.startswith("Página")]


def test_ningun_titulo_queda_solo_al_pie_de_la_pagina(generados):
    """"Resumen Ejecutivo" se quedaba al pie de la portada con media hoja en
    blanco, y "Reporte Detallado" a media página del Comparativo."""
    for identificador in REPORTES:
        for n, pagina in enumerate(generados[identificador][0], 1):
            renglones = _renglones_de_cuerpo(pagina)
            assert renglones, f"{identificador}: la página {n} salió vacía"
            ultimo = renglones[-1]
            assert not ultimo.startswith(("Resumen Ejecutivo", "Reporte Detallado",
                                          "Conclusiones y Factores")), \
                f"{identificador}, página {n}: el título quedó huérfano"


def test_pagina_x_de_y(generados):
    for identificador in REPORTES:
        paginas = generados[identificador][0]
        for n, texto in enumerate(paginas, 1):
            assert f"Página {n} de {len(paginas)}" in texto, f"{identificador}, página {n}"


def test_metadatos_del_pdf(generados):
    """Vacíos, el lector de PDF mostraba "untitled" y "anonymous"."""
    for identificador in REPORTES:
        meta = generados[identificador][1]
        assert "MG Colima PYD" in meta.get("Title", ""), identificador
        assert meta.get("Author") == "Christian Ramos", identificador
        assert "Bitácora" in meta.get("Subject", ""), identificador


@pytest.mark.parametrize("valor", ["$2.43 M", "$16.49 M", "$123.45 M", "100%"])
def test_cifra_lateral_cabe_en_un_renglon(valor):
    """"$16.49 M" se partía en dos renglones ("$16.49" / "M")."""
    ancho = pdf_util.ANCHO_LATERAL - 1.9 * 28.3465
    piezas = pdf_util._flowables_lateral(
        [{"etiqueta": "MONTO FINANCIADO", "valor": valor, "nota": "ticket de $305,328"}],
        alto=600, ancho=ancho)
    cifra = next(p for p in piezas
                 if isinstance(p, pdf_util.Parrafo) and p.style.name.startswith("LatNum"))
    cifra.wrap(ancho, 600)
    assert len(cifra.blPara.lines) == 1


def test_tabla_alta_se_deja_partir_y_la_corta_se_amarra():
    """Una tabla larga amarrada a su título no cabía en lo que quedaba de la
    hoja y se iba entera a la siguiente, dejando media página en blanco."""
    from reportlab.platypus import KeepTogether, Table

    def seccion(renglones):
        h2 = ParagraphStyle("H2MG")
        cuerpo = ParagraphStyle("CuerpoMG")
        tabla = Table([["a", "b"]] * renglones)
        return [pdf_util.Parrafo("Sección", h2), pdf_util.Parrafo("Texto.", cuerpo),
                KeepTogether(tabla)], tabla

    elementos, tabla = seccion(30)
    salida = pdf_util._para_pdf(elementos)
    assert tabla in salida, "la tabla alta debe quedar fuera del KeepTogether"
    assert isinstance(salida[0], pdf_util._SaltoSiNoCabe)

    elementos, tabla = seccion(5)
    salida = pdf_util._para_pdf(elementos)
    assert tabla not in salida and isinstance(salida[-1], KeepTogether)
    assert salida[-2].keepWithNext, "el párrafo viaja con su tabla corta"


# ---------------------------------------------------------------------------
# 17. Resumen por Vendedor, de punta a punta
# ---------------------------------------------------------------------------
def test_resumen_por_vendedor_de_punta_a_punta(generados, tmp_path):
    """No estaba en test_reportes.py: un PDF por asesor dentro del ZIP, con
    sus gráficas, su numeración y sus metadatos."""
    with zipfile.ZipFile(generados["_zip_vendedores"]) as zf:
        nombres = sorted(zf.namelist())
        zf.extractall(tmp_path)
    assert len(nombres) == 4 and all(n.endswith(" - Octubre 2026.pdf") for n in nombres)
    assert any(n.startswith("M&M Autos Flotillas") for n in nombres)

    for nombre in nombres:
        ruta = tmp_path / nombre
        assert ruta.read_bytes().count(b"/Subtype /Image") >= 3, f"{nombre}: faltan gráficas"
        paginas, meta = _leer(str(ruta))
        assert all(f"Página {n} de {len(paginas)}" in t for n, t in enumerate(paginas, 1))
        assert meta.get("Title", "").startswith("Resumen Mensual")
        texto = "\n".join(paginas)
        assert "Modelo + Solicitado" not in texto and "MODELOS + SOLICITADOS" not in texto
        assert "M&M;" not in texto


def test_limpieza_individual_parte_de_la_compartida():
    """El Resumen por Vendedor tenía su propia copia de la limpieza; ahora
    solo agrega lo suyo (y quita las filas sin vendedor)."""
    crudo = _bitacora_dificil()
    with contextlib.redirect_stdout(io.StringIO()):
        comun = base.limpiar_datos(crudo)
        individual = vend.limpiar_datos(crudo)
    assert len(comun) == 60 and len(individual) == 54
    assert base.SIN_VENDEDOR not in set(individual["Nombre del Vendedor"])
    con_vendedor = comun[comun["Nombre del Vendedor"] != base.SIN_VENDEDOR]
    pd.testing.assert_series_equal(
        con_vendedor["¿Tiene GAP?"].reset_index(drop=True),
        individual["¿Tiene GAP?"].reset_index(drop=True))
