# -*- coding: utf-8 -*-
"""RESUMEN DESEMPEÑO POR VENDEDOR — MES

Genera un PDF individual de "Resumen Mensual de Desempeño" para cada
asesor/vendedor a partir de la bitácora de solicitudes, con la misma
identidad visual y espíritu del reporte de Avance Preliminar (portada
con KPIs, resumen ejecutivo redactado, tablas con estilo y gráficas
explicadas), pero:

  - Con foco en UN vendedor a la vez (uno por PDF).
  - Con la narrativa reescrita como cierre MENSUAL (no preliminar):
    ya no se habla de "días restantes" ni de solicitudes que "todavía
    pueden convertirse" -- el mes ya se está resumiendo.
  - Con una sección de comparación contra el promedio y el ranking del
    equipo, para dar contexto a cada asesor sobre su desempeño relativo
    (sin exponer el detalle fila-por-fila de sus compañeros, solo su
    posición y los promedios agregados).

Pensado para Google Colab, con compatibilidad local.

Cambios de esta versión
-----------------------
1. ARREGLO PRINCIPAL — texto encimado en la tabla de solicitudes: todas
   las celdas se envuelven en Paragraph. ReportLab solo sabe partir en
   varias líneas el contenido de un Paragraph; el texto plano se dibuja
   en una sola línea y se desborda sobre la columna vecina (por eso los
   nombres de cliente largos se fusionaban con el vehículo).
2. Anchos de columna calculados a partir del contenido real
   (`anchos_ajustados`), repartiendo siempre el ancho útil completo de
   la página en vez de usar medidas fijas.
3. Tabla de solicitudes: ordenada por estatus y monto, con el año del
   modelo integrado al vehículo, el estatus a color y una fila de
   TOTALES (conteo, monto total y GAP colocados).
4. Etiquetas de los KPI de portada: "\n" no hace nada dentro de un
   Paragraph, se cambió por <br/> (antes salían en un solo renglón).
5. Limpieza de datos más robusta: montos con pd.to_numeric (una celda
   con texto ya no tumba el script), textos sin "Nan" impresos, GAP
   normalizado (SI/SÍ/S/X → SI) y filas vacías descartadas.
6. Correcciones menores: redacción del párrafo de monto financiado,
   etiqueta "Tú" de la gráfica de equipo cuando el vendedor no aparece,
   nombre largo recortado en el pie de página, tablas que ya no se
   parten entre páginas y borrado de las gráficas temporales al final.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import re
import shutil
import zipfile
import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # servidor sin pantalla: hay que fijarlo ANTES de pyplot
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap, to_rgb

try:
    from . import conclusiones as _conclusiones
    from . import pdf_util as _pdf_util
    from . import lateral as _lateral
except ImportError:  # ejecución suelta (Colab)
    import conclusiones as _conclusiones
    import pdf_util as _pdf_util
    import lateral as _lateral

try:
    from google.colab import files  # noqa
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

try:
    from IPython.display import display
except ImportError:
    display = print

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 140)

# reportlab va fijado en requirements.txt; ya no se instala en tiempo de
# ejecución (eso era herencia de Colab y en un servidor puede colgarse).
import reportlab  # noqa: F401

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors as rl_colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
    PageBreak, HRFlowable, KeepTogether, Flowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import stringWidth


# =======================================================================
# 1) PALETA DE COLORES — misma paleta de marca que el reporte de Avance
#    Preliminar, para que ambos reportes se vean como parte de la misma
#    familia de documentos.
# =======================================================================
MG_ROJO          = "#E4002B"
MG_ROJO_OSCURO   = "#7A0019"
INBURSA_AZUL     = "#191970"
MG_ROJO_MEDIO    = "#B3001B"
MG_ROJO_CLARO    = "#FF6B6B"
MG_ROJO_PASTEL   = "#FFB3B3"
MG_ROJO_PALIDO   = "#FBE7E9"
MG_GRIS_OSCURO   = "#2B2B2B"
MG_GRIS_CLARO    = "#EAEAEA"
MG_GRIS_MEDIO    = "#B7B7B7"
BLANCO           = "#FFFFFF"

# --- Tonos neutros del rediseño corporativo/moderno (misma familia que
#     el reporte de Avance Preliminar) ---
GRIS_TEXTO_SEC   = "#6B7280"   # texto secundario (labels, notas, pie)
GRIS_LINEA       = "#E3E5E9"   # reglas y bordes discretos
GRIS_ZEBRA       = "#F6F7F9"   # fondo de fila alterna en tablas (casi blanco)
AZUL_PALIDO      = "#EEF0F8"   # fondo muy sutil para acentos en azul Inbursa

PALETA_ROJOS = ["#7A0019", "#9E001F", "#C10024", "#E4002B",
                 "#F1354D", "#FF6B6B", "#FF9B9B", "#FFC7C7"]
_CMAP_ROJOS = LinearSegmentedColormap.from_list("rojos_mg", PALETA_ROJOS)

# =======================================================================
# 1B) FUENTE — igual que en el reporte de Avance Preliminar; cambia solo
#     FUENTE_BASE si se quiere otra tipografía en todo el PDF.
# =======================================================================
FUENTE_BASE = "Helvetica"

_FUENTES_DISPONIBLES = {
    "Helvetica": {"regular": "Helvetica",   "bold": "Helvetica-Bold",
                  "italica": "Helvetica-Oblique", "bold_italica": "Helvetica-BoldOblique"},
    "Times":     {"regular": "Times-Roman", "bold": "Times-Bold",
                  "italica": "Times-Italic",      "bold_italica": "Times-BoldItalic"},
    "Courier":   {"regular": "Courier",     "bold": "Courier-Bold",
                  "italica": "Courier-Oblique",    "bold_italica": "Courier-BoldOblique"},
}
_fuente_activa = _FUENTES_DISPONIBLES.get(FUENTE_BASE, _FUENTES_DISPONIBLES["Helvetica"])
FUENTE_REGULAR      = _fuente_activa["regular"]
FUENTE_BOLD         = _fuente_activa["bold"]
FUENTE_ITALICA      = _fuente_activa["italica"]
FUENTE_BOLD_ITALICA = _fuente_activa["bold_italica"]

COLOR_CATEGORIA = {
    "FINANCIADO":       MG_ROJO_OSCURO,
    "APROBADO":         MG_ROJO,
    "CONTRAPROPUESTA":  MG_GRIS_OSCURO,
    "RECHAZADO":        MG_ROJO_PASTEL,
}
ORDEN_CATEGORIAS = ["FINANCIADO", "APROBADO", "CONTRAPROPUESTA", "RECHAZADO"]

# Los colores de arriba están pensados para RELLENOS de gráfica. Para TEXTO
# sobre fondo blanco hacen falta tonos con más contraste (el rosa pastel de
# RECHAZADO era ilegible dentro de la tabla).
COLOR_CATEGORIA_TEXTO = {
    "FINANCIADO":       "#7A0019",
    "APROBADO":         "#C10024",
    "CONTRAPROPUESTA":  "#5A5A5A",
    "RECHAZADO":        "#9A9AA0",
}

NOMBRE_EMPRESA = "AUTOEXPRESS INBURSA"
SUBTITULO_EMPRESA = "MG Colima PYD"
NOMBRE_ANALISTA = "Christian Ramos"

_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# --- Geometría de página: se define UNA sola vez y se reutiliza tanto en
#     los márgenes del documento como en el cálculo de anchos de tabla,
#     para que ninguna tabla se salga de la caja de texto. ---
MARGEN_IZQ = 2.4 * cm   # igual que pdf_util.MARGEN
MARGEN_DER = 2.4 * cm
ANCHO_UTIL = letter[0] - MARGEN_IZQ - MARGEN_DER   # ≈ 18.6 cm

# Estas dos rutas las REAPUNTA herramienta_resumen_vendedor.py al
# directorio temporal de cada corrida. No se crean al importar: en un
# servidor compartido eso dejaría PDFs con nombres de clientes en el
# directorio de trabajo, sobreviviendo entre sesiones.
# Se leen en tiempo de ejecución (dentro de las funciones), así que
# reasignarlas desde fuera basta para redirigir toda la salida.
CARPETA_GRAFICAS = "graficas_temp_resumen_vendedor"
CARPETA_PDFS = "reportes_por_vendedor"

plt.rcParams.update({
    "figure.facecolor":  "white",
    "axes.facecolor":    "white",
    "axes.edgecolor":    GRIS_LINEA,
    "axes.labelcolor":   GRIS_TEXTO_SEC,
    "text.color":        MG_GRIS_OSCURO,
    "xtick.color":       GRIS_TEXTO_SEC,
    "ytick.color":       GRIS_TEXTO_SEC,
    "font.size":         10,
    "axes.titlesize":    12.5,
    "axes.titleweight":  "bold",
    "axes.titlecolor":   MG_GRIS_OSCURO,
    "axes.titlepad":     14,
    "axes.labelsize":    9.5,
    "axes.linewidth":    0.8,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.spines.left":  True,
    "axes.grid":         False,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "legend.fontsize":   9,
    "legend.frameon":    False,
})


# =======================================================================
# 2) CONTEXTO DEL MES — a diferencia del Avance Preliminar, aquí ya NO
#    importa "qué día del mes es" (esto es un cierre, no un corte a
#    medias); solo se identifica a qué mes/año corresponde el resumen,
#    para la portada y el pie de página.
# =======================================================================
def contexto_mensual(mes_anio=None, hoja_nombre=None, fecha_corte=None):
    """
    Determina el mes/año que se está resumiendo, en este orden de
    prioridad:
      1) mes_anio explícito, como string "agosto 2026".
      2) el nombre de la hoja de Excel, si coincide con un mes en
         español (p.ej. una hoja llamada "AGOSTO").
      3) fecha_corte (string "DD/MM/AAAA" o date/datetime), tomando
         su mes y año.
      4) la fecha de hoy, como último recurso.
    """
    if mes_anio:
        partes = mes_anio.strip().lower().split()
        nombre_mes = partes[0]
        anio = int(partes[1]) if len(partes) > 1 else datetime.date.today().year
        if nombre_mes in _MESES_ES:
            return {"nombre_mes": nombre_mes, "anio": anio,
                    "mes_num": _MESES_ES.index(nombre_mes) + 1}

    if hoja_nombre:
        hoja_lower = hoja_nombre.strip().lower()
        # Busca el nombre de un mes en español dentro del nombre de la
        # hoja (permite "agosto", "AGOSTO 2026", "Agosto_2026", etc.,
        # no solo una coincidencia exacta con el mes solo).
        nombre_mes_encontrado = next(
            (mes for mes in _MESES_ES if re.search(rf"\b{mes}\b", hoja_lower)),
            None
        )
        if nombre_mes_encontrado:
            # Si el nombre de la hoja también trae un año (p.ej. "agosto
            # 2026"), se usa ese año en vez de asumir el año actual.
            match_anio = re.search(r"(20\d{2})", hoja_lower)
            anio = int(match_anio.group(1)) if match_anio else datetime.date.today().year
            return {"nombre_mes": nombre_mes_encontrado, "anio": anio,
                    "mes_num": _MESES_ES.index(nombre_mes_encontrado) + 1}

    if fecha_corte is not None:
        if isinstance(fecha_corte, str):
            fecha_corte = pd.to_datetime(fecha_corte, dayfirst=True).date()
        elif isinstance(fecha_corte, datetime.datetime):
            fecha_corte = fecha_corte.date()
        return {"nombre_mes": _MESES_ES[fecha_corte.month - 1], "anio": fecha_corte.year,
                "mes_num": fecha_corte.month}

    hoy = datetime.date.today()
    return {"nombre_mes": _MESES_ES[hoy.month - 1], "anio": hoy.year, "mes_num": hoy.month}


def _gradiente(n):
    if n <= 1:
        return [MG_ROJO]
    valores = np.linspace(0.0, 0.82, n)
    return [_CMAP_ROJOS(v) for v in valores]


def _color_texto_legible(color_fondo):
    r, g, b = to_rgb(color_fondo)
    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    return "white" if luminancia < 0.6 else MG_GRIS_OSCURO


# =======================================================================
# 3) CARGA DEL ARCHIVO
# =======================================================================
def cargar_archivo(ruta_local=None):
    """
    Sube (en Colab) o abre (fuera de Colab) el archivo Excel de la
    bitácora y devuelve (DataFrame, nombre_archivo, nombre_hoja).
    """
    if ruta_local:
        nombre_archivo = ruta_local
    elif EN_COLAB:
        print("Sube el archivo Excel de la bitácora de solicitudes...")
        subido = files.upload()
        nombre_archivo = list(subido.keys())[0]
    else:
        nombre_archivo = input("Ruta del archivo Excel: ").strip()

    xls = pd.ExcelFile(nombre_archivo)
    hoja = xls.sheet_names[0]
    if len(xls.sheet_names) > 1:
        print(f"El archivo tiene varias hojas: {xls.sheet_names}")
        elegida = input(f"¿Cuál analizar? (Enter = '{hoja}'): ").strip()
        hoja = elegida if elegida else hoja

    df = pd.read_excel(nombre_archivo, sheet_name=hoja)
    print(f"Archivo cargado: {nombre_archivo}  |  Hoja: {hoja}  |  {len(df)} solicitudes\n")
    return df, nombre_archivo, hoja


# =======================================================================
# 4) LIMPIEZA Y NORMALIZACIÓN DE DATOS (igual que en Avance Preliminar)
# =======================================================================
COLUMNAS_ESPERADAS = [
    "Folio CCK", "STATUS", "Nombre Completo", "Fecha de Nacimiento",
    "Teléfono Móvil", "Correo Electrónico", "Nombre del Vendedor",
    "Marca", "Vehículo", "Año Modelo", "Precio Venta (c/IVA)",
    "Enganche", "¿Tiene GAP?", "Monto GAP", "Plazo (meses)",
    "Tasa Interés Anual", "Monto Total a Financiar",
    "Mensualidad Mínima", "Mensualidad Máxima",
]
COLUMNAS_MONEDA = [
    "Precio Venta (c/IVA)", "Enganche", "Monto GAP",
    "Monto Total a Financiar", "Mensualidad Mínima", "Mensualidad Máxima",
]
COLUMNAS_PORCENTAJE = ["Tasa Interés Anual"]

STATUS_APROBADO   = ["APROBADO"]
STATUS_FINANCIADO = ["FINANCIADOS", "FINANCIADO"]
STATUS_RECHAZADOS = ["RECHAZADO", "RECHAZADOS", "CANCELADO", "CANCELADOS"]


def _limpiar_moneda(serie):
    """Convierte una columna de montos a número. Se usa pd.to_numeric con
    errors='coerce' en vez de astype(float): así una celda con texto raro
    ("PENDIENTE", "N/A", un guion) se vuelve NaN en lugar de tumbar todo
    el script con un ValueError."""
    limpia = (
        serie.astype(str)
             .str.replace(r"[^\d\.\-]", "", regex=True)
             .str.strip()
             .replace({"": np.nan, "-": np.nan, ".": np.nan})
    )
    return pd.to_numeric(limpia, errors="coerce")


def _limpiar_texto(serie, modo=None):
    """Normaliza una columna de texto: quita espacios repetidos y convierte
    los 'nan'/'None'/'' que deja astype(str) en NaN reales (antes salían
    impresos como 'Nan' dentro de las tablas del PDF)."""
    limpia = (
        serie.astype(str)
             .str.replace(r"\s+", " ", regex=True)
             .str.strip()
    )
    limpia = limpia.replace(
        {"nan": np.nan, "NaN": np.nan, "NAN": np.nan, "None": np.nan,
         "none": np.nan, "": np.nan, "-": np.nan, "NaT": np.nan}
    )
    if modo == "titulo":
        limpia = limpia.str.title()
    elif modo == "mayusculas":
        limpia = limpia.str.upper()
    return limpia


def _limpiar_porcentaje(serie):
    def _convertir(valor):
        if pd.isna(valor):
            return np.nan
        if isinstance(valor, str):
            texto = valor.strip().replace("%", "")
            if texto in ("", "nan", "None"):
                return np.nan
            try:
                return float(texto)
            except ValueError:
                return np.nan
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return np.nan
        return numero * 100 if numero <= 1 else numero
    return serie.apply(_convertir)


def clasificar_status(status):
    s = str(status).strip().upper()
    if s in STATUS_FINANCIADO:
        return "FINANCIADO"
    if s in STATUS_APROBADO:
        return "APROBADO"
    if s in STATUS_RECHAZADOS:
        return "RECHAZADO"
    return "CONTRAPROPUESTA"


def limpiar_datos(df_original):
    df = df_original.copy()
    df.columns = [str(c).strip() for c in df.columns]

    faltantes = [c for c in COLUMNAS_ESPERADAS if c not in df.columns]
    if faltantes:
        print(f"Aviso: no se encontraron estas columnas esperadas: {faltantes}")
        print("El script seguirá, pero los análisis que dependan de ellas se omitirán.\n")

    for col in COLUMNAS_MONEDA:
        if col in df.columns:
            df[col] = _limpiar_moneda(df[col])

    for col in COLUMNAS_PORCENTAJE:
        if col in df.columns:
            df[col] = _limpiar_porcentaje(df[col])

    if "STATUS" in df.columns:
        df["STATUS"] = df["STATUS"].astype(str).str.strip().str.upper()
        df["Categoria"] = df["STATUS"].apply(clasificar_status)

    if "Nombre del Vendedor" in df.columns:
        df["Nombre del Vendedor"] = _limpiar_texto(df["Nombre del Vendedor"], modo="titulo")

    if "Nombre Completo" in df.columns:
        df["Nombre Completo"] = _limpiar_texto(df["Nombre Completo"], modo="titulo")

    if "Marca" in df.columns:
        df["Marca"] = _limpiar_texto(df["Marca"], modo="mayusculas")

    if "Vehículo" in df.columns:
        df["Vehículo"] = _limpiar_texto(df["Vehículo"])

    if "Folio CCK" in df.columns:
        df["Folio CCK"] = _limpiar_texto(df["Folio CCK"])

    if "¿Tiene GAP?" in df.columns:
        df["¿Tiene GAP?"] = (
            _limpiar_texto(df["¿Tiene GAP?"], modo="mayusculas")
            .replace({"SÍ": "SI", "S": "SI", "TRUE": "SI", "X": "SI", "N": "NO", "FALSE": "NO"})
        )

    # Filas completamente vacías (renglones sueltos al final de la bitácora)
    df = df.dropna(how="all")
    if "Nombre del Vendedor" in df.columns:
        df = df[df["Nombre del Vendedor"].notna()]

    return df.reset_index(drop=True)


# =======================================================================
# 5) ANÁLISIS POR VENDEDOR (tabla de todo el equipo — se usa como base
#    de comparación/ranking en cada reporte individual)
# =======================================================================
def analisis_por_vendedor(df):
    if "Nombre del Vendedor" not in df.columns:
        return None

    total_por_vendedor = df.groupby("Nombre del Vendedor").size().rename("Total")
    tabla = pd.DataFrame({"Total": total_por_vendedor})

    if "Categoria" in df.columns:
        pivote = pd.crosstab(df["Nombre del Vendedor"], df["Categoria"])
        for col in ORDEN_CATEGORIAS:
            if col not in pivote.columns:
                pivote[col] = 0
        tabla = tabla.join(pivote[ORDEN_CATEGORIAS])
        tabla["% Financiado"] = (tabla["FINANCIADO"] / tabla["Total"] * 100).round(1)

    if "Monto Total a Financiar" in df.columns and "Categoria" in df.columns:
        monto_financiado = (
            df[df["Categoria"] == "FINANCIADO"]
            .groupby("Nombre del Vendedor")["Monto Total a Financiar"].sum()
            .rename("Monto Financiado ($)")
        )
        monto_aprobado = (
            df[df["Categoria"] == "APROBADO"]
            .groupby("Nombre del Vendedor")["Monto Total a Financiar"].sum()
            .rename("Monto Aprobado ($)")
        )
        tabla = tabla.join(monto_financiado).join(monto_aprobado)
        tabla[["Monto Financiado ($)", "Monto Aprobado ($)"]] = tabla[
            ["Monto Financiado ($)", "Monto Aprobado ($)"]
        ].fillna(0)

    if "¿Tiene GAP?" in df.columns:
        gap_total_v = df[df["¿Tiene GAP?"] == "SI"].groupby("Nombre del Vendedor").size()
        tabla["GAP Total"] = gap_total_v.reindex(tabla.index).fillna(0).astype(int)
        tabla["% con GAP"] = (tabla["GAP Total"] / tabla["Total"] * 100).round(1)

    tabla = tabla.sort_values("Total", ascending=False)
    return tabla


def resumen_equipo(df, tabla_vendedor):
    """KPIs agregados de TODO el equipo, usados como línea base de
    comparación para cada reporte individual (promedios, no detalle)."""
    total = len(df)
    r = {"total": total, "n_vendedores": int(tabla_vendedor.shape[0]) if tabla_vendedor is not None else 0}

    if "Categoria" in df.columns:
        conteo_cat = df["Categoria"].value_counts()
        r["financiados"] = int(conteo_cat.get("FINANCIADO", 0))
        r["aprobados"] = int(conteo_cat.get("APROBADO", 0))
        r["rechazados"] = int(conteo_cat.get("RECHAZADO", 0))
        r["en_tramite"] = int(conteo_cat.get("CONTRAPROPUESTA", 0))
        r["pct_financiado_equipo"] = (r["financiados"] / total * 100) if total else 0

    if tabla_vendedor is not None and not tabla_vendedor.empty and r["n_vendedores"]:
        r["promedio_solicitudes_por_vendedor"] = total / r["n_vendedores"]
        if "FINANCIADO" in tabla_vendedor.columns:
            r["promedio_financiado_por_vendedor"] = tabla_vendedor["FINANCIADO"].mean()
        if "% Financiado" in tabla_vendedor.columns:
            # Conversión DEL EQUIPO = financiados del equipo / solicitudes del
            # equipo. Antes se promediaban las tasas de cada vendedor sin
            # ponderar, y alguien con 1 de 1 (100%) inflaba el "promedio" muy
            # por encima de la conversión real (28.2% contra 23.1% en julio),
            # haciendo que todos se vieran peor comparados contra él. Además
            # no cuadraba con el 23.1% que muestran los demás reportes.
            _fin_eq = int(tabla_vendedor["FINANCIADO"].sum()) if "FINANCIADO" in tabla_vendedor else 0
            _tot_eq = int(tabla_vendedor["Total"].sum())
            r["promedio_pct_financiado"] = _fin_eq / _tot_eq * 100 if _tot_eq else 0.0
        if "% con GAP" in tabla_vendedor.columns:
            r["promedio_pct_gap"] = tabla_vendedor["% con GAP"].mean()

    monto_col = "Monto Total a Financiar"
    if monto_col in df.columns:
        r["monto_total"] = df[monto_col].sum()
        if "Categoria" in df.columns:
            r["monto_financiado"] = df.loc[df["Categoria"] == "FINANCIADO", monto_col].sum()

    for col, clave in [("Precio Venta (c/IVA)", "precio_venta_prom_equipo"),
                        ("Plazo (meses)", "plazo_prom_equipo"),
                        ("Tasa Interés Anual", "tasa_prom_equipo")]:
        if col in df.columns:
            r[clave] = df[col].mean()

    if "Enganche" in df.columns and "Precio Venta (c/IVA)" in df.columns:
        r["pct_enganche_prom_equipo"] = (df["Enganche"] / df["Precio Venta (c/IVA)"] * 100).mean()

    if "¿Tiene GAP?" in df.columns:
        r["pct_gap_equipo"] = (df["¿Tiene GAP?"] == "SI").mean() * 100

    return r


# =======================================================================
# 6) ANÁLISIS INDIVIDUAL DEL VENDEDOR
# =======================================================================
def _rango(serie, vendedor, ascending=False):
    """Posición (1 = mejor) de `vendedor` dentro de una Series indexada
    por vendedor, con empates compartiendo el mismo lugar. El segundo
    valor devuelto es el número total de vendedores (no el rango máximo,
    que puede ser menor si hay empates en los últimos lugares)."""
    if serie is None or serie.empty or vendedor not in serie.index:
        return None, None
    rangos = serie.rank(ascending=ascending, method="min")
    return int(rangos.loc[vendedor]), int(serie.shape[0])


def analisis_individual(df_total, vendedor, tabla_vendedor, resumen_eq):
    df_v = df_total[df_total["Nombre del Vendedor"] == vendedor].copy()
    total_v = len(df_v)
    # df_equipo viaja con el resultado para que las conclusiones comparen
    # contra el equipo completo sin tener que cambiar la firma del PDF.
    r = {"vendedor": vendedor, "df": df_v, "df_equipo": df_total, "total": total_v}

    if "Categoria" in df_v.columns:
        conteo = df_v["Categoria"].value_counts()
        for cat in ORDEN_CATEGORIAS:
            r[cat.lower()] = int(conteo.get(cat, 0))
        r["pct_financiado"] = (r["financiado"] / total_v * 100) if total_v else 0

    monto_col = "Monto Total a Financiar"
    if monto_col in df_v.columns and "Categoria" in df_v.columns:
        r["monto_financiado"] = df_v.loc[df_v["Categoria"] == "FINANCIADO", monto_col].sum()
        r["monto_aprobado"] = df_v.loc[df_v["Categoria"] == "APROBADO", monto_col].sum()
        if r.get("financiado"):
            r["ticket_financiado"] = df_v.loc[df_v["Categoria"] == "FINANCIADO", monto_col].mean()

    if "¿Tiene GAP?" in df_v.columns and total_v:
        r["n_gap"] = int((df_v["¿Tiene GAP?"] == "SI").sum())
        r["pct_gap"] = r["n_gap"] / total_v * 100
        if "Categoria" in df_v.columns and r.get("financiado"):
            gap_fin = ((df_v["Categoria"] == "FINANCIADO") & (df_v["¿Tiene GAP?"] == "SI")).sum()
            r["gap_financiado"] = int(gap_fin)

    for col, clave in [("Precio Venta (c/IVA)", "precio_venta_prom"),
                        ("Plazo (meses)", "plazo_prom"),
                        ("Tasa Interés Anual", "tasa_prom")]:
        if col in df_v.columns and df_v[col].notna().any():
            r[clave] = df_v[col].mean()

    if "Enganche" in df_v.columns and "Precio Venta (c/IVA)" in df_v.columns:
        pct_eng = (df_v["Enganche"] / df_v["Precio Venta (c/IVA)"] * 100)
        if pct_eng.notna().any():
            r["pct_enganche_prom"] = pct_eng.mean()

    if "Vehículo" in df_v.columns:
        modelos = df_v["Vehículo"].dropna().value_counts()
        r["modelos"] = modelos
        if not modelos.empty:
            r["modelo_top"] = modelos.index[0]
            r["modelo_top_val"] = int(modelos.iloc[0])

    # -- posición dentro del equipo --
    if tabla_vendedor is not None and not tabla_vendedor.empty:
        r["rank_total"], r["rank_total_de"] = _rango(tabla_vendedor["Total"], vendedor)
        if "FINANCIADO" in tabla_vendedor.columns:
            r["rank_financiado"], r["rank_financiado_de"] = _rango(tabla_vendedor["FINANCIADO"], vendedor)
        if "% Financiado" in tabla_vendedor.columns:
            r["rank_pct_financiado"], r["rank_pct_financiado_de"] = _rango(tabla_vendedor["% Financiado"], vendedor)

    return r


# =======================================================================
# 7) GRÁFICAS
# =======================================================================
def _guardar_si_procede(fig, guardar_como):
    if guardar_como:
        fig.savefig(guardar_como, dpi=150, bbox_inches="tight", facecolor="white")
    return guardar_como


def _formato_miles(ax, eje="y"):
    formatter = mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    if eje == "y":
        ax.yaxis.set_major_formatter(formatter)
    else:
        ax.xaxis.set_major_formatter(formatter)


def grafica_dona_status_vendedor(df_v, vendedor, guardar_como=None):
    """Dona con la distribución de status de las solicitudes de ESTE vendedor."""
    if "Categoria" not in df_v.columns or df_v.empty:
        return None
    conteo_bruto = df_v["Categoria"].value_counts()
    orden_presente = [c for c in ORDEN_CATEGORIAS if c in conteo_bruto.index]
    conteo = conteo_bruto.reindex(orden_presente)
    colores = [COLOR_CATEGORIA.get(c, MG_GRIS_CLARO) for c in conteo.index]

    fig, ax = plt.subplots(figsize=(7, 6))
    wedges, _, autotextos = ax.pie(
        conteo.values, labels=None, autopct="%1.0f%%", pctdistance=0.8,
        colors=colores, startangle=90, wedgeprops=dict(width=0.42, edgecolor="white"),
        textprops=dict(fontweight="bold"),
    )
    for autotexto, color_rebanada in zip(autotextos, colores):
        autotexto.set_color(_color_texto_legible(color_rebanada))

    etiquetas = [f"{cat} ({valor})" for cat, valor in zip(conteo.index, conteo.values)]
    ax.legend(wedges, etiquetas, loc="upper center", bbox_to_anchor=(0.5, -0.03),
               frameon=False, fontsize=9, ncol=2)
    ax.set_title(f"Distribución de Solicitudes — {vendedor}")
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def grafica_equipo_destacado(df_total, vendedor, guardar_como=None):
    """Barras horizontales apiladas por categoría, con TODOS los vendedores
    del equipo para dar contexto, pero solo el vendedor actual conserva los
    colores de marca — el resto se muestra en gris tenue, sin exponer el
    detalle de cada compañero, solo la comparación de volumen."""
    if not {"Nombre del Vendedor", "Categoria"}.issubset(df_total.columns):
        return None

    pivote = pd.crosstab(df_total["Nombre del Vendedor"], df_total["Categoria"])
    orden_cols = [c for c in ORDEN_CATEGORIAS if c in pivote.columns]
    pivote = pivote[orden_cols]
    pivote["Total"] = pivote.sum(axis=1)
    pivote = pivote.sort_values("Total").drop(columns="Total")
    if pivote.empty:
        return None

    fig, ax = plt.subplots(figsize=(9, max(4, len(pivote) * 0.55) + 0.8))
    izquierda = np.zeros(len(pivote))
    for col in orden_cols:
        valores = pivote[col].values
        colores_fila = [
            COLOR_CATEGORIA.get(col, MG_GRIS_CLARO) if idx == vendedor else MG_GRIS_CLARO
            for idx in pivote.index
        ]
        ax.barh(pivote.index, valores, left=izquierda, color=colores_fila, edgecolor="white")
        izquierda += valores

    # etiquetas en negritas solo para el vendedor destacado
    etiquetas = ax.get_yticklabels()
    for etiqueta in etiquetas:
        if etiqueta.get_text() == vendedor:
            etiqueta.set_fontweight("bold")
            etiqueta.set_color(MG_ROJO_OSCURO)

    # La etiqueta "Tú" solo se dibuja si el vendedor realmente aparece en
    # la gráfica; antes se pintaba un "Tú: 0" sobre la barra equivocada.
    if vendedor in pivote.index:
        total_vendedor = int(pivote.loc[vendedor].sum())
        ax.text(total_vendedor + max(pivote.sum(axis=1).max() * 0.02, 0.3),
                 list(pivote.index).index(vendedor),
                 f"  Tú: {total_vendedor}", va="center", fontsize=9, fontweight="bold",
                 color=MG_ROJO_OSCURO)

    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR_CATEGORIA.get(c, MG_GRIS_CLARO)) for c in orden_cols]
    ax.legend(handles, orden_cols, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False, ncol=4)
    ax.set_title("Tu Volumen vs. el Equipo")
    ax.set_xlabel("Número de solicitudes")
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def grafica_modelos_vendedor(df_v, vendedor, guardar_como=None):
    if "Vehículo" not in df_v.columns:
        return None
    conteo = df_v["Vehículo"].dropna().value_counts().sort_values(ascending=True)
    if conteo.empty:
        return None

    fig, ax = plt.subplots(figsize=(8, max(2.5, len(conteo) * 0.45)))
    colores = list(reversed(_gradiente(len(conteo))))
    ax.barh(conteo.index, conteo.values, color=colores, edgecolor="white")
    for i, valor in enumerate(conteo.values):
        ax.text(valor + max(conteo.values) * 0.02, i, str(valor), va="center", fontsize=9)

    ax.set_title(f"Modelos Solicitados — {vendedor}")
    ax.set_xlabel("Número de solicitudes")
    ax.set_xlim(0, max(conteo.values) * 1.25)
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def generar_graficas_vendedor(df_total, df_v, vendedor):
    especificaciones = [
        ("dona_status", lambda: grafica_dona_status_vendedor(df_v, vendedor, os.path.join(CARPETA_GRAFICAS, f"dona_{_slug(vendedor)}.png"))),
        ("equipo_destacado", lambda: grafica_equipo_destacado(df_total, vendedor, os.path.join(CARPETA_GRAFICAS, f"equipo_{_slug(vendedor)}.png"))),
        ("modelos", lambda: grafica_modelos_vendedor(df_v, vendedor, os.path.join(CARPETA_GRAFICAS, f"modelos_{_slug(vendedor)}.png"))),
    ]
    rutas = {}
    for clave, funcion in especificaciones:
        resultado = funcion()
        if resultado:
            rutas[clave] = resultado
    return rutas


def _slug(texto):
    texto = re.sub(r"[^\w\s-]", "", str(texto)).strip().lower()
    return re.sub(r"[\s]+", "_", texto)


# =======================================================================
# 8) REPORTE PDF INDIVIDUAL (ReportLab)
# =======================================================================
def _nombres_y(nombres):
    nombres = [str(n) for n in nombres]
    if not nombres:
        return ""
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _texto_seguro(valor):
    """Prepara un texto para meterlo en una celda de tabla: colapsa los
    espacios repetidos y escapa los caracteres que ReportLab interpreta
    como marcado XML (&, <, >), que de otro modo revientan el Paragraph.

    El corte de palabras larguísimas (correos, folios, VIN) lo resuelve el
    propio Paragraph con splitLongWords=1, sin meter ningún caracter
    invisible: los espacios de ancho cero se dibujan como un cuadrito en
    las fuentes base de PDF.
    """
    texto = " ".join(str(valor).split())
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ancho_texto(texto, fuente, tam):
    """Ancho real (en puntos) del texto más largo de una celda, midiendo
    palabra por palabra para no sobredimensionar columnas que sí pueden
    partirse en varias líneas."""
    texto = str(texto)
    if not texto.strip():
        return 0.0, 0.0
    completo = stringWidth(texto, fuente, tam)
    palabra_larga = max((stringWidth(p, fuente, tam) for p in texto.split()), default=0.0)
    # el mínimo cómodo es la palabra más larga; el ideal, el texto completo
    return completo, palabra_larga


def anchos_ajustados(datos, ancho_total=None, tam_fuente=8.2, tam_encabezado=8.3,
                     padding=12, min_cm=1.4, max_cm=None):
    """Calcula los anchos de columna a partir del CONTENIDO real de la
    tabla, repartiendo exactamente `ancho_total` (por defecto, todo el
    ancho útil de la página).

    La lógica: cada columna pide un ancho "ideal" (su texto más largo sin
    partir) y declara un ancho "mínimo" (su palabra más larga, para que
    nunca se corte a media palabra). Si la suma de ideales cabe, se usa;
    si no, el excedente se recorta proporcionalmente respetando mínimos.
    Así, una columna con nombres largos se lleva el espacio que necesita
    y las columnas cortas (Folio, ¿GAP?) no lo desperdician.
    """
    if not datos:
        return None
    ancho_total = ancho_total if ancho_total is not None else ANCHO_UTIL
    n_cols = len(datos[0])
    min_pt = min_cm * cm
    max_pt = max_cm * cm if max_cm else None

    ideales, minimos = [], []
    for j in range(n_cols):
        ideal_col, min_col = 0.0, 0.0
        for i, fila in enumerate(datos):
            if j >= len(fila):
                continue
            celda = fila[j]
            texto = celda.getPlainText() if hasattr(celda, "getPlainText") else str(celda)
            fuente = FUENTE_BOLD if i == 0 else FUENTE_REGULAR
            tam = tam_encabezado if i == 0 else tam_fuente
            completo, palabra = _ancho_texto(texto, fuente, tam)
            ideal_col = max(ideal_col, completo)
            min_col = max(min_col, palabra)
        ideales.append(ideal_col + padding)
        minimos.append(max(min_col + padding, min_pt))

    if max_pt:
        ideales = [min(a, max(max_pt, minimos[j])) for j, a in enumerate(ideales)]

    suma_ideal = sum(ideales)
    if suma_ideal <= ancho_total:
        # sobra espacio: se reparte proporcionalmente al ideal de cada columna
        sobrante = ancho_total - suma_ideal
        return [a + sobrante * (a / suma_ideal) for a in ideales]

    # no cabe: se recorta el exceso sobre el mínimo, proporcionalmente
    exceso_total = sum(max(ideales[j] - minimos[j], 0) for j in range(n_cols))
    faltante = suma_ideal - ancho_total
    if exceso_total <= 0:
        # ni los mínimos caben: se escala todo (caso extremo)
        factor = ancho_total / suma_ideal
        return [a * factor for a in ideales]
    factor = min(faltante / exceso_total, 1.0)
    anchos = [ideales[j] - max(ideales[j] - minimos[j], 0) * factor for j in range(n_cols)]
    # ajuste fino para que la suma sea exactamente el ancho disponible
    diferencia = ancho_total - sum(anchos)
    anchos[-1] += diferencia
    return anchos


def imagen_ajustada(ruta, ancho_cm, alto_max_cm=None):
    ancho_px, alto_px = ImageReader(ruta).getSize()
    alto_cm = ancho_cm * (alto_px / ancho_px)
    if alto_max_cm and alto_cm > alto_max_cm:
        alto_cm = alto_max_cm
        ancho_cm = alto_cm * (ancho_px / alto_px)
    return Image(ruta, width=ancho_cm * cm, height=alto_cm * cm, hAlign="CENTER")


def generar_reporte_pdf_vendedor(vendedor, resumen_v, tabla_vendedor, resumen_eq, ctx_mes,
                                  rutas_graficas, nombre_archivo=None):
    df_v = resumen_v["df"]
    total_v = resumen_v["total"]

    if nombre_archivo is None:
        nombre_archivo = os.path.join(
            CARPETA_PDFS, f"Resumen_Mensual_{_slug(vendedor)}_{ctx_mes['nombre_mes']}_{ctx_mes['anio']}.pdf"
        )

    MES_TITULO = f"{ctx_mes['nombre_mes'].capitalize()} {ctx_mes['anio']}"

    # -------------------------------------------------------------
    # Estilos (misma identidad visual que el Avance Preliminar)
    # -------------------------------------------------------------
    styles = getSampleStyleSheet()
    estilo_kicker_portada = ParagraphStyle(
        "KickerPortada", parent=styles["Normal"], fontName=FUENTE_BOLD, fontSize=9.5,
        textColor=rl_colors.HexColor(MG_ROJO), alignment=TA_LEFT, spaceAfter=6, leading=12)
    estilo_titulo_portada = ParagraphStyle(
        "TituloPortada", parent=styles["Title"], fontName=FUENTE_BOLD, fontSize=22,
        textColor=rl_colors.HexColor(INBURSA_AZUL), alignment=TA_LEFT, spaceAfter=2, leading=26)
    estilo_nombre_portada = ParagraphStyle(
        "NombrePortada", parent=styles["Title"], fontName=FUENTE_BOLD, fontSize=16,
        textColor=rl_colors.HexColor(MG_GRIS_OSCURO), alignment=TA_LEFT, spaceAfter=4, leading=20)
    estilo_subtitulo_portada = ParagraphStyle(
        "SubtituloPortada", parent=styles["Normal"], fontName=FUENTE_REGULAR, fontSize=12,
        textColor=rl_colors.HexColor(GRIS_TEXTO_SEC), alignment=TA_LEFT, spaceAfter=4)
    estilo_meta_portada = ParagraphStyle(
        "MetaPortada", parent=styles["Normal"], fontName=FUENTE_REGULAR, fontSize=9.5,
        textColor=rl_colors.HexColor(GRIS_TEXTO_SEC), alignment=TA_LEFT, leading=13)
    estilo_h1 = ParagraphStyle(
        "H1MG", parent=styles["Heading1"], fontName=FUENTE_BOLD, fontSize=15.5,
        textColor=rl_colors.HexColor(INBURSA_AZUL), spaceBefore=16, spaceAfter=8)
    estilo_h2 = ParagraphStyle(
        "H2MG", parent=styles["Heading2"], fontName=FUENTE_BOLD, fontSize=12.5,
        textColor=rl_colors.HexColor(INBURSA_AZUL), spaceBefore=18, spaceAfter=6)
    estilo_cuerpo = ParagraphStyle(
        "CuerpoMG", parent=styles["Normal"], fontName=FUENTE_REGULAR, fontSize=10,
        textColor=rl_colors.HexColor(MG_GRIS_OSCURO), leading=15, alignment=TA_LEFT, spaceAfter=8)
    estilo_nota = ParagraphStyle(
        "NotaMG", parent=styles["Normal"], fontSize=8.5,
        textColor=rl_colors.HexColor(GRIS_TEXTO_SEC), leading=11, alignment=TA_LEFT,
        spaceAfter=4, fontName=FUENTE_ITALICA)
    estilo_kpi_valor = ParagraphStyle(
        "KPIValor", parent=styles["Normal"], fontSize=20,
        textColor=rl_colors.HexColor(MG_GRIS_OSCURO), alignment=TA_CENTER,
        fontName=FUENTE_BOLD, leading=23)
    estilo_kpi_label = ParagraphStyle(
        "KPILabel", parent=styles["Normal"], fontName=FUENTE_BOLD, fontSize=7.8,
        textColor=rl_colors.HexColor(GRIS_TEXTO_SEC), alignment=TA_CENTER, leading=9.5)
    estilo_encabezado_tabla = ParagraphStyle(
        "EncabezadoTabla", parent=styles["Normal"], fontSize=8.3, leading=10,
        textColor=rl_colors.HexColor(INBURSA_AZUL), fontName=FUENTE_BOLD, alignment=TA_CENTER)
    # Estilo base de las celdas del cuerpo: `splitLongWords` + `hyphenationLang`
    # apagado evita cortes raros, y el Paragraph garantiza el salto de línea.
    estilo_celda_base = ParagraphStyle(
        "CeldaTablaBase", parent=styles["Normal"], fontName=FUENTE_REGULAR,
        fontSize=8.2, leading=10.2, textColor=rl_colors.HexColor(MG_GRIS_OSCURO),
        alignment=TA_LEFT, splitLongWords=1, spaceBefore=0, spaceAfter=0)

    def encabezado_pie_pagina(canvas_obj, doc):
        """Encabezado y pie: el dibujo vive en pdf_util.pintar_encabezado_pie,
        compartido por los cuatro reportes."""
        _pdf_util.pintar_encabezado_pie(
            canvas_obj, doc, NOMBRE_EMPRESA, f"Resumen Mensual Individual · {vendedor}", MES_TITULO, NOMBRE_ANALISTA,
            fuente_regular=FUENTE_REGULAR, fuente_bold=FUENTE_BOLD)

    def celda(texto, alineacion="left", negrita=False, color=None, tam=8.2):
        """Convierte cualquier valor en un Paragraph, que es lo ÚNICO que
        ReportLab sabe partir en varias líneas dentro de una celda. Si se
        pasa texto plano a una Table, el contenido se dibuja en una sola
        línea y se desborda encima de la columna vecina (que era justo el
        problema con los nombres de cliente y vehículos largos)."""
        if isinstance(texto, Flowable):
            return texto
        estilo = estilo_celda_base.clone(
            f"Celda_{alineacion}_{int(negrita)}_{color or 'def'}_{tam}",
            alignment={"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}[alineacion],
            fontName=FUENTE_BOLD if negrita else FUENTE_REGULAR,
            fontSize=tam,
            leading=tam * 1.25,
            textColor=rl_colors.HexColor(color) if color else rl_colors.HexColor(MG_GRIS_OSCURO),
        )
        return Paragraph(_texto_seguro(texto), estilo)

    def tabla_estilo_mg(data, col_widths=None, alinear_derecha_desde=1,
                        alineaciones=None, tam_fuente=8.2, fila_total=False,
                        ajustar_al_contenido=True, ancho_total=None):
        """Tabla 'corporativa moderna': encabezado azul Inbursa, sin líneas
        verticales (solo reglas horizontales finas), zebrado casi blanco y
        un filete rojo MG bajo el encabezado como acento.

        TODAS las celdas se envuelven en Paragraph, de modo que el texto
        largo se acomoda en varias líneas dentro de su propia columna en
        vez de encimarse con la siguiente.
        """
        n_cols = len(data[0])
        if alineaciones is None:
            alineaciones = [
                "left" if j < alinear_derecha_desde else "center" for j in range(n_cols)
            ]

        encabezado = [Paragraph(_texto_seguro(c), estilo_encabezado_tabla) for c in data[0]]
        cuerpo = []
        for i, fila in enumerate(data[1:]):
            es_total = fila_total and i == len(data) - 2
            cuerpo.append([
                celda(v, alineacion=alineaciones[j] if j < len(alineaciones) else "center",
                      negrita=es_total, tam=tam_fuente)
                for j, v in enumerate(fila)
            ])
        data = [encabezado] + cuerpo

        if col_widths is None and ajustar_al_contenido:
            col_widths = anchos_ajustados(data, ancho_total=ancho_total, tam_fuente=tam_fuente)

        tabla = Table(data, colWidths=col_widths, repeatRows=1, hAlign="CENTER")
        n_filas = len(data)
        # Formato compartido (pdf_util.estilo_tabla): encabezado claro con
        # texto azul, sin zebrado ni recuadro, fila de totales en azul.
        estilo = _pdf_util.estilo_tabla(
            n_filas, alinear_desde=alinear_derecha_desde, compacta=False,
            fila_total=fila_total, fuente_regular=FUENTE_REGULAR,
            fuente_bold=FUENTE_BOLD, color_texto=MG_GRIS_OSCURO)
        tabla.setStyle(TableStyle(estilo))
        return tabla

    def tarjeta_kpi(valor, etiqueta, color_acento):
        """Tarjeta KPI 'plana' corporativa: fondo blanco, barra de acento
        delgada arriba y el número protagonizando en el color de acento."""
        estilo_valor_acento = estilo_kpi_valor.clone("KPIValorAcento", textColor=rl_colors.HexColor(INBURSA_AZUL))
        t = Table(
            [[""], [Paragraph(str(valor), estilo_valor_acento)], [Paragraph(str(etiqueta).upper(), estilo_kpi_label)]],
            colWidths=[_pdf_util.ANCHO_KPI], rowHeights=[0.11 * cm, None, None]
        )
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), rl_colors.white),
            ("TOPPADDING", (0, 1), (-1, 1), 10),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 1),
            ("TOPPADDING", (0, 2), (-1, 2), 0),
            ("BOTTOMPADDING", (0, 2), (-1, 2), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    def pct_de(n):
        return (n / total_v * 100) if total_v else 0

    financiado = resumen_v.get("financiado", 0)
    aprobado = resumen_v.get("aprobado", 0)
    rechazado = resumen_v.get("rechazado", 0)
    en_tramite = resumen_v.get("contrapropuesta", 0)

    # -------------------------------------------------------------
    # Construcción del documento
    # -------------------------------------------------------------
    elementos = []

    # --- Portada ---
    elementos.append(Spacer(1, 0.2 * cm))
    elementos.append(Paragraph("RESUMEN MENSUAL&nbsp;&nbsp;·&nbsp;&nbsp;DESEMPEÑO INDIVIDUAL", estilo_kicker_portada))
    elementos.append(Paragraph("Resumen Mensual de Desempeño", estilo_titulo_portada))
    elementos.append(Paragraph(vendedor, estilo_nombre_portada))
    elementos.append(Paragraph(f"{NOMBRE_EMPRESA} · {SUBTITULO_EMPRESA}", estilo_subtitulo_portada))
    elementos.append(Spacer(1, 0.12 * cm))
    elementos.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor(GRIS_LINEA),
                                 spaceBefore=6, spaceAfter=10, hAlign="LEFT"))
    elementos.append(Paragraph(f"Periodo: <b>{MES_TITULO}</b>", estilo_meta_portada))
    elementos.append(Spacer(1, 0.45 * cm))

    intro_portada = Table(
        [[Paragraph(
            f"Este reporte resume tu desempeño individual durante <b>{MES_TITULO}</b>: gestionaste "
            f"<b>{total_v}</b> solicitud{'es' if total_v != 1 else ''} de crédito automotriz, de las "
            f"cuales <b>{financiado}</b> se convirtieron en crédito <b>FINANCIADO</b> (dispersado). "
            f"Incluye tu detalle de solicitudes del mes, la colocación del seguro GAP y cómo te "
            f"comparas frente al promedio del equipo.",
            estilo_cuerpo
        )]],
        colWidths=[_pdf_util.ANCHO_UTIL]
    )
    intro_portada.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    _pdf_util.como_entrada(intro_portada)
    elementos.append(intro_portada)
    elementos.append(Spacer(1, 0.45 * cm))

    # Cifras clave: en el PDF se dibujan como la columna lateral de la
    # portada (pdf_util.construir_con_lateral); en el Word quedan como tabla.
    elementos.append(_lateral.bloque_cifras(_lateral.cifras_vendedor(resumen_v["df_equipo"], vendedor)))
    elementos.append(Spacer(1, 0.5 * cm))

    # --- Resumen Ejecutivo ---
    elementos.append(Paragraph("Resumen Ejecutivo", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    elementos.append(Paragraph("Panorama del mes", estilo_h2))
    elementos.append(Paragraph(
        f"Durante {MES_TITULO} gestionaste {total_v} solicitud{'es' if total_v != 1 else ''}: "
        f"{financiado} ({pct_de(financiado):.1f}%) quedaron <b>FINANCIADAS</b>, {aprobado} "
        f"({pct_de(aprobado):.1f}%) <b>APROBADAS</b> pendientes de dispersar, {rechazado} "
        f"({pct_de(rechazado):.1f}%) <b>RECHAZADAS</b> y {en_tramite} ({pct_de(en_tramite):.1f}%) "
        f"en <b>CONTRAPROPUESTA</b> o negociación.",
        estilo_cuerpo
    ))
    if resumen_v.get("monto_financiado"):
        texto_monto = f"El monto financiado (ya dispersado) que generaste en el mes fue de <b>${resumen_v['monto_financiado']:,.2f}</b>"
        if "ticket_financiado" in resumen_v:
            texto_monto += f", con un ticket promedio de ${resumen_v['ticket_financiado']:,.2f} por crédito."
        else:
            texto_monto += "."
        if resumen_v.get("monto_aprobado"):
            texto_monto += f" Además, tienes ${resumen_v['monto_aprobado']:,.2f} en solicitudes APROBADAS a la espera de dispersarse."
        elementos.append(Paragraph(_pdf_util.resaltar(texto_monto), estilo_cuerpo))
    elif resumen_v.get("monto_aprobado"):
        elementos.append(Paragraph(
            f"Aún no tienes monto FINANCIADO (dispersado) este mes, pero tienes "
            f"<b>${resumen_v['monto_aprobado']:,.2f}</b> en solicitudes APROBADAS a la espera de dispersarse.",
            estilo_cuerpo
        ))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph("Tu posición en el equipo", estilo_h2))
    partes_equipo = []
    if resumen_v.get("rank_total"):
        partes_equipo.append(
            f"En volumen de solicitudes ocupas el lugar <b>{resumen_v['rank_total']} de {resumen_v['rank_total_de']}</b> "
            f"del equipo (promedio del equipo: {resumen_eq.get('promedio_solicitudes_por_vendedor', 0):.1f} solicitudes por vendedor)."
        )
    if resumen_v.get("rank_financiado"):
        partes_equipo.append(
            f"En créditos FINANCIADOS ocupas el lugar <b>{resumen_v['rank_financiado']} de {resumen_v['rank_financiado_de']}</b> "
            f"(promedio del equipo: {resumen_eq.get('promedio_financiado_por_vendedor', 0):.1f})."
        )
    if "pct_financiado" in resumen_v and "promedio_pct_financiado" in resumen_eq:
        diferencia = resumen_v["pct_financiado"] - resumen_eq["promedio_pct_financiado"]
        comparativo = "por arriba" if diferencia >= 0 else "por debajo"
        partes_equipo.append(
            f"Tu tasa de conversión a financiado es de {resumen_v['pct_financiado']:.1f}%, "
            f"{abs(diferencia):.1f} puntos {comparativo} del promedio del equipo "
            f"({resumen_eq['promedio_pct_financiado']:.1f}%)."
        )
    if partes_equipo:
        elementos.append(Paragraph(_pdf_util.resaltar(" ".join(partes_equipo)), estilo_cuerpo))
    else:
        elementos.append(Paragraph(
            "No fue posible calcular tu posición en el equipo con los datos disponibles.", estilo_nota
        ))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph("Seguro GAP", estilo_h2))
    if "pct_gap" in resumen_v:
        texto_gap = f"{resumen_v.get('n_gap', 0)} de tus {total_v} solicitudes ({resumen_v['pct_gap']:.1f}%) incluyeron seguro GAP"
        if "pct_gap_equipo" in resumen_eq:
            dif_gap = resumen_v["pct_gap"] - resumen_eq["pct_gap_equipo"]
            comp_gap = "por arriba" if dif_gap >= 0 else "por debajo"
            texto_gap += f", {abs(dif_gap):.1f} puntos {comp_gap} del promedio del equipo ({resumen_eq['pct_gap_equipo']:.1f}%)"
        texto_gap += "."
        if resumen_v.get("gap_financiado"):
            texto_gap += f" De tus créditos FINANCIADOS, {resumen_v['gap_financiado']} llevaron GAP colocado."
        elementos.append(Paragraph(_pdf_util.resaltar(texto_gap), estilo_cuerpo))
    else:
        elementos.append(Paragraph("No se encontró información de GAP para tus solicitudes.", estilo_nota))
    elementos.append(Spacer(1, 0.3 * cm))

    if resumen_v.get("modelo_top"):
        elementos.append(Paragraph("Modelo + Solicitado", estilo_h2))
        elementos.append(Paragraph(
            f"Tu modelo con más solicitudes en el mes fue <b>{resumen_v['modelo_top']}</b>, "
            f"con {resumen_v['modelo_top_val']} solicitud{'es' if resumen_v['modelo_top_val'] != 1 else ''}.",
            estilo_cuerpo
        ))

    elementos.append(PageBreak())

    # ===============================================================
    # REPORTE DETALLADO
    # ===============================================================
    elementos.append(Paragraph("Reporte Detallado", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    # --- 1. Tus solicitudes del mes ---
    elementos.append(Paragraph("1. Tus Solicitudes del Mes", estilo_h2))
    elementos.append(Paragraph(
        "Detalle de cada solicitud que gestionaste durante el mes, con su estatus, vehículo, "
        "monto a financiar y si incluyó seguro GAP.",
        estilo_cuerpo
    ))
    mapa_detalle = [
        ("Folio CCK",                "Folio",             "left"),
        ("Nombre Completo",          "Cliente",           "left"),
        ("Vehículo",                 "Vehículo",          "left"),
        ("Categoria",                "Estatus",           "center"),
        ("Monto Total a Financiar",  "Monto a Financiar", "right"),
        ("¿Tiene GAP?",              "GAP",               "center"),
    ]
    cols_detalle = [(c, e, a) for c, e, a in mapa_detalle if c in df_v.columns]

    if cols_detalle:
        # Se ordenan las solicitudes por estatus (financiadas primero) y
        # luego por monto, para que la tabla se lea como un ranking y no
        # en el orden arbitrario de captura de la bitácora.
        df_det = df_v.copy()
        if "Categoria" in df_det.columns:
            df_det["_orden"] = df_det["Categoria"].apply(
                lambda c: ORDEN_CATEGORIAS.index(c) if c in ORDEN_CATEGORIAS else len(ORDEN_CATEGORIAS)
            )
            orden_por = ["_orden"]
            if "Monto Total a Financiar" in df_det.columns:
                orden_por.append("Monto Total a Financiar")
                df_det = df_det.sort_values(orden_por, ascending=[True, False])
            else:
                df_det = df_det.sort_values(orden_por)

        # El año del modelo se fusiona en la columna del vehículo: da más
        # información sin gastar una columna extra de ancho.
        tiene_anio = "Año Modelo" in df_det.columns

        encabezados_d = [e for _, e, _ in cols_detalle]
        alineaciones_d = [a for _, _, a in cols_detalle]
        filas_d = []
        for _, fila in df_det.iterrows():
            f = []
            for col, _, alineacion in cols_detalle:
                valor = fila[col]
                if col == "Monto Total a Financiar":
                    f.append(f"${valor:,.0f}" if pd.notna(valor) else "—")
                elif col == "Vehículo":
                    texto_v = str(valor).strip() if pd.notna(valor) else "—"
                    if tiene_anio and pd.notna(fila.get("Año Modelo")):
                        try:
                            texto_v = f"{texto_v} {int(fila['Año Modelo'])}"
                        except (ValueError, TypeError):
                            pass
                    f.append(texto_v)
                elif col == "Categoria":
                    # El estatus se colorea con el color de su categoría
                    # para localizar de un vistazo financiados/rechazados.
                    cat = str(valor).strip().upper() if pd.notna(valor) else "—"
                    f.append(celda(cat, alineacion="center", negrita=True,
                                   color=COLOR_CATEGORIA_TEXTO.get(cat, MG_GRIS_OSCURO), tam=7.6))
                elif col == "¿Tiene GAP?":
                    texto_gap = str(valor).strip().upper() if pd.notna(valor) else "—"
                    f.append("Sí" if texto_gap in ("SI", "SÍ") else ("No" if texto_gap == "NO" else "—"))
                else:
                    f.append(str(valor) if pd.notna(valor) else "—")
            filas_d.append(f)

        # Fila de totales: suma del monto y conteo de GAP, para cerrar la
        # tabla con el dato agregado que antes había que sacar a mano.
        fila_totales = []
        for col, _, _ in cols_detalle:
            if col == "Folio CCK":
                fila_totales.append(f"TOTAL ({len(df_det)})")
            elif col == "Monto Total a Financiar":
                suma = df_det[col].sum(skipna=True)
                fila_totales.append(f"${suma:,.0f}" if pd.notna(suma) else "—")
            elif col == "¿Tiene GAP?":
                fila_totales.append(str(int((df_det[col].astype(str).str.strip().str.upper() == "SI").sum())))
            else:
                fila_totales.append("")
        if cols_detalle[0][0] != "Folio CCK":
            fila_totales[0] = f"TOTAL ({len(df_det)})"
        filas_d.append(fila_totales)

        elementos.append(tabla_estilo_mg(
            [encabezados_d] + filas_d,
            alineaciones=alineaciones_d,
            tam_fuente=8.0,
            fila_total=True,
        ))
        elementos.append(Paragraph(
            "Las solicitudes se muestran ordenadas por estatus (financiadas primero) "
            "y, dentro de cada estatus, de mayor a menor monto a financiar.",
            estilo_nota
        ))
    elementos.append(Spacer(1, 0.4 * cm))

    # --- 2. Distribución por estatus ---
    if "dona_status" in rutas_graficas:
        elementos.append(Paragraph("2. Distribución de tus Solicitudes por Estatus", estilo_h2))
        elementos.append(imagen_ajustada(rutas_graficas["dona_status"], ancho_cm=12, alto_max_cm=11))
        elementos.append(Spacer(1, 0.4 * cm))

    # --- 3. Comparativo con el equipo ---
    elementos.append(KeepTogether([
        Paragraph("3. Comparativo con el Equipo", estilo_h2),
        Paragraph(
            "Esta gráfica compara tu volumen de solicitudes, por categoría de cierre, contra el resto "
            "del equipo (mostrado en gris, sin detalle individual de cada compañero).",
            estilo_cuerpo
        ),
    ]))
    if "equipo_destacado" in rutas_graficas:
        elementos.append(imagen_ajustada(rutas_graficas["equipo_destacado"], ancho_cm=16, alto_max_cm=13))
        elementos.append(Spacer(1, 0.2 * cm))

    filas_comp = [
        ["Total de solicitudes", str(total_v), f"{resumen_eq.get('promedio_solicitudes_por_vendedor', 0):.1f}"],
        ["Créditos financiados", str(financiado), f"{resumen_eq.get('promedio_financiado_por_vendedor', 0):.1f}"],
        ["% Conversión a financiado", f"{resumen_v.get('pct_financiado', 0):.1f}%", f"{resumen_eq.get('promedio_pct_financiado', 0):.1f}%"],
        ["% Solicitudes con GAP", f"{resumen_v.get('pct_gap', 0):.1f}%", f"{resumen_eq.get('pct_gap_equipo', 0):.1f}%"],
    ]
    elementos.append(KeepTogether(tabla_estilo_mg(
        [["Métrica", "Tú", "Promedio del Equipo"]] + filas_comp,
        col_widths=[ANCHO_UTIL * 0.46, ANCHO_UTIL * 0.27, ANCHO_UTIL * 0.27],
        alineaciones=["left", "center", "center"],
        tam_fuente=9,
    )))
    elementos.append(Spacer(1, 0.4 * cm))

    # --- 4. Modelos + Solicitados ---
    if "modelos" in rutas_graficas:
        elementos.append(Paragraph("4. Modelos + Solicitados", estilo_h2))
        elementos.append(imagen_ajustada(rutas_graficas["modelos"], ancho_cm=15, alto_max_cm=10))
        elementos.append(Spacer(1, 0.4 * cm))

    # ===============================================================
    # CONCLUSIONES
    # ===============================================================
    elementos.append(Paragraph("Conclusiones y Factores Importantes", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    # Criterios compartidos con los demás reportes (herramientas/conclusiones.py):
    # se compara contra la conversión REAL del equipo, el GAP que se mide es
    # el colocado en créditos financiados, y con pocas solicitudes se dice
    # explícitamente que la comparación todavía no es justa.
    conclusiones = _conclusiones.conclusiones_vendedor(resumen_v["df_equipo"], vendedor)
    if not conclusiones:
        conclusiones = ["No hay datos suficientes para una lectura automática de este mes."]

    for c in conclusiones:
        elementos.append(Paragraph(_pdf_util.resaltar("•  " + c), estilo_cuerpo))

    # -------------------------------------------------------------
    # Generar el PDF
    # -------------------------------------------------------------
    doc = SimpleDocTemplate(
        nombre_archivo, pagesize=letter,
        topMargin=_pdf_util.MARGEN_SUPERIOR, bottomMargin=_pdf_util.MARGEN_INFERIOR,
        leftMargin=MARGEN_IZQ, rightMargin=MARGEN_DER,
        title=f"Resumen Mensual {vendedor} — {MES_TITULO}",
        author=NOMBRE_EMPRESA, subject="Resumen mensual de desempeño individual",
    )
    # Sin esto, un Spacer que no cabe al final de una página genera una
    # hoja en blanco antes del siguiente salto. Ver pdf_util.py.
    elementos[:] = _pdf_util.pulir(_pdf_util.quitar_espacios_antes_de_salto(elementos))
    _pdf_util.construir_con_lateral(doc, elementos, encabezado_pie_pagina)
    return nombre_archivo


# =======================================================================
# 9) FLUJO PRINCIPAL
# =======================================================================
def main(ruta_local=None, mes_anio=None, vendedores_incluir=None):
    """
    ruta_local: ruta del Excel a usar fuera de Colab (si es None y estás
    en Colab, te pedirá subirlo).
    mes_anio: opcional, para forzar el mes/año del reporte, ej. "agosto 2026".
    vendedores_incluir: opcional, lista de nombres para generar el PDF
    solo de esos vendedores (por defecto, genera el de TODOS).
    """
    df_crudo, nombre_archivo_origen, hoja = cargar_archivo(ruta_local=ruta_local)
    df = limpiar_datos(df_crudo)
    ctx_mes = contexto_mensual(mes_anio=mes_anio, hoja_nombre=hoja)

    if "Nombre del Vendedor" not in df.columns:
        raise ValueError("No se encontró la columna 'Nombre del Vendedor' en el archivo.")

    tabla_vendedor = analisis_por_vendedor(df)
    resumen_eq = resumen_equipo(df, tabla_vendedor)

    print("=" * 72)
    print(f" RESUMEN MENSUAL POR VENDEDOR — {ctx_mes['nombre_mes'].capitalize()} {ctx_mes['anio']}")
    print("=" * 72)
    display(tabla_vendedor)

    vendedores = sorted(df["Nombre del Vendedor"].dropna().unique().tolist())
    if vendedores_incluir:
        solicitados = {str(v).strip().title() for v in vendedores_incluir}
        no_encontrados = solicitados - set(vendedores)
        if no_encontrados:
            print(f"Aviso: estos vendedores no están en el archivo y se omiten: {sorted(no_encontrados)}")
        vendedores = [v for v in vendedores if v in solicitados]

    if not vendedores:
        print("No hay vendedores que procesar con los filtros indicados.")
        return df, []

    rutas_generadas = []
    for vendedor in vendedores:
        resumen_v = analisis_individual(df, vendedor, tabla_vendedor, resumen_eq)
        rutas_graficas = generar_graficas_vendedor(df, resumen_v["df"], vendedor)
        ruta_pdf = generar_reporte_pdf_vendedor(
            vendedor, resumen_v, tabla_vendedor, resumen_eq, ctx_mes, rutas_graficas
        )
        rutas_generadas.append(ruta_pdf)
        print(f"  ✓ PDF generado: {ruta_pdf}")

    # -------------------------------------------------------------
    # Empaquetar todos los PDFs en un solo ZIP para descargar de un jalón
    # -------------------------------------------------------------
    nombre_zip = f"Resumenes_Mensuales_{ctx_mes['nombre_mes']}_{ctx_mes['anio']}.zip"
    with zipfile.ZipFile(nombre_zip, "w") as zf:
        for ruta in rutas_generadas:
            zf.write(ruta, arcname=os.path.basename(ruta))

    print("=" * 72)
    print(f" Se generaron {len(rutas_generadas)} reportes individuales.")
    print(f" Empaquetados en: {nombre_zip}")
    print("=" * 72)

    # Las gráficas ya quedaron incrustadas en los PDFs: se borra la carpeta
    # temporal para no dejar basura acumulándose entre corridas de Colab.
    shutil.rmtree(CARPETA_GRAFICAS, ignore_errors=True)
    os.makedirs(CARPETA_GRAFICAS, exist_ok=True)

    if EN_COLAB:
        files.download(nombre_zip)
    else:
        print(f"Archivos guardados en la carpeta: {CARPETA_PDFS}/  y en: {nombre_zip}")

    return df, rutas_generadas


if __name__ == "__main__":
    main()