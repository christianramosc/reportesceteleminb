"""Relación de clientes: qué PDFs de cada carpeta de estatus se leen.

Antes se perdían sin aviso los .PDF en mayúsculas y los nombres con acento
("Amortización_..."), y el cliente desaparecía de la bitácora.
"""

import unicodedata

from herramientas import bitacora_zip


def _crear(carpeta, *nombres):
    for nombre in nombres:
        (carpeta / nombre).write_bytes(b"%PDF-1.4\n")


def _nombres(rutas):
    return sorted(unicodedata.normalize("NFC", r.rsplit("/", 1)[-1]) for r in rutas)


def test_clasifica_sin_importar_mayusculas_ni_acentos(tmp_path):
    amortizacion_mac = unicodedata.normalize("NFD", "Amortización_2.pdf")   # así nombra macOS
    _crear(tmp_path,
           "Solicitud_1.PDF", "Amortización_1.pdf", "solicitud 2.pdf", amortizacion_mac,
           "AMORTIZACION_3.Pdf", "Contrato_4.pdf",
           "._Solicitud_1.pdf",            # basura de macOS: se salta
           "notas.txt")
    (tmp_path / "subcarpeta.pdf").mkdir()  # una carpeta no es un PDF

    solicitudes, amortizaciones, ignorados = bitacora_zip.clasificar_pdfs(str(tmp_path))

    assert _nombres(solicitudes) == ["Solicitud_1.PDF", "solicitud 2.pdf"]
    assert _nombres(amortizaciones) == ["AMORTIZACION_3.Pdf", "Amortización_1.pdf",
                                        "Amortización_2.pdf"]
    assert _nombres(ignorados) == ["Contrato_4.pdf"]


def test_avisa_los_pdfs_ignorados_en_el_log(tmp_path, capsys):
    _crear(tmp_path, "Contrato_4.pdf")
    registros = bitacora_zip.procesar_carpeta(str(tmp_path), "APROBADO")
    assert registros == []
    assert "PDFs ignorados" in capsys.readouterr().out
