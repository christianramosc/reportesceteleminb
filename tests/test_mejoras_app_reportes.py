"""
Vista previa con columnas faltantes, vendedores por lista, descarga en ZIP,
conversión por modelo, ticket y GAP por vendedor, comparación contra el mes
anterior, historial del vendedor y tabla de desempeño con equipos grandes.
"""

import contextlib
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pdfplumber
import pytest
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Table
from streamlit.testing.v1 import AppTest

from conftest import construir_bitacora
from herramientas import REGISTRO, lateral, vista_bitacora
from herramientas import reporte_base as base

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _excel_bytes(df, hoja):
    memoria = io.BytesIO()
    df.to_excel(memoria, index=False, sheet_name=hoja)
    return memoria.getvalue()


def _guardar(df, ruta, hoja):
    df.to_excel(ruta, index=False, sheet_name=hoja)
    return str(ruta)


def _ejecutar(identificador, rutas, destino, **opciones):
    herramienta = next(h for h in REGISTRO if h.id == identificador)
    registro = io.StringIO()
    with contextlib.redirect_stdout(registro):
        resultado = herramienta.ejecutar(rutas, carpeta_salida=str(destino), **opciones)
    return resultado, registro.getvalue()


def _texto(ruta_pdf):
    with pdfplumber.open(ruta_pdf) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _septiembre():
    """Un mes anterior claramente peor: menos solicitudes y sin GAP."""
    df = construir_bitacora(n=45)
    df.loc[df.index % 3 == 0, "STATUS"] = "RECHAZADO"
    df["¿Tiene GAP?"] = "NO"
    return df


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def _elegir(at, identificador):
    herramienta = next(h for h in REGISTRO if h.id == identificador)
    at.radio(key="herramienta_activa").set_value(herramienta).run()


# ---------------------------------------------------------------------------
# 4. Columnas faltantes en la vista previa
# ---------------------------------------------------------------------------
def test_revisar_dice_que_se_pierde_por_cada_columna_que_falta():
    df = construir_bitacora(n=12).drop(columns=["¿Tiene GAP?", "Vehículo", "Correo Electrónico"])
    revision = vista_bitacora.revisar(df)
    assert revision["filas"] == 12 and revision["conteo"]
    faltantes = dict(revision["faltantes"])
    assert set(faltantes) == {"¿Tiene GAP?", "Vehículo"}
    assert "GAP" in faltantes["¿Tiene GAP?"] and "modelos" in faltantes["Vehículo"]
    # Las que no cambian ninguna cifra van aparte, sin alarmar.
    assert revision["otras"] == ["Correo Electrónico"]


def test_revisar_no_reporta_nada_en_una_bitacora_completa():
    revision = vista_bitacora.revisar(construir_bitacora(n=12))
    assert revision["faltantes"] == [] and revision["otras"] == []


def test_revisar_lista_los_vendedores_como_salen_en_el_reporte():
    df = construir_bitacora(n=12)
    df.loc[0, "Nombre del Vendedor"] = "  ana   RUIZ "
    df.loc[1, "Nombre del Vendedor"] = np.nan
    vendedores = vista_bitacora.revisar(df)["vendedores"]
    assert vendedores == ["Ana Ruiz", "Diego Lara", "Luis Mora", "Sofia Paz"]


def test_la_app_avisa_de_las_columnas_que_faltan(app):
    _elegir(app, "resumen_mensual")
    df = construir_bitacora(n=12).drop(columns=["¿Tiene GAP?"])
    app.file_uploader(key="uploader_resumen_mensual").set_value(
        ("Bitacora.xlsx", _excel_bytes(df, "OCTUBRE 2026"), XLSX)).run()
    assert not app.exception, app.exception
    avisos = " ".join(w.value for w in app.warning)
    assert "Faltan columnas" in avisos and "¿Tiene GAP?" in avisos and "seguro GAP" in avisos


# ---------------------------------------------------------------------------
# 5. Vendedores por lista de selección
# ---------------------------------------------------------------------------
def test_los_vendedores_se_eligen_de_una_lista_con_los_del_excel(app):
    _elegir(app, "resumen_vendedor")
    lista = app.multiselect(key="vend_resumen_vendedor")
    assert lista.disabled and list(lista.options) == []       # aún no hay archivo

    app.file_uploader(key="uploader_resumen_vendedor").set_value(
        ("Bitacora.xlsx", _excel_bytes(construir_bitacora(n=24), "OCTUBRE 2026"), XLSX)).run()
    lista = app.multiselect(key="vend_resumen_vendedor")
    assert not lista.disabled
    assert list(lista.options) == ["Ana Ruiz", "Diego Lara", "Luis Mora", "Sofia Paz"]

    lista.set_value(["Luis Mora"]).run()
    app.button(key="generar_resumen_vendedor").click().run()
    assert not app.exception and not app.error, [e.value for e in app.error]
    archivos = dict(app.session_state["resultado_resumen_vendedor"]["archivos"])
    with zipfile.ZipFile(io.BytesIO(archivos["Vendedores_Oct26.zip"])) as zf:
        assert zf.namelist() == ["Luis Mora - Octubre 2026.pdf"]


# ---------------------------------------------------------------------------
# 12. Conversión por modelo
# ---------------------------------------------------------------------------
def _df_modelos():
    return pd.DataFrame({
        "Vehículo": ["MG 5"] * 6 + ["MG ZS"] * 3 + ["MG HS"],
        "Categoria": ["FINANCIADO"] + ["RECHAZADO"] * 5 + ["FINANCIADO"] * 2 + ["APROBADO"] * 2,
        "Monto Total a Financiar": [100.0] * 10,
    })


def test_conversion_por_modelo():
    tabla = base.analisis_por_modelo(_df_modelos())
    assert list(tabla.index) == ["MG 5", "MG ZS", "MG HS"]            # por solicitudes
    assert tabla.loc["MG ZS", ["Solicitudes", "Financiados"]].tolist() == [3, 2]
    assert tabla.loc["MG ZS", "% Financiado"] == pytest.approx(66.7)
    assert tabla.loc["MG ZS", "Monto Financiado ($)"] == 200.0
    # El más solicitado (MG 5) no es el que más se financia (MG ZS).
    assert base.modelo_mas_financiado(tabla) == ("MG ZS", 2, 3, pytest.approx(66.7))


def test_tabla_de_modelos_agrupa_los_que_no_caben_en_otros():
    filas, anchos = base.filas_tabla_modelos(base.analisis_por_modelo(_df_modelos()), maximo=2)
    assert [f[0] for f in filas] == ["Modelo", "MG 5", "MG ZS", "Otros (1 modelos)", "TOTAL"]
    assert filas[-1][1:4] == ["10", "3", "30.0%"]
    assert sum(anchos) == pytest.approx(16.0)


def test_sin_financiados_no_hay_modelo_mas_financiado():
    df = _df_modelos().assign(Categoria="RECHAZADO")
    assert base.modelo_mas_financiado(base.analisis_por_modelo(df)) is None


# ---------------------------------------------------------------------------
# 13. Ticket promedio y monto GAP por vendedor
# ---------------------------------------------------------------------------
def test_ticket_promedio_y_monto_gap_por_vendedor():
    df = pd.DataFrame({
        "Nombre del Vendedor": ["Ana Ruiz"] * 3 + ["Luis Mora"] * 2,
        "Categoria": ["FINANCIADO", "FINANCIADO", "RECHAZADO", "APROBADO", "RECHAZADO"],
        "Monto Total a Financiar": [300_000.0, 200_000.0, 999.0, 150_000.0, 1.0],
        "¿Tiene GAP?": ["SI", "NO", "SI", "SI", "NO"],
        "Monto GAP": [12_000.0, 0.0, 12_000.0, 12_000.0, 0.0],
    })
    with contextlib.redirect_stdout(io.StringIO()):
        tabla = base.analisis_por_vendedor(df)
    assert tabla.loc["Ana Ruiz", "Ticket Promedio ($)"] == 250_000
    assert pd.isna(tabla.loc["Luis Mora", "Ticket Promedio ($)"])     # sin créditos no hay ticket
    # Solo el GAP de créditos FINANCIADOS: el de la rechazada no cuenta.
    assert tabla.loc["Ana Ruiz", "Monto GAP Financiado ($)"] == 12_000

    filas, nota, _ = base.filas_tabla_ticket_gap(tabla)
    assert [f[0] for f in filas] == ["Vendedor", "Ana Ruiz", "TOTAL EQUIPO"]
    assert filas[1][1:] == ["2", "$500,000", "$250,000", "1", "$12,000"]
    assert "1 vendedor sin créditos financiados" in nota


# ---------------------------------------------------------------------------
# 16. Contra el mes anterior
# ---------------------------------------------------------------------------
def test_comparar_meses():
    antes = pd.DataFrame({"Categoria": ["FINANCIADO"] + ["RECHAZADO"] * 9,
                          "Monto Total a Financiar": [100_000.0] * 10,
                          "¿Tiene GAP?": ["NO"] * 10})
    ahora = pd.DataFrame({"Categoria": ["FINANCIADO"] * 3 + ["RECHAZADO"] * 9,
                          "Monto Total a Financiar": [100_000.0] * 12,
                          "¿Tiene GAP?": ["SI"] * 12})
    filas = {f["clave"]: f for f in lateral.comparar_meses(ahora, antes)}
    assert (filas["solicitudes"]["anterior"], filas["solicitudes"]["actual"],
            filas["solicitudes"]["cambio"]) == ("10", "12", "+2 (+20%)")
    assert filas["conversion"]["cambio"] == "+15.0 pts" and filas["conversion"]["mejora"] is True
    assert filas["monto"]["cambio"] == "+200%"
    assert filas["ticket"]["cambio"] == "sin cambio" and filas["ticket"]["mejora"] is None
    assert filas["gap"]["cambio"] == "+100.0 pts"


def test_resumen_mensual_con_el_mes_anterior(tmp_path):
    actual = _guardar(construir_bitacora(n=60), tmp_path / "0_oct.xlsx", "OCTUBRE 2026")
    anterior = _guardar(_septiembre(), tmp_path / "1_sep.xlsx", "SEPTIEMBRE 2026")
    rutas, registro = _ejecutar("resumen_mensual", [actual], tmp_path / "s",
                                rutas_anteriores=[anterior])
    assert "Mes anterior para comparar: sep.xlsx" in registro
    texto = _texto(next(r for r in rutas if r.endswith(".pdf")))
    assert "COMPARACIÓN CON EL MES ANTERIOR" in texto
    assert "Frente a Septiembre 2026" in texto
    assert "Solicitudes 45 60 +15 (+33%)" in texto
    assert "vs. septiembre" in texto                  # en las cifras de la portada


def test_resumen_mensual_sin_mes_anterior_no_cambia(tmp_path):
    actual = _guardar(construir_bitacora(n=60), tmp_path / "0_oct.xlsx", "OCTUBRE 2026")
    rutas, _ = _ejecutar("resumen_mensual", [actual], tmp_path / "s")
    texto = _texto(next(r for r in rutas if r.endswith(".pdf")))
    assert "MES ANTERIOR" not in texto and "vs." not in texto
    # Lo nuevo que sí va siempre: conversión por modelo y ticket por vendedor.
    assert "más se financia" in texto
    assert "Ticket promedio = monto financiado entre créditos financiados" in texto


def test_la_app_manda_el_mes_anterior_al_reporte(app):
    _elegir(app, "resumen_mensual")
    app.file_uploader(key="uploader_resumen_mensual").set_value(
        ("Octubre.xlsx", _excel_bytes(construir_bitacora(n=30), "OCTUBRE 2026"), XLSX)).run()
    app.file_uploader(key="anteriores_resumen_mensual").set_value(
        ("Septiembre.xlsx", _excel_bytes(_septiembre(), "SEPTIEMBRE 2026"), XLSX)).run()
    app.button(key="generar_resumen_mensual").click().run()
    assert not app.exception and not app.error, [e.value for e in app.error]
    assert "Mes anterior para comparar: Septiembre.xlsx" in \
        app.session_state["resultado_resumen_mensual"]["log"]


# ---------------------------------------------------------------------------
# 15. Historial del vendedor
# ---------------------------------------------------------------------------
def test_resumen_por_vendedor_con_historial(tmp_path):
    actual = _guardar(construir_bitacora(n=60), tmp_path / "0_oct.xlsx", "OCTUBRE 2026")
    septiembre = _guardar(_septiembre(), tmp_path / "1_sep.xlsx", "SEPTIEMBRE 2026")
    agosto = construir_bitacora(n=30)
    agosto = _guardar(agosto[agosto["Nombre del Vendedor"] != "Ana Ruiz"],
                      tmp_path / "2_ago.xlsx", "AGOSTO 2026")
    repetido = _guardar(construir_bitacora(n=10), tmp_path / "3_oct.xlsx", "OCTUBRE 2026")

    # Se suben desordenados y con un archivo del mismo mes del reporte.
    rutas, registro = _ejecutar("resumen_vendedor", [actual], tmp_path / "s",
                                rutas_anteriores=[septiembre, repetido, agosto])
    assert "Historial: Agosto 2026, Septiembre 2026, Octubre 2026" in registro
    assert "Octubre 2026 no es anterior al mes del reporte" in registro

    with zipfile.ZipFile(next(r for r in rutas if r.endswith(".zip"))) as zf:
        zf.extractall(tmp_path / "pdfs")
    texto = _texto(tmp_path / "pdfs" / "Ana Ruiz - Octubre 2026.pdf")
    assert "TU HISTORIAL" in texto and "FRENTE AL MES ANTERIOR" in texto
    assert "Frente a Septiembre 2026, tus solicitudes pasaron de 12 a 15 (+3, +25%)" \
        in texto.replace("\n", " ")
    assert "vs. septiembre" in texto
    # Ana no tuvo solicitudes en agosto: el mes aparece, sin inventarle cifras.
    assert "Agosto 2026 0 — —" in texto


def test_resumen_por_vendedor_sin_historial_no_cambia(tmp_path):
    actual = _guardar(construir_bitacora(n=24), tmp_path / "0_oct.xlsx", "OCTUBRE 2026")
    rutas, _ = _ejecutar("resumen_vendedor", [actual], tmp_path / "s",
                         vendedores_incluir=["Ana Ruiz"])
    with zipfile.ZipFile(next(r for r in rutas if r.endswith(".zip"))) as zf:
        zf.extractall(tmp_path / "pdfs")
    texto = _texto(tmp_path / "pdfs" / "Ana Ruiz - Octubre 2026.pdf")
    assert "HISTORIAL" not in texto and "MES ANTERIOR" not in texto
    assert "Ticket promedio por crédito" in texto


# ---------------------------------------------------------------------------
# 18. Tabla de desempeño con muchos vendedores
# ---------------------------------------------------------------------------
def test_encabezados_de_vendedor_cortos_y_unicos():
    cortos = base.encabezados_vendedores([
        "Jessica Elizabeth Machuca Roque", "Jessica Esther Lopez Diaz",
        "Luis Mora", "Casa", base.SIN_VENDEDOR])
    assert cortos["Luis Mora"] == "Luis M." and cortos["Casa"] == "Casa"
    assert cortos[base.SIN_VENDEDOR] == "Sin vendedor"
    assert cortos["Jessica Elizabeth Machuca Roque"] == "Jessica E. M."
    assert len(set(cortos.values())) == len(cortos)


def _tablas_volteadas(nombres):
    df = pd.DataFrame({
        "Nombre del Vendedor": [n for n in nombres for _ in range(3)],
        "Categoria": ["FINANCIADO", "APROBADO", "RECHAZADO"] * len(nombres),
    })
    with contextlib.redirect_stdout(io.StringIO()):
        tabla_vendedor = base.analisis_por_vendedor(df)

    def tabla_simple(data, col_widths=None, compacta=False, **_):
        return Table(data, colWidths=col_widths)

    salida = base.tablas_desempeno_volteadas(
        tabla_vendedor, ["FINANCIADO", "APROBADO", "RECHAZADO"], tabla_simple,
        ParagraphStyle("NotaMG"))
    return [f for f in salida if isinstance(f, Table)], salida


def test_equipo_grande_parte_la_tabla_y_abrevia_los_nombres():
    nombres = [f"Nombre{i} Apellido Largo Compuesto" for i in range(18)]
    tablas, salida = _tablas_volteadas(nombres)
    assert len(tablas) == 3
    encabezados = [t._cellvalues[0] for t in tablas]
    assert all(len(e) <= 8 for e in encabezados)
    assert encabezados[0][1] == "Nombre0 A." and encabezados[-1][-1] == "Total<br/>equipo"
    # Solo la última parte lleva el total, y suma a los 18.
    assert tablas[-1]._cellvalues[1][-1] == 18 and len(encabezados[0]) == 7
    nota = salida[-1].text
    assert "3 partes" in nota and "Nombre0 A. = Nombre0 Apellido Largo Compuesto" in nota


def test_equipo_chico_conserva_los_nombres_completos():
    tablas, salida = _tablas_volteadas(["Ana Ruiz", "Luis Mora", "Sofia Paz", "Diego Lara"])
    assert len(tablas) == 1 and salida == tablas          # sin nota de abreviaturas
    encabezado = tablas[0]._cellvalues[0]
    assert encabezado[0] == "Estatus" and encabezado[-1] == "Total"
    assert sorted(encabezado[1:-1]) == ["Ana Ruiz", "Diego Lara", "Luis Mora", "Sofia Paz"]
