# -*- coding: utf-8 -*-
"""Fecha local y nombres cortos para los archivos que entrega la app.

FECHA: Streamlit Cloud corre en UTC, seis horas adelante de Colima. Después
de las 6:00 pm los reportes salían con la fecha del día siguiente. La app
fija la zona horaria al arrancar (ver usar_hora_local) para que todos los
date.today() / datetime.now() del proyecto den la hora de Colima.

NOMBRES: antes eran del estilo "Avance_Preliminar_Datos_20261013_0000.xlsx"
(el "_0000" siempre salía en ceros). Ahora cada reporte usa un nombre base
corto y sus archivos solo cambian de extensión:
    Avance_13oct26.pdf / .docx / .xlsx / .png
"""

import os
import time
from datetime import datetime, timedelta, timezone

# Colima usa la hora del centro de México: UTC-6 todo el año (México quitó
# el horario de verano en 2022).
ZONA_COLIMA = timezone(timedelta(hours=-6))

_MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"]


def usar_hora_local():
    """Pone el proceso en la hora de Colima. Se llama una vez al iniciar la app.

    Se usa la cadena POSIX "CST6" (UTC-6 fijo, sin horario de verano) porque
    no depende de que el servidor tenga instalada la base de zonas horarias.
    """
    os.environ["TZ"] = "CST6"
    if hasattr(time, "tzset"):
        time.tzset()


def hoy():
    """Fecha de hoy en Colima, sin importar la zona del servidor."""
    return datetime.now(ZONA_COLIMA).date()


def marca_fecha(fecha=None):
    """'13oct26' para el 13 de octubre de 2026."""
    f = fecha or hoy()
    return f"{f.day:02d}{_MESES_CORTOS[f.month - 1]}{f:%y}"


def mes_corto(nombre_mes, anio):
    """'Sep26' a partir de ('septiembre', 2026)."""
    return f"{str(nombre_mes).strip()[:3].title()}{str(anio)[-2:]}"
