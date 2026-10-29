# -*- coding: utf-8 -*-
"""
Pruebas del validador de CSF.

Dos niveles:

1. SIEMPRE corren (sin datos de nadie): los algoritmos (dígito verificador
   de RFC/CURP, letras del RFC, QR, código postal) y constancias FABRICADAS
   desde cero o fotos, que deben salir como alteradas / no verificables.

2. Corren SOLO si pones CSF reales en tests/muestras_csf/ (esa carpeta está
   en .gitignore porque las constancias traen RFC, CURP y domicilio, y el
   repositorio es público). Con ellas se comprueba que:
     - una CSF auténtica pasa sin FALLAS en las secciones 1 a 3, y
     - cada tipo de alteración conocida (re-guardar, guardado incremental,
       parche encima, rasterizar, cambiar la fecha "fino", cambiar el QR,
       clonar) se detecta.
"""

import glob
import io
import os
import re
import zlib
from datetime import date

import numpy as np
import pytest
from PIL import Image

from herramientas import validar_csf as v
from herramientas.herramienta_validar_csf import ejecutar

MUESTRAS = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "muestras_csf", "*.pdf")))
HOY = date(2026, 10, 28)


# ---------------------------------------------------------------------------
# 1. Algoritmos (datos ficticios / ejemplos públicos)
# ---------------------------------------------------------------------------
def test_digito_rfc_ejemplo_publico_del_sat():
    assert v.digito_rfc("GODE561231GR8") == "8"


def test_digito_rfc_detecta_un_caracter_cambiado():
    assert v.digito_rfc("GODE561231GR7") != "7"


def test_digito_rfc_persona_moral_se_rellena_con_espacio():
    base = "ABC010101AB"
    rfc = base + v.digito_rfc(base + "0")
    assert len(rfc) == 12 and v.digito_rfc(rfc) == rfc[-1]


def test_digito_curp_ida_y_vuelta():
    base = "PELJ900101HCLRPN0"           # CURP ficticia
    curp = base + v.digito_curp(base + "0")
    assert v.PAT_CURP.match(curp)
    otra = curp[:-1] + str((int(curp[-1]) + 1) % 10)
    assert v.digito_curp(otra) != otra[-1]


@pytest.mark.parametrize("paterno, materno, nombres, esperado", [
    ("PEREZ", "LOPEZ", "JUAN", "PELJ"),
    ("DE LA ROSA", "GARCIA", "ANA", "ROGA"),      # partículas fuera
    ("PEREZ", "LOPEZ", "MARIA FERNANDA", "PELF"),  # MARIA compuesto se salta
    ("PEREZ", "", "JUAN", "PEXJ"),                # sin segundo apellido
])
def test_letras_rfc_fisica(paterno, materno, nombres, esperado):
    assert v.letras_rfc_fisica(paterno, materno, nombres) == esperado


@pytest.mark.parametrize("razon, esperado", [
    ("REFRIGERACION DEL NORTE", "RNO"),
    ("CONSTRUCTORA AZUL DE OCCIDENTE", "CAO"),
    ("PANADERIA", "PAN"),
])
def test_letras_rfc_moral(razon, esperado):
    assert v.letras_rfc_moral(razon) == esperado


def test_qr_oficial_y_dominio_clonado():
    ok = v.parse_qr_sat(f"https://{v.DOMINIO_QR}{v.RUTA_QR}?D1=10&D2=1&D3=12345678901_ABC010101AB1")
    assert (ok["dominio"], ok["D1"], ok["folio"], ok["rfc"]) == (v.DOMINIO_QR, "10", "12345678901", "ABC010101AB1")
    falso = v.parse_qr_sat(f"https://siat.sat.gob.mx.validar.site{v.RUTA_QR}?D1=10&D2=1&D3=1_X")
    assert falso["dominio"] != v.DOMINIO_QR


@pytest.mark.parametrize("cp, entidad, esperado", [
    ("28000", "COLIMA", True), ("44100", "JALISCO", True), ("44100", "COLIMA", False),
    ("06600", "CIUDAD DE MEXICO", True), ("55000", "MEXICO", True),
    ("06600", "MEXICO", False), ("2800", "COLIMA", None),
])
def test_cp_por_entidad(cp, entidad, esperado):
    assert v.cp_coincide_entidad(cp, entidad) is esperado


def test_fechas_en_texto():
    assert v._fecha_texto("COLIMA , COLIMA A 05 DE AGOSTO DE 2026") == date(2026, 8, 5)
    assert v._fecha_texto("25/07/2022") == date(2022, 7, 25)


# ---------------------------------------------------------------------------
# 2. Constancias fabricadas (sin datos reales)
# ---------------------------------------------------------------------------
def _fabricada(ruta, productor="Oracle XML Publisher 5.6.2"):
    """Lo que entrega un generador (IA, Word, Canva): se ve como CSF, no lo es."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    base = "PELJ900101AB"
    rfc = base + v.digito_rfc(base + "0")
    c = canvas.Canvas(ruta, pagesize=letter)
    c.setProducer(productor)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(330, 700, "CONSTANCIA DE SITUACIÓN FISCAL")
    c.setFont("Helvetica", 10)
    c.drawString(330, 680, "COLIMA , COLIMA A 20 DE OCTUBRE DE 2026")
    y = 600
    for k, val in [("RFC:", rfc), ("Nombre (s):", "JUAN"), ("Primer Apellido:", "PEREZ"),
                   ("Segundo Apellido:", "LOPEZ"), ("Estatus en el padrón:", "ACTIVO")]:
        c.drawString(40, y, f"{k} {val}")
        y -= 18
    c.save()
    return ruta


def test_constancia_fabricada_se_detecta(tmp_path):
    a = v.analizar_csf(_fabricada(str(tmp_path / "fabricada.pdf")), hoy=HOY)
    assert a.veredicto == "ALTERADA / NO CONFIABLE"
    fallas = {c.clave for c in a.candados if c.estado == v.FALLA}
    # Aunque falsifique el /Producer, no trae QR, código de barras, sello ni /ID igual.
    assert {"1.3", "1.11", "2.1", "2.5", "3.10"} <= fallas


def test_foto_no_es_verificable(tmp_path):
    qr = zxing_qr(f"https://{v.DOMINIO_QR}{v.RUTA_QR}?D1=10&D2=1&D3=1_ABC")
    lienzo = Image.new("RGB", (600, 400), "white")
    lienzo.paste(qr, (40, 40))
    ruta = str(tmp_path / "foto.jpg")
    lienzo.save(ruta, quality=90)
    a = v.analizar_csf(ruta, hoy=HOY)
    assert a.veredicto == "NO VERIFICABLE"
    assert any(c.clave.startswith("2.") and c.estado == v.OK for c in a.candados)


def test_adaptador_genera_un_pdf_por_archivo(tmp_path):
    entrada = _fabricada(str(tmp_path / "0_cliente.pdf"))
    res = ejecutar([entrada], carpeta_salida=str(tmp_path / "salida"),
                   nombre_pdv="PDV Prueba", nombre_analista="Analista")
    salidas, resumen = res["archivos"], res["resumen"]
    assert len(salidas) == 1 and os.path.getsize(salidas[0]) > 3000
    assert open(salidas[0], "rb").read(5) == b"%PDF-"
    # El resumen para la página: datos simples, mismo archivo, sin prefijo "0_".
    assert len(resumen) == 1
    r = resumen[0]
    assert r["archivo"] == "cliente.pdf" and r["reporte"] == os.path.basename(salidas[0])
    assert r["veredicto"] == "ALTERADA / NO CONFIABLE" and r["fallas"] > 0
    assert r["ok"] + r["avisos"] + r["fallas"] <= r["total"] == len(r["candados"])


def test_vista_en_la_pagina_no_truena(tmp_path):
    """Dibuja el resultado con AppTest (sin navegador) para 2 archivos."""
    from streamlit.testing.v1 import AppTest
    entrada = _fabricada(str(tmp_path / "0_a.pdf"))
    otra = _fabricada(str(tmp_path / "1_b.pdf"), productor="Microsoft Word")
    res = ejecutar([entrada, otra], carpeta_salida=str(tmp_path / "s"))

    def app(resumen):
        from herramientas.vista_validar_csf import mostrar
        mostrar(resumen)
    at = AppTest.from_function(app, args=(res["resumen"],)).run(timeout=60)
    assert not at.exception
    assert len(at.metric) >= 4 and at.dataframe


def zxing_qr(texto, lado=150):
    import zxingcpp
    img = zxingcpp.create_barcode(texto, zxingcpp.BarcodeFormat.QRCode).to_image(scale=1)
    return Image.fromarray(np.asarray(img)).convert("RGB").resize((lado, lado), Image.NEAREST)


# ---------------------------------------------------------------------------
# 3. Con CSF reales (solo local, tests/muestras_csf/)
# ---------------------------------------------------------------------------
requiere_muestras = pytest.mark.skipif(not MUESTRAS, reason="sin CSF reales en tests/muestras_csf/")


@requiere_muestras
@pytest.mark.parametrize("ruta", MUESTRAS, ids=lambda r: os.path.basename(r)[:25])
def test_csf_autentica_pasa(ruta):
    a = v.analizar_csf(ruta, hoy=HOY)
    fallas = [(c.clave, c.detalle) for c in a.candados if c.estado == v.FALLA and c.seccion < 4]
    assert not fallas, fallas
    assert a.veredicto in ("SIN INDICIOS DE ALTERACIÓN", "REVISAR MANUALMENTE")


def _variantes(src, carpeta):
    """Las alteraciones conocidas, aplicadas a una CSF real."""
    import pikepdf
    import pypdf
    import pypdfium2 as pdfium
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    crudo = open(src, "rb").read()
    id_original = re.search(rb"/ID \[<([0-9a-f]+)>", crudo).group(1)
    salida = {}

    def experta(cambio, nombre):
        """Edición fina: cambia texto y RESTAURA versión, /ID y Producer."""
        p = pikepdf.open(src)
        for pg in p.pages:
            d = pg.Contents.read_bytes()
            pg.Contents.write(cambio(d))
        tmp = os.path.join(carpeta, "_tmp.pdf")
        p.save(tmp, static_id=True)
        b = open(tmp, "rb").read()
        b = re.sub(rb"%PDF-1\.\d", b"%PDF-1.4", b, count=1)
        b = re.sub(rb"/ID \[ ?<[0-9a-f]+> ?<[0-9a-f]+> ?\]",
                   b"/ID [<" + id_original + b"><" + id_original + b">]", b)
        ruta = os.path.join(carpeta, nombre + ".pdf")
        open(ruta, "wb").write(b)
        salida[nombre] = ruta

    # Fecha de emisión "renovada": se cambia el mes del recuadro "Lugar y
    # Fecha de Emisión" (y nada más; versión, /ID y Producer quedan igual).
    meses = rb"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"

    def renovar_fecha(d):
        i = d.find(b"Lugar y Fecha de Emisi")
        if i < 0:
            return d
        m = re.search(meses, d[i:i + 800])
        nuevo = b"MAYO" if m.group(1) == b"NOVIEMBRE" else b"NOVIEMBRE"
        return d[:i + m.start()] + nuevo + d[i + m.end():]
    experta(renovar_fecha, "fecha_renovada")

    w = pypdf.PdfWriter(clone_from=src)
    w.add_metadata({"/Producer": "iLovePDF"})
    w.write(os.path.join(carpeta, "reguardada.pdf"))
    salida["reguardada"] = os.path.join(carpeta, "reguardada.pdf")

    w = pypdf.PdfWriter(src, incremental=True)
    w.add_metadata({"/ModDate": "D:20261020"})
    w.write(os.path.join(carpeta, "incremental.pdf"))
    salida["incremental"] = os.path.join(carpeta, "incremental.pdf")

    # Parche: recuadro blanco sobre el estatus y "ACTIVO" escrito encima.
    import pdfplumber
    with pdfplumber.open(src) as pdf:
        pg0 = pdf.pages[0]
        w0 = next(w for w in pg0.extract_words() if w["text"] == "ACTIVO")
        alto = float(pg0.height)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFillColorRGB(1, 1, 1)
    c.rect(w0["x0"] - 2, alto - w0["bottom"] - 2, 60, 12, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 8)
    c.drawString(w0["x0"], alto - w0["bottom"] + 1.5, "ACTIVO")
    c.save()
    r = pypdf.PdfReader(src)
    w = pypdf.PdfWriter()
    for i, pg in enumerate(r.pages):
        if i == 0:
            pg.merge_page(pypdf.PdfReader(io.BytesIO(buf.getvalue())).pages[0])
        w.add_page(pg)
    w.write(os.path.join(carpeta, "parche.pdf"))
    salida["parche"] = os.path.join(carpeta, "parche.pdf")

    doc = pdfium.PdfDocument(src)
    imgs = [doc[i].render(scale=2).to_pil().convert("RGB") for i in range(len(doc))]
    imgs[0].save(os.path.join(carpeta, "rasterizada.pdf"), save_all=True, append_images=imgs[1:])
    salida["rasterizada"] = os.path.join(carpeta, "rasterizada.pdf")

    p = pikepdf.open(src)
    for nombre, xo in p.pages[0].Resources.XObject.items():
        if int(xo.get("/Width", 0)) == 150:
            qr = zxing_qr("https://siat-sat-gob.mx" + v.RUTA_QR + "?D1=10&D2=1&D3=1_X")
            xo.write(zlib.compress(qr.tobytes()), filter=pikepdf.Name.FlateDecode)
            break
    p.save(os.path.join(carpeta, "qr_falso.pdf"))
    salida["qr_falso"] = os.path.join(carpeta, "qr_falso.pdf")
    return salida


@requiere_muestras
@pytest.mark.parametrize("variante, candado", [
    ("fecha_renovada", "1.13"), ("reguardada", "1.2"), ("incremental", "1.4"),
    ("parche", "1.9"), ("rasterizada", "1.1"), ("qr_falso", "2.2"),
])
def test_alteraciones_se_detectan(tmp_path, variante, candado):
    rutas = _variantes(MUESTRAS[0], str(tmp_path))
    a = v.analizar_csf(rutas[variante], hoy=HOY)
    assert a.veredicto == "ALTERADA / NO CONFIABLE"
    assert candado in {c.clave for c in a.candados if c.estado == v.FALLA}


@requiere_muestras
def test_clon_en_el_lote(tmp_path):
    rutas = _variantes(MUESTRAS[0], str(tmp_path))
    lote = v.analizar_lote([MUESTRAS[0], rutas["fecha_renovada"]], hoy=HOY)
    for a in lote:
        assert "3.12" in {c.clave for c in a.candados if c.estado == v.FALLA}


# ---------------------------------------------------------------------------
# 4. Consulta al portal del SAT (2.7) con una ficha simulada, sin internet
# ---------------------------------------------------------------------------
def _ficha_sat(*campos):
    """HTML con la misma estructura que la ficha del validador del SAT."""
    filas = "".join(
        f'<tr><td><span style="font-weight: bold;">{k}:</span></td>'
        f'<td role="gridcell" style="text-align:left;">{v}</td></tr>' for k, v in campos)
    return f"<html><body><table>{filas}</table></body></html>"


def _doc_fisica():
    return {"tipo": "fisica", "curp": "PELJ900101HCLRPN05", "nombres": "JUAN", "paterno": "PEREZ",
            "materno": "LOPEZ", "razon_social": "", "estatus": "ACTIVO",
            "inicio_operaciones": "01 DE MARZO DE 2015", "cp": "28000", "entidad": "COLIMA",
            "regimenes": [{"regimen": "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios"}]}


_QR = {"url": "https://siat.sat.gob.mx/x"}
_FICHA_OK = [("CURP", "PELJ900101HCLRPN05"), ("Nombre", "JUAN"), ("Apellido Paterno", "PEREZ"),
             ("Apellido Materno", "LOPEZ"), ("Fecha de Inicio de operaciones", "01-03-2015"),
             ("Situación del contribuyente", "ACTIVO"), ("Entidad Federativa", "COLIMA"), ("CP", "28000"),
             ("Régimen", "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios"),
             ("Fecha de alta", "01-03-2015")]


def test_sat_coincide(monkeypatch):
    monkeypatch.setattr(v, "_descargar_sat", lambda url, timeout=10: _ficha_sat(*_FICHA_OK))
    estado, detalle, _ = v._consultar_sat(_QR, _doc_fisica())
    assert estado == v.OK and "CURP" in detalle and "Régimen" in detalle


def test_sat_detecta_dato_cambiado(monkeypatch):
    """La CURP no cambia con el tiempo: si difiere, el documento se alteró."""
    ficha = [(k, "PELJ900101HCLRPN06" if k == "CURP" else val) for k, val in _FICHA_OK]
    monkeypatch.setattr(v, "_descargar_sat", lambda url, timeout=10: _ficha_sat(*ficha))
    estado, detalle, _ = v._consultar_sat(_QR, _doc_fisica())
    assert estado == v.FALLA and "CURP" in detalle


def test_sat_dato_que_cambia_con_el_tiempo_es_aviso(monkeypatch):
    """La situación sí puede cambiar después de emitida la constancia."""
    ficha = [(k, "SUSPENDIDO" if k.startswith("Situación") else val) for k, val in _FICHA_OK]
    monkeypatch.setattr(v, "_descargar_sat", lambda url, timeout=10: _ficha_sat(*ficha))
    estado, detalle, _ = v._consultar_sat(_QR, _doc_fisica())
    assert estado == v.AVISO and "SUSPENDIDO" in detalle


def test_sat_sin_ficha_es_aviso(monkeypatch):
    monkeypatch.setattr(v, "_descargar_sat", lambda url, timeout=10: "<html><body>Sin datos</body></html>")
    assert v._consultar_sat(_QR, _doc_fisica())[0] == v.AVISO


def test_sat_inalcanzable_dice_el_motivo(monkeypatch):
    import urllib.error

    def falla(url, timeout=10):
        raise urllib.error.URLError(TimeoutError("timed out"))
    monkeypatch.setattr(v, "_descargar_sat", falla)
    estado, detalle, _ = v._consultar_sat(_QR, _doc_fisica())
    assert estado == v.INFO and "no respondió a tiempo" in detalle
