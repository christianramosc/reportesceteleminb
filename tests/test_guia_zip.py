"""La guía para armar el ZIP se genera con el catálogo real de estatus."""

import pdfplumber

from herramientas import estatus
from scripts import guia_zip


def test_guia_lista_las_carpetas_del_catalogo(tmp_path):
    ruta = guia_zip.dibujar(str(tmp_path / "guia.pdf"))
    with pdfplumber.open(ruta) as pdf:
        texto = " ".join(p.extract_text() or "" for p in pdf.pages)
    assert "ZIP" in texto
    # Cada estatus del catálogo debe aparecer como carpeta en la guía.
    faltan = [c for c in estatus.ORDEN_CATEGORIAS[:5] if guia_zip.nombre_de_carpeta(c) not in texto]
    assert not faltan, faltan
