"""Adaptador de validar_nomina_sat.py para el registro. Herramienta PRIVADA:
pide usuario y contraseña (acceso.py) porque procesa nóminas de clientes."""

import os

from . import nombres_archivo as _nombres
from . import validar_nomina_sat as _v
from .registro import Herramienta


def ejecutar(rutas_archivos, carpeta_salida="salida", **_opciones):
    os.makedirs(carpeta_salida, exist_ok=True)
    archivos, resumen = _v.main(
        list(rutas_archivos), carpeta_salida,
        nombres=[_nombres.subido(r) for r in rutas_archivos],
    )
    return {"archivos": archivos, "resumen": resumen}


def mostrar_resumen(resumen):
    from .vista_validar_nomina import mostrar   # importa streamlit solo en la app
    mostrar(resumen)


HERRAMIENTA = Herramienta(
    id="validar_nomina",
    nombre="Validar nómina SAT",
    descripcion=(
        "Valida los recibos de nómina ante el SAT, toma los de los últimos 2 meses, "
        "suma el ingreso bruto por mes y revisa la vigencia de 10 días hábiles."
    ),
    multiple_archivos=True,
    tipos_permitidos=["pdf", "xml", "zip"],
    ejecutar=ejecutar,
    mostrar_resumen=mostrar_resumen,
    ayuda_archivo=(
        "Sube los recibos en PDF o XML, sueltos o en un ZIP. Si tienes el XML, súbelo: "
        "trae el total exacto del CFDI (indispensable en tarjetones del IMSS)."
    ),
    icono=":material/receipt_long:",
    nombre_corto="Validar nómina SAT",
    requiere_acceso=True,
)
