"""Adaptador de resumen_vendedor_original.py (un PDF por vendedor) para el registro.

Este script es distinto de los demás en un punto: no genera UN archivo,
genera uno por cada asesor. El adaptador arma un PDF por vendedor y los
empaqueta en un ZIP, todo dentro del directorio temporal que la app borra
al terminar.
"""

import os
import zipfile

from . import resumen_vendedor_original as _rv
from .libros_analisis import libro_mensual
from .config import DatosReporte
from .registro import Herramienta
from . import nombres_archivo as _nombres


def ejecutar(rutas_archivos, carpeta_salida="salida", nombre_pdv=None,
             nombre_analista=None, vendedores_incluir=None, **_opciones):
    datos = DatosReporte.desde_opciones(nombre_pdv, nombre_analista)

    os.makedirs(carpeta_salida, exist_ok=True)

    # Toda la salida va al temporal de esta corrida: los PDFs llevan nombre
    # de vendedor y detalle de clientes, y no tienen por qué sobrevivir a la
    # descarga.
    carpeta_pdfs = os.path.join(carpeta_salida, "reportes_por_vendedor")
    carpeta_graficas = os.path.join(carpeta_salida, "graficas")
    os.makedirs(carpeta_pdfs, exist_ok=True)
    os.makedirs(carpeta_graficas, exist_ok=True)

    df_crudo, _origen, hoja = _rv.cargar_archivo(ruta_local=rutas_archivos[0])
    df = _rv.limpiar_datos(df_crudo)
    ctx_mes = _rv.contexto_mensual(hoja_nombre=hoja)

    if "Nombre del Vendedor" not in df.columns:
        raise ValueError(
            "El Excel no tiene la columna 'Nombre del Vendedor'. "
            "Revisa que sea la bitácora de solicitudes y no otro reporte."
        )

    tabla_vendedor = _rv.analisis_por_vendedor(df)
    resumen_eq = _rv.resumen_equipo(df, tabla_vendedor)

    vendedores = sorted(df["Nombre del Vendedor"].dropna().unique().tolist())
    if vendedores_incluir:
        solicitados = {str(v).strip().title() for v in vendedores_incluir}
        faltantes = solicitados - set(vendedores)
        if faltantes:
            print(f"  Aviso: no están en el archivo y se omiten: {sorted(faltantes)}")
        vendedores = [v for v in vendedores if v in solicitados]

    if not vendedores:
        raise ValueError(
            "No quedó ningún vendedor por procesar. Revisa los nombres que "
            "escribiste en el filtro; deben coincidir con los del Excel."
        )

    print(f"  Vendedores a procesar: {len(vendedores)}")
    mes_largo = f"{ctx_mes['nombre_mes'].title()} {ctx_mes['anio']}"
    mes_corto = f"{_nombres.CORTOS[ctx_mes['mes_num'] - 1]}{str(ctx_mes['anio'])[2:]}"
    rutas_pdf = []
    for vendedor in vendedores:
        resumen_v = _rv.analisis_individual(df, vendedor, tabla_vendedor, resumen_eq)
        graficas = _rv.generar_graficas_vendedor(df, resumen_v["df"], vendedor, carpeta_graficas)
        # Dentro del ZIP: "Jessica Elizabeth Machuca Roque - Septiembre 2026.pdf"
        nombre_pdf = _nombres.seguro(f"{vendedor} - {mes_largo}") + ".pdf"
        ruta = _rv.generar_reporte_pdf_vendedor(
            vendedor, resumen_v, tabla_vendedor, resumen_eq, ctx_mes, graficas,
            nombre_archivo=os.path.join(carpeta_pdfs, nombre_pdf), datos=datos,
        )
        rutas_pdf.append(ruta)
        print(f"  ✓ {vendedor}")

    # Un botón de descarga por vendedor sería inmanejable con un equipo
    # grande, así que se entrega un solo ZIP con todos los PDFs dentro.
    nombre_zip = f"Vendedores_{mes_corto}.zip"
    ruta_zip = os.path.join(carpeta_salida, nombre_zip)
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta in rutas_pdf:
            zf.write(ruta, arcname=os.path.basename(ruta))

    print(f"  Empaquetados {len(rutas_pdf)} PDFs en {nombre_zip}")

    # Libro de análisis: los PDFs por vendedor son de lectura, no de
    # trabajo. Esto entrega la base para que cualquiera reconstruya los
    # mismos KPIs con sus propios cortes.
    ruta_xlsx = os.path.join(
        carpeta_salida,
        f"Vendedores_{mes_corto}_datos.xlsx")
    libro_mensual(df, ruta_xlsx,
                  f"Resumen por Vendedor — datos y cálculos "
                  f"({ctx_mes['nombre_mes'].title()} {ctx_mes['anio']})",
                  os.path.basename(rutas_archivos[0]))

    return [ruta_zip, ruta_xlsx]


HERRAMIENTA = Herramienta(
    id="resumen_vendedor",
    nombre="Resumen por Vendedor",
    descripcion=(
        "Sube el Excel de la bitácora del mes y obtén un PDF individual de "
        "desempeño para cada asesor, con sus KPIs, sus gráficas y su "
        "posición frente al promedio del equipo. Todos los PDFs se "
        "descargan juntos en un ZIP."
    ),
    multiple_archivos=False,
    tipos_permitidos=["xlsx"],
    ejecutar=ejecutar,
    ayuda_archivo="El Excel de la bitácora de solicitudes del mes.",
    icono=":material/groups:",
    nombre_corto="Resumen por vendedor",
    vista_previa_bitacora=True,
    pide_pdv_e_implant=True,
    pide_vendedores=True,
)
