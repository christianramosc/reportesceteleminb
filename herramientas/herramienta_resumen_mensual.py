"""Adaptador del Resumen Mensual (reporte_mensual.py, modo "cierre") para el registro."""

import os
import pandas as pd

from . import reporte_base as _base
from .reporte_mensual import generar_reporte_pdf
from .docx_reportes import generar_docx_resumen
from .ficha_resumen import fichas_ambos_formatos, ficha_mensual
from .libros_analisis import libro_mensual
from .config import DatosReporte
from .registro import Herramienta
from . import nombres_archivo as _nombres


def _mes_anterior(rutas_anteriores):
    """(bitácora limpia, nombre del mes) del archivo opcional del mes
    anterior, o (None, "") si no se subió."""
    if not rutas_anteriores:
        return None, ""
    ruta = rutas_anteriores[0]
    with pd.ExcelFile(ruta) as xls:
        hoja = xls.sheet_names[0]
    print(f"Mes anterior para comparar: {_nombres.subido(ruta)} (hoja '{hoja}')")
    return _base.limpiar_datos(_base.cargar_archivo(ruta_local=ruta)), str(hoja).strip().title()


def ejecutar(rutas_archivos, carpeta_salida="salida", nombre_pdv=None,
             nombre_analista=None, rutas_anteriores=None, **_opciones):
    datos = DatosReporte.desde_opciones(nombre_pdv, nombre_analista)
    nombre_pdv, nombre_analista = datos.pdv, datos.analista

    os.makedirs(carpeta_salida, exist_ok=True)

    # El mes anterior se limpia ANTES que el actual: la limpieza reparte los
    # colores de estatus, y deben quedar los de la bitácora del reporte.
    df_anterior, mes_anterior = _mes_anterior(rutas_anteriores)

    df_crudo = _base.cargar_archivo(ruta_local=rutas_archivos[0])
    df = _base.limpiar_datos(df_crudo)
    resumen = _base.resumen_general(df)
    tabla_vendedor = _base.analisis_por_vendedor(df)
    tabla_categoria = _base.analisis_financiero_por_categoria(df)

    # Nombre corto: Resumen_Jul26 (+ .pdf, .docx, _datos.xlsx, fichas)
    with pd.ExcelFile(rutas_archivos[0]) as xls:
        hoja = xls.sheet_names[0]
    base = f"Resumen_{_nombres.periodo_corto(hoja)}"
    ruta_pdf = os.path.join(carpeta_salida, f"{base}.pdf")

    # El PDF deja aquí sus flowables y el Word se construye con ESOS mismos
    # elementos, para que ambos documentos digan exactamente lo mismo.
    elementos_pdf = []
    generar_reporte_pdf(
        df, resumen, tabla_vendedor, tabla_categoria, "cierre",
        nombre_archivo=ruta_pdf,
        recolectar_elementos=elementos_pdf, hoja=hoja, datos=datos,
        df_anterior=df_anterior, mes_anterior=mes_anterior,
    )

    ruta_docx = generar_docx_resumen(
        elementos_pdf, nombre_pdv, nombre_analista,
        nombre_archivo=f"{base}.docx",
        carpeta_salida=carpeta_salida,
    )

    # Libro de análisis: las mismas tablas del reporte pero con fórmulas
    # vivas, para que quien lo reciba pueda auditarlas o rehacer el corte
    # por su cuenta sin volver a ejecutar la herramienta.
    ruta_xlsx = os.path.join(carpeta_salida, f"{base}_datos.xlsx")
    libro_mensual(df, ruta_xlsx, "Resumen Mensual — datos y cálculos",
                  os.path.basename(rutas_archivos[0]))

    # Ficha de una página (PNG) para mandar por WhatsApp.
    # Dos versiones: WhatsApp (vertical) y correo (dos columnas).
    rutas_png = fichas_ambos_formatos(
        ficha_mensual, os.path.join(carpeta_salida, base), df,
        modo="cierre", periodo=str(hoja).strip().title(), pdv=nombre_pdv,
        analista=nombre_analista, resumen=resumen)

    return [ruta_pdf, ruta_docx, ruta_xlsx] + rutas_png


HERRAMIENTA = Herramienta(
    id="resumen_mensual",
    nombre="🗓️ Resumen Mensual",
    descripcion=(
        "Sube el Excel de la bitácora del mes ya cerrado y obtén el PDF de "
        "resumen mensual (cierre de mes), un Word editable con el mismo "
        "contenido y una ficha de una página (imagen) para compartir por WhatsApp. "
        "Si además subes la bitácora del mes anterior, el reporte muestra cuánto "
        "cambió cada indicador."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes ya cerrado.",
    icono=":material/calendar_month:",
    nombre_corto="Resumen mensual",
    vista_previa_bitacora=True,
    pide_pdv_e_implant=True,
    meses_anteriores="uno",
    ayuda_meses_anteriores=(
        "Sube la bitácora del mes anterior y el reporte mostrará, en la portada "
        "y en el resumen ejecutivo, cuánto subieron o bajaron las solicitudes, la "
        "conversión, el monto financiado y el GAP."
    ),
)
