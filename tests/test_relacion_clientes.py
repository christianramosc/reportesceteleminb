"""Relación de clientes: de los PDFs del ZIP al Excel de la bitácora.

Es la primera herramienta del flujo: si lee mal un PDF, todos los reportes
salen mal. Estas pruebas usan PDFs FALSOS (tests/pdfs_bitacora.py) con el
acomodo que espera el lector, y corren con los dos lectores de texto:

  · pdfplumber: el que usa Streamlit Cloud (allá no hay poppler);
  · pdftotext:  el que se usa si está instalado (se salta si no).

Y con varios espacios entre renglones, porque ambos lectores meten una línea
en blanco entre etiqueta y valor cuando el formato viene espaciado: así se
perdían los apellidos y el correo de las personas morales.
"""

import os
import re
import shutil
import zipfile

import pandas as pd
import pytest

import pdfs_bitacora as P
from herramientas import bitacora_zip as bz
from herramientas.ejecucion import ejecutar_aislado
from herramientas.herramienta_relacion_zip import HERRAMIENTA as RELACION
from herramientas.herramienta_resumen_mensual import HERRAMIENTA as RESUMEN

HAY_PDFTOTEXT = shutil.which("pdftotext") is not None

LECTORES = [
    "pdfplumber",
    pytest.param("pdftotext", marks=pytest.mark.skipif(
        not HAY_PDFTOTEXT, reason="pdftotext (poppler) no está instalado")),
]


@pytest.fixture(params=LECTORES)
def lector(request, monkeypatch):
    """Obliga a bitacora_zip a usar ese lector."""
    monkeypatch.setattr(bz, "_hay_pdftotext", lambda: request.param == "pdftotext")
    return request.param


@pytest.fixture(params=[12, 16, 20, 24], ids=lambda p: f"{p}pt")
def interlineado(request, monkeypatch):
    monkeypatch.setattr(P, "INTERLINEADO", request.param)
    return request.param


def _leer(ruta):
    return bz.extraer_texto_pdf(ruta)


# --------------------------------------------------------------- solicitudes
def test_solicitud_persona_fisica(lector, interlineado, tmp_path):
    ruta = P.solicitud_fisica(tmp_path / "s.pdf", "17665240", "JUAN CARLOS", "ARROYO", "BUSTOS",
                              "15/03/1988", "52", "3121234567", "juan.arroyo@ejemplo.com",
                              "ANA RUIZ LOPEZ")
    assert bz.parsear_solicitud(_leer(ruta)) == {
        "tipo_persona": "FÍSICA",
        "folio_cck": "17665240",
        "nombre_completo": "JUAN CARLOS ARROYO BUSTOS",
        "primer_apellido": "ARROYO",
        "segundo_apellido": "BUSTOS",
        "fecha_nacimiento": "15/03/1988",
        "telefono_movil": "3121234567",
        "correo_electronico": "juan.arroyo@ejemplo.com",
        "nombre_vendedor": "ANA RUIZ LOPEZ",
    }


def test_solicitud_con_actividad_empresarial_es_pfae(lector, tmp_path):
    ruta = P.solicitud_fisica(tmp_path / "s.pdf", "17665242", "MARIA", "PEREZ", "GIL",
                              "01/07/1979", "52", "3129876543", "maria@ejemplo.com",
                              "ANA RUIZ LOPEZ", actividad_empresarial=True)
    datos = bz.parsear_solicitud(_leer(ruta))
    assert datos["tipo_persona"] == "PFAE"
    assert datos["nombre_completo"] == "MARIA PEREZ GIL"


def test_solicitud_persona_moral_usa_la_razon_social(lector, interlineado, tmp_path):
    """El formato de persona moral trae más abajo los datos del
    representante legal con Nombre(s) y apellidos: el cliente es la
    empresa, no el representante."""
    ruta = P.solicitud_moral(tmp_path / "s.pdf", "17665241", "TRANSPORTES DEL PACIFICO SA DE CV",
                             "01/02/2015", "312 555 1234", "contacto@transpac.mx",
                             "LUIS MORA DIAZ", representante=("PEDRO", "LUNA", "SOTO"))
    datos = bz.parsear_solicitud(_leer(ruta))
    assert datos == {
        "tipo_persona": "MORAL",
        "folio_cck": "17665241",
        "nombre_completo": "TRANSPORTES DEL PACIFICO SA DE CV",
        "primer_apellido": "",
        "segundo_apellido": "",
        "fecha_nacimiento": "01/02/2015",      # fecha de constitución
        "telefono_movil": "312 555 1234",
        "correo_electronico": "contacto@transpac.mx",
        "nombre_vendedor": "LUIS MORA DIAZ",
    }
    assert "PEDRO" not in datos["nombre_completo"]


def test_solicitud_en_blanco_no_inventa_datos(lector, interlineado, tmp_path):
    """Debajo de una etiqueta sin capturar viene otra etiqueta; antes el
    nombre salía como "P" (de "Primer apellido")."""
    datos = bz.parsear_solicitud(_leer(P.solicitud_fisica_en_blanco(tmp_path / "s.pdf", "17665249")))
    assert datos["folio_cck"] == "17665249"
    assert datos["nombre_completo"] == datos["primer_apellido"] == datos["segundo_apellido"] == ""
    assert datos["fecha_nacimiento"] == ""


# ------------------------------------------------------------ amortizaciones
def test_amortizacion_con_gap(lector, interlineado, tmp_path):
    ruta = P.amortizacion(tmp_path / "a.pdf", "17665240")
    assert bz.parsear_amortizacion(_leer(ruta)) == {
        "folio_cck": "17665240",
        "marca": "MG MOTOR",
        # Nombre largo: el hueco con la columna del seguro se reduce y aun así
        # no debe colarse "Aseguradora: INBURSA".
        "vehiculo": "NEW ZS 1.5T COM TURBO EXCITE AT",
        "modelo_anio": "2026",
        "precio_venta_iva": "$420,000.00",
        "enganche": "$84,000.00",
        "gap_monto": "$9,800.00",
        "tiene_gap": "SI",
        "plazo_meses": "48",
        "tasa_interes_anual": "14.99%",
        "monto_total_financiar": "$358,300.00",
        "mensualidad_minima": "$10,250.00",
        "mensualidad_maxima": "$9,870.00",
        "tipo_seguro": "MULTIANUAL FINANCIADO",
        "aseguradora": "INBURSA",
        "tiene_accesorios": "NO",
        "tiene_garantia_extendida": "SI",
    }


def test_amortizacion_sin_gap_y_contado(lector, tmp_path):
    ruta = P.amortizacion(tmp_path / "a.pdf", "17665241", vehiculo="MG5 EXCITE MT",
                          gap="0.00", tipo_seguro="Contado anual", accesorios="8,500.00",
                          garantia="0.00", plazo="60", tasa="16.50%")
    datos = bz.parsear_amortizacion(_leer(ruta))
    assert datos["vehiculo"] == "MG5 EXCITE MT"
    assert (datos["tiene_gap"], datos["gap_monto"]) == ("NO", "$0.00")
    assert datos["tipo_seguro"] == "CONTADO ANUAL"
    assert datos["tiene_accesorios"] == "SI"
    assert datos["tiene_garantia_extendida"] == "NO"
    assert (datos["plazo_meses"], datos["tasa_interes_anual"]) == ("60", "16.50%")


# --------------------------------------------------------- del ZIP al Excel
def _zip_del_mes(carpeta, nombre="Bitacora OCTUBRE 2026.zip", raiz=""):
    """ZIP como el que arman en el PDV: una carpeta por estatus. Los nombres
    de archivo varían a propósito (mayúsculas, acentos)."""
    origen = carpeta / "armado"
    archivos = {
        "Aprobados/Solicitud_17665240.pdf": lambda r: P.solicitud_fisica(
            r, "17665240", "JUAN CARLOS", "ARROYO", "BUSTOS", "15/03/1988", "52",
            "3121234567", "juan.arroyo@ejemplo.com", "ANA RUIZ LOPEZ"),
        "Aprobados/Amortización_17665240.PDF": lambda r: P.amortizacion(r, "17665240"),
        "Rechazados/SOLICITUD 17665241.pdf": lambda r: P.solicitud_moral(
            r, "17665241", "TRANSPORTES DEL PACIFICO SA DE CV", "01/02/2015",
            "312 555 1234", "contacto@transpac.mx", "LUIS MORA DIAZ"),
        "Rechazados/amortizacion 17665241.pdf": lambda r: P.amortizacion(
            r, "17665241", vehiculo="MG5 EXCITE MT", gap="0.00", tipo_seguro="Contado anual"),
        # Sin amortización: el cliente debe aparecer igual, con los datos de
        # la solicitud y el vehículo vacío.
        "Contrapropuestas/Solicitud_17665242.pdf": lambda r: P.solicitud_fisica(
            r, "17665242", "MARIA", "PEREZ", "GIL", "01/07/1979", "52", "3129876543",
            "maria@ejemplo.com", "LUIS MORA DIAZ", actividad_empresarial=True),
        # No es solicitud ni amortización: se ignora (y se avisa en el log).
        "Contrapropuestas/Contrato_17665242.pdf": lambda r: P.amortizacion(r, "99999999"),
    }
    ruta_zip = carpeta / nombre
    with zipfile.ZipFile(ruta_zip, "w") as z:
        for destino, crear in archivos.items():
            ruta = origen / destino
            ruta.parent.mkdir(parents=True, exist_ok=True)
            crear(ruta)
            z.write(ruta, arcname=(raiz + "/" if raiz else "") + destino)
    return str(ruta_zip)


COLUMNAS_EXCEL = [
    "Folio CCK", "STATUS", "Tipo de Persona", "Nombre Completo", "Fecha de Nacimiento",
    "Teléfono Móvil", "Correo Electrónico", "Nombre del Vendedor", "Marca", "Vehículo",
    "Año Modelo", "Accesorios", "Tipo de Seguro", "Aseguradora", "Precio Venta (c/IVA)",
    "Enganche", "¿Tiene GAP?", "Monto GAP", "Garantía Extendida", "Plazo (meses)",
    "Tasa Interés Anual", "Monto Total a Financiar", "Mensualidad Mínima", "Mensualidad Máxima",
]


def _generar(ruta_zip, tmp_path):
    archivos, log = ejecutar_aislado(RELACION, [ruta_zip], str(tmp_path / "salida"))
    assert len(archivos) == 1
    return archivos[0], log


def test_del_zip_sale_el_excel_de_la_bitacora(lector, tmp_path):
    excel, log = _generar(_zip_del_mes(tmp_path), tmp_path)

    assert re.fullmatch(r"Bitacora_Oct26_al_\d{2}-\d{2}-\d{4}\.xlsx", os.path.basename(excel))
    with pd.ExcelFile(excel) as xls:
        assert xls.sheet_names == ["OCTUBRE 2026"]
        df = xls.parse("OCTUBRE 2026", dtype=str).fillna("")
    assert list(df.columns) == COLUMNAS_EXCEL

    filas = df.set_index("Folio CCK")
    assert sorted(filas.index) == ["17665240", "17665241", "17665242"]

    fisica = filas.loc["17665240"]
    assert fisica["STATUS"] == "APROBADO"
    assert fisica["Nombre Completo"] == "JUAN CARLOS ARROYO BUSTOS"
    assert fisica["Nombre del Vendedor"] == "ANA RUIZ LOPEZ"
    assert fisica["Vehículo"] == "NEW ZS 1.5T COM TURBO EXCITE AT"
    assert (fisica["¿Tiene GAP?"], fisica["Monto GAP"]) == ("SI", "$9,800.00")
    assert fisica["Monto Total a Financiar"] == "$358,300.00"

    moral = filas.loc["17665241"]
    assert (moral["STATUS"], moral["Tipo de Persona"]) == ("RECHAZADO", "MORAL")
    assert moral["Nombre Completo"] == "TRANSPORTES DEL PACIFICO SA DE CV"
    assert (moral["Vehículo"], moral["¿Tiene GAP?"]) == ("MG5 EXCITE MT", "NO")

    sin_amortizacion = filas.loc["17665242"]
    assert (sin_amortizacion["STATUS"], sin_amortizacion["Tipo de Persona"]) == ("CONTRAPROPUESTA", "PFAE")
    assert sin_amortizacion["Nombre Completo"] == "MARIA PEREZ GIL"
    assert sin_amortizacion["Vehículo"] == ""
    assert "SIN AMORTIZACIÓN" in log
    assert "Contrato_17665242.pdf" in log          # el PDF ignorado se reporta

    # Los PDFs extraídos (con datos de clientes) no se quedan en disco.
    assert not [c for c in os.listdir(tmp_path) if c.startswith("_extraido_")]


def test_zip_con_carpeta_raiz_toma_el_mes_de_la_carpeta(lector, tmp_path):
    """ZIP que envuelve todo en una carpeta ("JULIO 2026/Aprobados/...")."""
    excel, _log = _generar(_zip_del_mes(tmp_path, nombre="export.zip", raiz="JULIO 2026"), tmp_path)
    with pd.ExcelFile(excel) as xls:
        assert xls.sheet_names == ["JULIO 2026"]
        assert len(xls.parse("JULIO 2026")) == 3
    assert os.path.basename(excel).startswith("Bitacora_Jul26_al_")


def test_zip_sin_carpetas_de_estatus_avisa(tmp_path):
    ruta_zip = tmp_path / "OCTUBRE.zip"
    with zipfile.ZipFile(ruta_zip, "w") as z:
        z.writestr("Solicitud_1.pdf", b"%PDF-1.4\n")      # suelto, sin carpeta de estatus
    with pytest.raises(RuntimeError, match="subcarpetas de estatus"):
        ejecutar_aislado(RELACION, [str(ruta_zip)], str(tmp_path / "salida"))


def test_el_excel_alimenta_los_demas_reportes(tmp_path):
    """El flujo completo: ZIP -> Excel de la bitácora -> Resumen mensual."""
    excel, _log = _generar(_zip_del_mes(tmp_path), tmp_path)
    archivos, _ = ejecutar_aislado(RESUMEN, [excel], str(tmp_path / "reporte"))
    assert any(a.endswith(".pdf") for a in archivos)
    assert all(os.path.getsize(a) > 5_000 for a in archivos)
