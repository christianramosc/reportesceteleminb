# -*- coding: utf-8 -*-
"""
Registro central de herramientas de la app.

Cómo agregar un nuevo script más adelante (sin tocar streamlit_app.py):

  1. Copia tu script .py (el que ya usas en Colab) a esta carpeta,
     tal cual, con un guard `if __name__ == "__main__": main()` al final
     y una función `main(ruta_local=..., **lo_que_necesites)` como punto
     de entrada (igual que avance_preliminar_original.py y
     comparativo_mensual_original.py).

  2. Crea un archivo herramienta_tu_script.py en esta misma carpeta con:
       - una función ejecutar(rutas_archivos, carpeta_salida="salida", **opciones) -> list[str]
         que llame a tu main() y regrese la ruta del/los archivo(s) generado(s)
       - un objeto HERRAMIENTA = Herramienta(id=..., nombre=..., descripcion=...,
         multiple_archivos=..., tipos_permitidos=[...], ejecutar=ejecutar)
     (usa herramienta_avance_preliminar.py como plantilla — es el más simple)

  3. Impórtalo abajo y agrégalo a la lista REGISTRO.

  streamlit_app.py arma una pestaña con file uploader y botón "Generar" de
  forma automática por cada elemento de REGISTRO.
"""

from .registro import Herramienta  # noqa: F401 (re-exportado para las herramienta_*.py)
from .herramienta_relacion_zip import HERRAMIENTA as _relacion_zip
from .herramienta_avance_preliminar import HERRAMIENTA as _avance_preliminar
from .herramienta_comparativo_mensual import HERRAMIENTA as _comparativo_mensual
from .herramienta_resumen_mensual import HERRAMIENTA as _resumen_mensual

REGISTRO = [
    _relacion_zip,
    _avance_preliminar,
    _comparativo_mensual,
    _resumen_mensual,
]
