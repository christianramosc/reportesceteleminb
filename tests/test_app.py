"""La app de punta a punta, sin navegador (streamlit.testing.v1.AppTest)."""

import io
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import construir_bitacora
from herramientas import REGISTRO

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def _elegir(at, identificador):
    herramienta = next(h for h in REGISTRO if h.id == identificador)
    at.radio(key="herramienta_activa").set_value(herramienta).run()


def _subir(at, identificador, archivos):
    at.file_uploader(key=f"uploader_{identificador}").set_value(archivos).run()
    assert not at.exception, at.exception


def _excel(hojas):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as libro:
        for nombre, df in hojas.items():
            df.to_excel(libro, sheet_name=nombre, index=False)
    return buffer.getvalue()


def _descargas(at):
    return at.get("download_button")


def test_cambiar_de_archivo_borra_el_resultado_anterior(app):
    """Antes las descargas del archivo anterior seguían en pantalla hasta
    volver a generar: era fácil bajar el reporte equivocado."""
    app.session_state["resultado_relacion_zip"] = {
        "archivos": [("Bitacora_Sep26.xlsx", b"datos viejos")],
        "log": "", "resumen": None, "fecha": "01/10/2026 · 10:00",
    }
    app.run()
    assert len(_descargas(app)) == 1

    _subir(app, "relacion_zip", ("Octubre.zip", b"PK\x05\x06" + b"\0" * 18, "application/zip"))

    assert "resultado_relacion_zip" not in app.session_state
    assert len(_descargas(app)) == 0


def test_genera_un_reporte_desde_la_app(app):
    """Recorre el flujo real (subir, Generar, descargar) con el candado de
    herramientas/ejecucion.py de por medio."""
    _elegir(app, "resumen_mensual")
    _subir(app, "resumen_mensual",
           ("Bitacora.xlsx", _excel({"OCTUBRE 2026": construir_bitacora()}), XLSX))

    app.button(key="generar_resumen_mensual").click().run()

    assert not app.exception, app.exception
    assert not app.error, [e.value for e in app.error]
    nombres = sorted(nombre for nombre, _ in app.session_state["resultado_resumen_mensual"]["archivos"])
    assert [n.rsplit(".", 1)[-1] for n in nombres] == ["docx", "pdf", "png", "png", "xlsx"]
    assert len(_descargas(app)) == 5


def test_vista_previa_avisa_si_hay_varias_hojas(app):
    _elegir(app, "resumen_mensual")
    _subir(app, "resumen_mensual", ("Bitacora.xlsx", _excel({
        "OCTUBRE 2026": construir_bitacora(),
        "Hoja2": pd.DataFrame({"Notas": ["apoyo"]}),
    }), XLSX))

    avisos = " ".join(i.value for i in app.info)
    assert "varias hojas" in avisos and "OCTUBRE 2026" in avisos


@pytest.mark.parametrize("herramienta", REGISTRO, ids=[h.id for h in REGISTRO])
def test_cada_herramienta_muestra_los_campos_que_declara(app, herramienta):
    """Qué pide cada página lo declara la herramienta (registro.py); la app
    ya no decide con listas de ids. Si alguien agrega una herramienta, esta
    prueba la recorre sola."""
    _elegir(app, herramienta.id)
    assert not app.exception, app.exception

    def hay_texto(etiqueta):
        return any(t.label == etiqueta for t in app.text_input)

    assert hay_texto("Nombre del PDV") == herramienta.pide_pdv_e_implant
    assert hay_texto("Implant") == herramienta.pide_pdv_e_implant
    assert any("fecha de corte" in t.label for t in app.toggle) == herramienta.pide_fecha_corte
    areas = {a.label for a in app.text_area}
    assert ("Un vendedor por línea" in areas) == herramienta.pide_vendedores
    assert ("Un mes por línea" in areas) == herramienta.pide_etiquetas_mes
    # El menú usa el icono y el nombre corto declarados.
    opciones_menu = app.radio(key="herramienta_activa").options
    assert any(herramienta.icono in o and (herramienta.nombre_corto or "") in o for o in opciones_menu)
