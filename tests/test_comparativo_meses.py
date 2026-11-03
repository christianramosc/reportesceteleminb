"""El comparativo no debe descartar en silencio un archivo con el mes repetido.

Los datos se guardan por mes: con dos Excel de la misma hoja (el avance y el
cierre de septiembre), el segundo pisaba al primero y el reporte salía como
si solo se hubiera subido uno.
"""

import pytest

from conftest import construir_bitacora
from herramientas import nombres_archivo
from herramientas.ejecucion import ejecutar_aislado
from herramientas.herramienta_comparativo_mensual import HERRAMIENTA as COMPARATIVO


def _excel(carpeta, nombre, hoja, semilla):
    ruta = carpeta / nombre
    construir_bitacora(semilla=semilla).to_excel(ruta, index=False, sheet_name=hoja)
    return str(ruta)


def test_dos_archivos_del_mismo_mes_se_detienen_con_aviso(tmp_path):
    rutas = [
        _excel(tmp_path, "0_Avance_Sep.xlsx", "SEPTIEMBRE 2026", 1),
        _excel(tmp_path, "1_Cierre_Sep.xlsx", "SEPTIEMBRE 2026", 2),
        _excel(tmp_path, "2_Cierre_Oct.xlsx", "OCTUBRE 2026", 3),
    ]
    with pytest.raises(ValueError) as error:
        ejecutar_aislado(COMPARATIVO, rutas, str(tmp_path / "salida"))

    mensaje = str(error.value)
    assert "Septiembre 2026 (Avance_Sep.xlsx, Cierre_Sep.xlsx)" in mensaje
    assert "Etiquetas de mes" in mensaje
    assert "Octubre" not in mensaje


def test_etiquetas_distintas_permiten_el_mismo_archivo_dos_veces(tmp_path):
    """El caso legítimo sigue funcionando: misma hoja, etiquetas distintas
    (así lo usa también tests/test_reportes.py)."""
    rutas = [
        _excel(tmp_path, "0_a.xlsx", "SEPTIEMBRE 2026", 1),
        _excel(tmp_path, "1_b.xlsx", "SEPTIEMBRE 2026", 2),
    ]
    archivos, _log = ejecutar_aislado(COMPARATIVO, rutas, str(tmp_path / "salida"),
                                      nombres_meses=["AGOSTO 2026", "SEPTIEMBRE 2026"])
    assert any(r.endswith(".pdf") for r in archivos)


@pytest.mark.parametrize("ruta, esperado", [
    ("/tmp/x/0_Bitacora.xlsx", "Bitacora.xlsx"),
    ("12_Csf 2026.pdf", "Csf 2026.pdf"),
    ("Bitacora.xlsx", "Bitacora.xlsx"),
])
def test_nombre_subido_quita_el_prefijo_de_la_app(ruta, esperado):
    assert nombres_archivo.subido(ruta) == esperado
