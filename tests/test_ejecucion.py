"""Dos personas generando al mismo tiempo no deben mezclar sus reportes.

Antes del candado de herramientas/ejecucion.py, con dos corridas en paralelo
el PDF de una salía con el PDV y el implant de la otra: los adaptadores
sobrescriben constantes de módulo que comparten todas las sesiones de
Streamlit.
"""

import os
import threading
import types

import pdfplumber

from conftest import construir_bitacora
from herramientas import ejecucion
from herramientas.herramienta_resumen_mensual import HERRAMIENTA as RESUMEN


def _portada(ruta_pdf):
    with pdfplumber.open(ruta_pdf) as pdf:
        return pdf.pages[0].extract_text()


def test_corridas_simultaneas_no_se_mezclan(tmp_path):
    pdvs = ["PDV Norte", "PDV Sur"]
    salida = {}
    errores = []
    arranque = threading.Barrier(len(pdvs))   # que empiecen juntas

    def corre(i, pdv):
        carpeta = tmp_path / f"corrida{i}"
        carpeta.mkdir()
        bitacora = carpeta / "bitacora.xlsx"
        construir_bitacora(semilla=i).to_excel(bitacora, index=False,
                                               sheet_name="OCTUBRE 2026")
        try:
            arranque.wait()
            resultados, log = ejecucion.ejecutar_aislado(
                RESUMEN, [str(bitacora)], str(carpeta / "salida"),
                nombre_pdv=pdv, nombre_analista=f"Implant {pdv}",
            )
            salida[pdv] = (resultados, log)
        except Exception as e:      # el hilo no puede fallar la prueba solo
            errores.append(e)

    hilos = [threading.Thread(target=corre, args=(i, p)) for i, p in enumerate(pdvs)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, errores
    for pdv, otro in (pdvs, pdvs[::-1]):
        resultados, log = salida[pdv]
        portada = _portada(next(r for r in resultados if r.endswith(".pdf")))
        assert pdv in portada and f"Implant {pdv}" in portada
        assert otro not in portada, f"El PDF de {pdv} trae datos de {otro}"
        assert log.strip(), "cada corrida debe conservar su propio log"


def test_avisa_cuando_otra_corrida_tiene_el_turno(tmp_path):
    herramienta = types.SimpleNamespace(
        ejecutar=lambda rutas, carpeta_salida, **_: print("listo") or ["x.pdf"])
    avisos = []
    resultado = {}

    ejecucion._CANDADO.acquire()            # otra corrida en curso
    try:
        hilo = threading.Thread(target=lambda: resultado.update(
            r=ejecucion.ejecutar_aislado(herramienta, [], str(tmp_path),
                                         al_esperar=lambda: avisos.append(1))))
        hilo.start()
        hilo.join(timeout=2)
        assert hilo.is_alive(), "debe esperar mientras el candado está tomado"
        assert avisos == [1]
    finally:
        ejecucion._CANDADO.release()
    hilo.join(timeout=10)

    assert resultado["r"] == (["x.pdf"], "listo\n")
    assert not ejecucion._CANDADO.locked(), "el candado debe quedar libre"


def test_suelta_el_candado_aunque_la_herramienta_truene(tmp_path):
    def truena(rutas, carpeta_salida, **_):
        raise ValueError("archivo malo")

    herramienta = types.SimpleNamespace(ejecutar=truena)
    try:
        ejecucion.ejecutar_aislado(herramienta, [], str(tmp_path))
    except ValueError:
        pass
    assert not ejecucion._CANDADO.locked()
    assert not [c for c in os.listdir(".") if c.startswith("graficas_temp_")]
