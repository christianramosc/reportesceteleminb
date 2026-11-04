"""Adaptador del Avance Preliminar Mensual (reporte_mensual.py, modo "avance") para el registro."""

import os
import pandas as pd

from . import reporte_base as _base
from .reporte_mensual import generar_reporte_pdf
from .docx_reportes import generar_docx_avance
from . import conclusiones as _c
from .ficha_resumen import fichas_ambos_formatos, ficha_mensual
from .libros_analisis import libro_mensual
from .config import DatosReporte
from .registro import Herramienta
from . import nombres_archivo as _nombres


def ejecutar(rutas_archivos, carpeta_salida="salida", fecha_corte=None,
             nombre_pdv=None, nombre_analista=None, **_opciones):
    datos = DatosReporte.desde_opciones(nombre_pdv, nombre_analista)
    nombre_pdv, nombre_analista = datos.pdv, datos.analista

    os.makedirs(carpeta_salida, exist_ok=True)

    df_crudo = _base.cargar_archivo(ruta_local=rutas_archivos[0])
    df = _base.limpiar_datos(df_crudo)
    resumen = _base.resumen_general(df)
    tabla_vendedor = _base.analisis_por_vendedor(df)
    tabla_categoria = _base.analisis_financiero_por_categoria(df)
    ctx = _base.contexto_de_corte(fecha_corte)

    # El nombre de la hoja ("JULIO 2026") es la única pista del mes al que
    # pertenecen los datos. Se usa para advertir si la fecha de corte cae en
    # otro mes (sin esto, correr el avance sobre un mes ya cerrado afirmaba
    # "quedan 10 días para el cierre") y para nombrar los archivos.
    try:
        with pd.ExcelFile(rutas_archivos[0]) as xls:
            hoja = xls.sheet_names[0]
    except Exception:
        hoja = None

    # Nombre corto: Avance_Oct26_corte13-10 (+ .pdf, .docx, _datos.xlsx...)
    corte = ctx["fecha_corte"]
    periodo_archivo = _nombres.periodo_corto(hoja) if hoja else f"{_nombres.CORTOS[corte.month - 1]}{str(corte.year)[2:]}"
    base = f"Avance_{periodo_archivo}_corte{corte:%d-%m}"
    ruta_pdf = os.path.join(carpeta_salida, f"{base}.pdf")

    # El PDF deja aquí sus flowables y el Word se construye con ESOS mismos
    # elementos, para que ambos documentos digan exactamente lo mismo.
    elementos_pdf = []
    generar_reporte_pdf(
        df, resumen, tabla_vendedor, tabla_categoria, "avance",
        nombre_archivo=ruta_pdf, fecha_corte=fecha_corte,
        recolectar_elementos=elementos_pdf, hoja=hoja, datos=datos,
    )

    ruta_docx = generar_docx_avance(
        elementos_pdf, nombre_pdv, nombre_analista,
        nombre_archivo=f"{base}.docx",
        carpeta_salida=carpeta_salida,
    )

    # Libro de análisis: las mismas tablas del reporte pero con fórmulas
    # vivas, para que quien lo reciba pueda auditarlas o rehacer el corte
    # por su cuenta sin volver a ejecutar la herramienta.
    ruta_xlsx = os.path.join(carpeta_salida, f"{base}_datos.xlsx")
    libro_mensual(df, ruta_xlsx, "Avance Preliminar — datos y cálculos",
                  os.path.basename(rutas_archivos[0]))

    # Ficha de una página (PNG) para mandar por WhatsApp.
    periodo = f"Corte al {ctx['dia_actual']} de {ctx['nombre_mes']} de {ctx['fecha_corte'].year}"
    if hoja:
        # Si la hoja es del mismo mes del corte, no se repite mes y año.
        if _c.mes_desde_hoja(hoja) == ctx["fecha_corte"].month:
            periodo = f"{str(hoja).strip().title()}  ·  corte al día {ctx['dia_actual']}"
        else:
            periodo = f"{str(hoja).strip().title()}  ·  {periodo.lower()}"
    # Dos versiones: WhatsApp (vertical) y correo (dos columnas).
    rutas_png = fichas_ambos_formatos(
        ficha_mensual, os.path.join(carpeta_salida, base), df,
        modo="avance", periodo=periodo, pdv=nombre_pdv, analista=nombre_analista,
        resumen=resumen, ctx=ctx, hoja=hoja)

    return [ruta_pdf, ruta_docx, ruta_xlsx] + rutas_png


HERRAMIENTA = Herramienta(
    id="avance_preliminar",
    nombre="📈 Avance Preliminar Mensual",
    descripcion=(
        "Sube el Excel de la bitácora del mes (el que genera la herramienta "
        "'Relación de Clientes') y obtén el PDF de avance preliminar, un "
        "Word editable con el mismo contenido y una ficha de una página "
        "(imagen) para compartir por WhatsApp."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes en curso.",
)
