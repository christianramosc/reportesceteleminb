# -*- coding: utf-8 -*-
"""Fecha y hora LOCALES (Colima / centro de México).

Por qué existe
--------------
Streamlit Cloud (y Colab) corren en servidores con el reloj en UTC. México
está 6 horas atrás de UTC, así que todo lo que se generaba después de las
6:00 pm salía con la fecha del día siguiente: un reporte hecho el 13 de
octubre a las 6 pm decía "14/10/2026".

Todo el proyecto toma la fecha de aquí (hoy() / ahora()) en lugar de
date.today() o datetime.now(), que dependen del reloj del servidor.

Si la base de zonas horarias no está disponible, se usa UTC-6 fijo: desde
2022 México ya no cambia de horario en verano (salvo algunos municipios
fronterizos), así que para Colima es exacto.
"""

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ZONA = ZoneInfo("America/Mexico_City")
except Exception:  # sin base de zonas horarias en el servidor
    ZONA = timezone(timedelta(hours=-6), "CST")


def ahora():
    """Fecha y hora locales, sin zona (para formatear y restar sin sorpresas)."""
    return datetime.now(ZONA).replace(tzinfo=None)


def hoy():
    """Fecha local de hoy."""
    return ahora().date()
