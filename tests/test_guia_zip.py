"""La guía de uso del ZIP: que exista, que la app la encuentre y que no se
quede atrás del catálogo de estatus."""

import os
import re

import pdfplumber
from PIL import Image

from herramientas import estatus
from herramientas.herramienta_relacion_zip import HERRAMIENTA as RELACION
from scripts import guia_zip

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_la_herramienta_apunta_a_archivos_que_existen():
    for ruta in (RELACION.guia, RELACION.guia_vista):
        assert ruta and os.path.isfile(os.path.join(RAIZ, ruta)), ruta
    assert os.path.join(RAIZ, RELACION.guia) == guia_zip.PDF
    assert os.path.join(RAIZ, RELACION.guia_vista) == guia_zip.IMAGEN


def test_pdf_de_dos_paginas_carta_horizontal():
    with pdfplumber.open(guia_zip.PDF) as pdf:
        assert len(pdf.pages) == 2
        assert (round(pdf.pages[0].width), round(pdf.pages[0].height)) == (792, 612)
        texto = " ".join(p.extract_text() or "" for p in pdf.pages)
    assert "Relación de clientes" in texto and "Folio CCK" in texto


def test_la_imagen_es_la_pagina_uno_en_alta_resolucion():
    with Image.open(guia_zip.IMAGEN) as imagen:
        assert imagen.size == (2112, 1632)


def test_la_guia_lista_todos_los_estatus_del_catalogo_con_su_color():
    """Si se agrega un estatus a herramientas/estatus.py, esta prueba falla
    hasta agregarlo también a la guía (guias/guia_zip.html) y regenerarla
    con: python -m scripts.guia_zip"""
    with open(guia_zip.HTML, encoding="utf-8") as f:
        html = f.read()
    bloque = html.split('<div class="estatus">', 1)[1].split("</div>", 1)[0]
    colores_guia = re.findall(r'class="punto" style="background:(#[0-9A-Fa-f]{6})"', bloque)
    colores_catalogo = [estatus.COLOR_CATEGORIA[c.clave] for c in estatus.CATALOGO]
    assert [c.upper() for c in colores_guia] == [c.upper() for c in colores_catalogo]
    assert f"Los {len(estatus.CATALOGO)} nombres de carpeta" in html
