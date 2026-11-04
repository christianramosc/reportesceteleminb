"""Corre una herramienta a la vez, para que los reportes no se mezclen.

Streamlit atiende a todos los usuarios en UN solo proceso de Python, así que
los módulos de reportes son compartidos. El PDV, el implant y la carpeta de
gráficas ya viajan como parámetro (fase 3), pero sigue habiendo estado
compartido:

  · los colores de estatus (estatus.COLOR_CATEGORIA), que cada corrida
    reparte según los estatus de SU bitácora;
  · matplotlib.pyplot, que guarda "la figura actual" para todo el proceso y
    no está hecho para dibujar desde dos hilos a la vez;
  · sys.stdout: contextlib.redirect_stdout lo cambia para TODO el proceso.

Antes del candado, con dos personas generando al mismo tiempo, el PDF de una
salía con datos de la otra (tests/test_ejecucion.py). Con el candado, las
corridas se forman: la segunda espera a que termine la primera (unos 5 s).
Quitarlo exigiría dibujar las ~30 gráficas sin pyplot; con pocos usuarios no
vale la pena.
"""

import contextlib
import io
import threading

_CANDADO = threading.Lock()


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
        _CANDADO.release()
