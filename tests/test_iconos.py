# -*- coding: utf-8 -*-
"""Pruebas de herramientas/iconos.py."""
import os

from herramientas import iconos as I
from herramientas import pdf_util

TITULOS_ACTUALES = [
    "Comparativo Financiero por Categoría", "Comparativo con el Equipo", "Desempeño por Vendedor",
    "Distribución de Solicitudes por Estatus", "Distribución de tus Solicitudes por Estatus",
    "Focos de atención", "Lectura del periodo", "Modelo más solicitado", "Modelos + Solicitados",
    "Modelos de Vehículo Más Solicitados (Periodo)", "Monto Colocado por Vendedor",
    "Panorama Financiero por Mes", "Panorama del mes", "Panorama financiero", "Panorama general",
    "Seguro GAP", "Tasa de Conversión por Mes", "Tu posición en el equipo", "Tus Solicitudes del Mes",
    "Vendedores destacados", "Volumen y Categorías de Cierre por Mes",
]


def test_todo_icono_asignado_existe_como_archivo():
    """Si alguien agrega una regla con un icono que no copió a iconos/, esa
    sección saldría sin icono en silencio. Esta prueba lo impide."""
    nombres = {n for _, n in I._SECCIONES + I._CIFRAS}
    nombres |= {I._SECCION_GENERICA, I._CIFRA_GENERICA, "shield-alert"}
    faltan = [n for n in nombres if not os.path.exists(os.path.join(I._CARPETA, f"{n}.svg"))]
    assert not faltan, faltan


def test_los_titulos_actuales_tienen_icono_especifico():
    genericos = [t for t in TITULOS_ACTUALES if I.nombre_seccion(t) == I._SECCION_GENERICA]
    assert not genericos, genericos


def test_titulo_nuevo_recibe_icono_generico():
    assert I.nombre_seccion("Una sección que aún no existe") == I._SECCION_GENERICA


def test_gap_en_alerta_cambia_de_escudo():
    assert I.nombre_cifra("GAP EN FINANCIADOS", alerta=True) == "shield-alert"
    assert I.nombre_cifra("GAP EN FINANCIADOS", alerta=False) == "shield-check"


def test_icono_inexistente_no_truena():
    assert I.icono("no-existe", 12, "#000000") is None


def test_barra_se_arma_aunque_fallen_los_iconos(monkeypatch):
    """Un icono nunca debe impedir que salga un reporte."""
    monkeypatch.setattr(pdf_util._iconos, "icono", lambda *a, **k: None)
    barra = pdf_util.barra_seccion("Seguro GAP", 3)
    assert barra._ncols == 1


def test_licencia_incluida():
    assert os.path.exists(os.path.join(I._CARPETA, "LICENSE-lucide.txt"))


def test_barra_recalcula_su_ancho_al_pasar_a_pagina_interior():
    """Regresión: una barra medida primero en la columna angosta de la
    portada (12.3 cm) se dibujaba con ese ancho en las páginas interiores
    (16.8 cm), porque ReportLab sobrescribía la especificación "*"."""
    from reportlab.lib.units import cm
    barra = pdf_util.barra_seccion("Seguro GAP", 3)
    barra.wrap(12.3 * cm, 20 * cm)
    assert abs(barra.wrap(16.8 * cm, 20 * cm)[0] - 16.8 * cm) < 1


def test_la_portada_siempre_queda_en_la_pagina_1(tmp_path):
    """Regresión: la columna lateral se desbordó al agregar los iconos y
    empujó la portada a la página 2. Con muchas cifras y notas largas, el
    título del reporte debe seguir en la página 1."""
    import pypdf
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from herramientas import lateral
    cifras = [{"etiqueta": f"CIFRA NÚMERO {i}", "valor": "123%", "alerta": i % 2 == 0,
               "nota": "una nota bastante larga que ocupa varios renglones en la columna"}
              for i in range(12)]
    ruta = str(tmp_path / "p.pdf")
    elementos = [lateral.bloque_cifras(cifras), Paragraph("TITULO DE PORTADA", getSampleStyleSheet()["Title"])]
    pdf_util.construir_con_lateral(SimpleDocTemplate(ruta), elementos, lambda c, d: None)
    assert "TITULO DE PORTADA" in pypdf.PdfReader(ruta).pages[0].extract_text()
