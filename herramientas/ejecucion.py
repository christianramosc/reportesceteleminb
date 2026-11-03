"""Corre una herramienta a la vez, para que los reportes no se mezclen.

Streamlit atiende a todos los usuarios en UN solo proceso de Python, así que
los módulos de reportes son compartidos. Y esos módulos guardan cosas a nivel
de módulo:

  · el PDV y el implant (SUBTITULO_EMPRESA, NOMBRE_ANALISTA), que cada
    adaptador herramienta_*.py sobrescribe antes de generar;
  · la carpeta de gráficas, con nombres fijos (g01_status.png, ...);
  · los colores de estatus (estatus.COLOR_CATEGORIA) y las figuras de
    matplotlib;
  · sys.stdout: contextlib.redirect_stdout lo cambia para TODO el proceso.

Si dos personas generaban al mismo tiempo, el PDF de una salía con el PDV,
las gráficas o el log de la otra (comprobado: tests/test_ejecucion.py). Con
el candado, las corridas se forman: la segunda espera a que termine la
primera. Cuando los reportes reciban todo por parámetro, el candado sobra.
"""

import contextlib
import glob
import io
import shutil
import threading

_CANDADO = threading.Lock()

# Las gráficas intermedias se escriben junto al script (reporte_base y el
# comparativo usan carpetas fijas) y llevan nombres de vendedores.
_PATRON_GRAFICAS = "graficas_temp_*"


def ejecutar_aislado(herramienta, rutas_archivos, carpeta_salida,
                     al_esperar=None, **opciones):
    """Ejecuta herramienta.ejecutar() con el candado tomado.

    Devuelve (resultados, log): lo que regrese la herramienta y todo lo que
    imprimió durante la corrida.

    al_esperar: función sin argumentos que se llama una sola vez si otra
        corrida tiene el candado, antes de esperar (la app la usa para
        avisar que el reporte está en fila).
    """
    if not _CANDADO.acquire(blocking=False):
        if al_esperar:
            al_esperar()
        _CANDADO.acquire()
    try:
        registro = io.StringIO()
        with contextlib.redirect_stdout(registro):
            resultados = herramienta.ejecutar(
                rutas_archivos, carpeta_salida=carpeta_salida, **opciones
            )
        return resultados, registro.getvalue()
    finally:
        # Dentro del candado: borrar fuera de él podía llevarse las gráficas
        # de una corrida que todavía estaba armando su PDF.
        for temporal in glob.glob(_PATRON_GRAFICAS):
            shutil.rmtree(temporal, ignore_errors=True)
        _CANDADO.release()
