# -*- coding: utf-8 -*-
"""Definición del objeto Herramienta que usa el registro central (__init__.py)."""

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Herramienta:
    id: str                      # identificador único, usado como key de Streamlit
    nombre: str                  # título de la pestaña / botón
    descripcion: str             # texto explicativo para el usuario final
    multiple_archivos: bool      # True si acepta varios archivos a la vez
    tipos_permitidos: List[str]  # extensiones que acepta el file_uploader, ej. ["xlsx"]
    # ejecutar(rutas_archivos, carpeta_salida="salida", **opciones) -> lista de rutas de salida
    ejecutar: Callable[..., List[str]]
    ayuda_archivo: Optional[str] = None  # texto de ayuda bajo el uploader (opcional)
