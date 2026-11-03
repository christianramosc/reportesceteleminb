"""Un Excel con más de una hoja no debe tronar los reportes.

cargar_archivo() preguntaba con input() qué hoja usar. En el servidor de
Streamlit no hay teclado: Avance, Resumen y Por vendedor tronaban con
EOFError en cuanto el libro traía una segunda hoja. Ahora se usa la primera,
como el comparativo.
"""

import pandas as pd
import pytest

from conftest import construir_bitacora
from herramientas import REGISTRO
from herramientas.ejecucion import ejecutar_aislado


@pytest.fixture
def bitacora_dos_hojas(tmp_path):
    ruta = tmp_path / "bitacora_dos_hojas.xlsx"
    with pd.ExcelWriter(ruta) as libro:
        construir_bitacora().to_excel(libro, sheet_name="OCTUBRE 2026", index=False)
        pd.DataFrame({"Notas": ["hoja de apoyo"]}).to_excel(libro, sheet_name="Hoja2", index=False)
    return str(ruta)


@pytest.mark.parametrize("identificador",
                         ["avance_preliminar", "resumen_mensual", "resumen_vendedor"])
def test_excel_con_dos_hojas_usa_la_primera(identificador, bitacora_dos_hojas, tmp_path):
    herramienta = next(h for h in REGISTRO if h.id == identificador)
    rutas, log = ejecutar_aislado(herramienta, [bitacora_dos_hojas], str(tmp_path / "salida"))

    assert rutas, "no se generó ningún archivo"
    assert "Se usa la primera: 'OCTUBRE 2026'" in log
    # El periodo de los archivos sale de la primera hoja (Oct26), no de Hoja2.
    assert all("Oct26" in r for r in rutas), rutas
