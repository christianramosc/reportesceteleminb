"""Reporte Comparativo Mensual — Bitácora de Solicitudes MG Colima.

Compara 1 o más meses de la bitácora de solicitudes (mismo formato que el
avance preliminar) y genera un PDF con gráficas comparativas e insights
automáticos: evolución del volumen y las categorías de cierre, tasa de
conversión a FINANCIADO, panorama financiero, colocación de GAP y
desempeño de vendedores a lo largo del periodo comparado.

Cada mes se sube como un archivo Excel independiente (mismo formato que
usa el avance preliminar). El nombre del mes se toma, por default, del
nombre de la primera hoja del Excel (ej. "JULIO").
"""

import os
from . import fechas as _fechas   # hora de México, no la del servidor
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors as rl_colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Spacer, HRFlowable, KeepTogether, CondPageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from xml.sax.saxutils import escape as _xml_escape


# =======================================================================
# LO COMPARTIDO CON LOS DEMÁS REPORTES
# La paleta, las fuentes, el estilo de las gráficas (plt.rcParams), las
# columnas esperadas, la limpieza de montos y porcentajes y 5 gráficas
# (vendedores, estatus por vendedor, GAP, GAP en financiados y modelos)
# viven en reporte_base.py. Antes este archivo tenía su propia copia de
# todo eso. El catálogo de estatus está en estatus.py.
# =======================================================================
from . import estatus as _est
from . import conclusiones as _conclusiones
from . import pdf_util as _pdf_util
from . import lateral as _lateral
from . import folios as _folios
from . import hallazgos as _h
from .config import DatosReporte
# Paragraph que tolera "&" y "<" en los nombres de la bitácora.
from .pdf_util import Parrafo as Paragraph
from .reporte_base import limpiar_datos as _limpiar_datos_base
from .reporte_base import (  # paleta, fuentes, limpieza y gráficas compartidas
    COLOR_CATEGORIA,
    FUENTE_BOLD,
    FUENTE_REGULAR,
    GRIS_LINEA,
    INBURSA_AZUL,
    MG_GRIS_CLARO,
    MG_GRIS_OSCURO,
    MG_ROJO_OSCURO,
    ORDEN_CATEGORIAS,
    _MESES_ES,
    _color_texto_legible,
    _guardar_si_procede,
    SIN_VENDEDOR,
    crear_estilos,
    exigir_solicitudes,
    grafica_gap_financiado_por_vendedor,
    grafica_gap_por_vendedor_total,
    grafica_modelos,
    grafica_vendedor_status,
    grafica_vendedores,
    imagen_ajustada,
)




# =======================================================================
# 2) CARGA DE ARCHIVOS — uno o más meses
# =======================================================================
def _orden_mes(etiqueta_mes):
    """Ubica el nombre del mes dentro del calendario (0=enero..11=diciembre)
    buscando el nombre del mes en español dentro de la etiqueta, sin importar
    mayúsculas/año pegado (ej. "JULIO 2026" -> julio). Si no se reconoce
    ningún mes, regresa 999 para que quede al final, en el orden en que se subió."""
    texto = str(etiqueta_mes).strip().lower()
    for i, nombre in enumerate(_MESES_ES):
        if nombre in texto:
            return i
    return 999


def cargar_multiples_archivos(rutas_locales, nombres_meses=None):
    """
    Abre los archivos Excel de la bitácora, uno por mes a comparar, y
    regresa una lista de tuplas (mes, dataframe_crudo).

    rutas_locales: lista de rutas a los archivos Excel.
    nombres_meses: lista opcional del mismo tamaño que rutas_locales, con
        la etiqueta de mes a usar para cada archivo (ej. ["JULIO", "AGOSTO"]).
        Si no se indica, se usa el nombre de la primera hoja de cada Excel.
    """
    rutas = list(rutas_locales or [])
    if not rutas:
        raise ValueError("No se proporcionó ningún archivo para comparar.")

    if nombres_meses and len(nombres_meses) != len(rutas):
        print("Aviso: 'nombres_meses' no coincide en longitud con los archivos "
              "subidos; se ignorará y se usará el nombre de hoja de cada Excel.")
        nombres_meses = None

    resultado = []
    for i, ruta in enumerate(rutas):
        with pd.ExcelFile(ruta) as xls:
            hoja = xls.sheet_names[0]
            if len(xls.sheet_names) > 1:
                print(f"'{ruta}' tiene varias hojas: {xls.sheet_names}. Se usará '{hoja}'.")
            df_crudo = xls.parse(hoja)
        exigir_solicitudes(df_crudo, ruta, hoja)
        mes = (nombres_meses[i].strip().upper() if nombres_meses
               else str(hoja).strip().upper())
        print(f"Archivo cargado: {ruta}  |  Mes: {mes}  |  Hoja: {hoja}  |  {len(df_crudo)} solicitudes")
        resultado.append((mes, df_crudo))
    print()
    return resultado


# =======================================================================
# 3) LIMPIEZA Y NORMALIZACIÓN — idéntico al avance preliminar
# =======================================================================


def limpiar_datos(df_original, mes=None):
    """La limpieza es la de reporte_base (la misma de los demás reportes);
    aquí solo se agrega a qué mes pertenece cada fila."""
    df = _limpiar_datos_base(df_original, aviso=mes or "")
    if mes is not None:
        df["Mes"] = mes
    return df


# =======================================================================
# 4) CÁLCULOS POR MES — resumen general, por vendedor y por categoría
#    (mismas funciones que el avance preliminar, reutilizadas mes a mes)
# =======================================================================
def resumen_general(df, mes=None, silencioso=False):
    if not silencioso:
        print("-" * 72)
        print(f" RESUMEN — {mes}" if mes else " RESUMEN GENERAL")
        print("-" * 72)

    total = len(df)
    r = {"total": total, "mes": mes}

    if "Categoria" in df.columns:
        conteo_cat = df["Categoria"].value_counts()

        # Conteo de TODAS las categorías del mes, no solo de cuatro fijas.
        conteo_categorias = {
            c: int(conteo_cat.get(c, 0)) for c in _est.categorias_presentes(df)
        }

        financiados = int(conteo_cat.get("FINANCIADO", 0))
        aprobados   = int(conteo_cat.get("APROBADO", 0))
        rechazados  = int(conteo_cat.get("RECHAZADO", 0))

        # "en_tramite" agrupa todo lo que quedó sin resolver (contrapropuesta,
        # en proceso, en revisión, pendiente...), excepto lo ya aprobado.
        claves_abiertas = [c for c in _est.claves_por_grupo(_est.ABIERTA)
                           if c != "APROBADO"]
        en_tramite = sum(int(conteo_cat.get(c, 0)) for c in claves_abiertas)

        r.update({"financiados": financiados, "aprobados": aprobados,
                   "rechazados": rechazados, "en_tramite": en_tramite,
                   "conteo_categorias": conteo_categorias})
        if not silencioso:
            detalle = "  |  ".join(
                f"{_est.etiqueta(c)}: {n}" for c, n in conteo_categorias.items()
            )
            print(f"Total: {total}  |  {detalle}")
    else:
        financiados = aprobados = 0

    monto_col = "Monto Total a Financiar"
    if monto_col in df.columns:
        r["monto_total"] = df[monto_col].sum()
        if "Categoria" in df.columns:
            r["monto_financiado"] = df.loc[df["Categoria"] == "FINANCIADO", monto_col].sum()
            r["monto_aprobado"] = df.loc[df["Categoria"] == "APROBADO", monto_col].sum()
            if financiados:
                r["ticket_financiado"] = df.loc[df["Categoria"] == "FINANCIADO", monto_col].mean()
            if aprobados:
                r["ticket_aprobado"] = df.loc[df["Categoria"] == "APROBADO", monto_col].mean()

    if "Enganche" in df.columns and "Precio Venta (c/IVA)" in df.columns:
        r["pct_enganche"] = (df["Enganche"] / df["Precio Venta (c/IVA)"] * 100).mean()

    if "Plazo (meses)" in df.columns:
        r["plazo_promedio"] = df["Plazo (meses)"].mean()

    if "Tasa Interés Anual" in df.columns:
        r["tasa_promedio"] = df["Tasa Interés Anual"].mean()

    if "¿Tiene GAP?" in df.columns:
        r["pct_gap"] = (df["¿Tiene GAP?"] == "SI").mean() * 100
        r["n_gap"] = int((df["¿Tiene GAP?"] == "SI").sum())
        if "Categoria" in df.columns and financiados:
            n_gap_financiado = int(((df["Categoria"] == "FINANCIADO") & (df["¿Tiene GAP?"] == "SI")).sum())
            r["n_gap_financiado"] = n_gap_financiado
            r["pct_gap_financiado"] = n_gap_financiado / financiados * 100

    cols_clave = [c for c in ["Marca", "Vehículo", "Monto Total a Financiar"] if c in df.columns]
    if cols_clave:
        r["incompletas"] = int(df[cols_clave].isna().any(axis=1).sum())

    if not silencioso:
        print()
    return r


def analisis_por_vendedor(df):
    if "Nombre del Vendedor" not in df.columns:
        return None
    total_por_vendedor = df.groupby("Nombre del Vendedor").size().rename("Total")
    tabla = pd.DataFrame({"Total": total_por_vendedor})

    if "Categoria" in df.columns:
        pivote = pd.crosstab(df["Nombre del Vendedor"], df["Categoria"])
        presentes = _est.categorias_presentes(df)
        for col in presentes:
            if col not in pivote.columns:
                pivote[col] = 0
        tabla = tabla.join(pivote[presentes])
        # Un mes puede no tener algún estatus (septiembre 2026 no tuvo ninguna
        # APROBADA). Antes esto tronaba con KeyError: 'APROBADO'. Mismo
        # criterio que reporte_base.py: si el estatus no está, cuenta cero.
        aprobado_v = tabla["APROBADO"] if "APROBADO" in tabla.columns else 0
        financiado_v = tabla["FINANCIADO"] if "FINANCIADO" in tabla.columns else 0
        tabla["% Aprobación"] = (aprobado_v / tabla["Total"] * 100).round(1)
        tabla["% Financiado"] = (financiado_v / tabla["Total"] * 100).round(1)

    if "Monto Total a Financiar" in df.columns and "Categoria" in df.columns:
        monto_financiado = (df[df["Categoria"] == "FINANCIADO"]
                             .groupby("Nombre del Vendedor")["Monto Total a Financiar"]
                             .sum().rename("Monto Financiado ($)"))
        monto_aprobado = (df[df["Categoria"] == "APROBADO"]
                           .groupby("Nombre del Vendedor")["Monto Total a Financiar"]
                           .sum().rename("Monto Aprobado ($)"))
        tabla = tabla.join(monto_financiado).join(monto_aprobado)
        tabla[["Monto Financiado ($)", "Monto Aprobado ($)"]] = tabla[
            ["Monto Financiado ($)", "Monto Aprobado ($)"]].fillna(0)

    if "¿Tiene GAP?" in df.columns:
        gap_total_v = df[df["¿Tiene GAP?"] == "SI"].groupby("Nombre del Vendedor").size()
        tabla["GAP Total"] = gap_total_v.reindex(tabla.index).fillna(0).astype(int)
        if "Categoria" in df.columns:
            gap_fin_v = (df[(df["Categoria"] == "FINANCIADO") & (df["¿Tiene GAP?"] == "SI")]
                         .groupby("Nombre del Vendedor").size())
            tabla["GAP Financiado"] = gap_fin_v.reindex(tabla.index).fillna(0).astype(int)

    return tabla.sort_values("Total", ascending=False)


def analisis_financiero_por_categoria(df):
    if "Categoria" not in df.columns:
        return None
    columnas_interes = [c for c in [
        "Precio Venta (c/IVA)", "Enganche", "Monto Total a Financiar",
        "Plazo (meses)", "Tasa Interés Anual",
    ] if c in df.columns]
    if not columnas_interes:
        return None
    tabla = df.groupby("Categoria")[columnas_interes].mean().round(2)
    orden_presente = [c for c in ORDEN_CATEGORIAS if c in tabla.index]
    tabla = tabla.reindex(orden_presente)
    if "¿Tiene GAP?" in df.columns:
        tabla["% con GAP"] = ((df["¿Tiene GAP?"] == "SI").groupby(df["Categoria"])
                               .mean().mul(100).round(1)).reindex(orden_presente)
    return tabla


def _lista_vendedores_por_categoria(df, categoria, max_nombres=4):
    nombres = (df.loc[df["Categoria"] == categoria, "Nombre del Vendedor"]
               .dropna().unique().tolist())
    primeros = sorted({n.split()[0] for n in nombres if n and n != "Nan"})
    if not primeros:
        return "—"
    if len(primeros) > max_nombres:
        return ", ".join(primeros[:max_nombres]) + f" +{len(primeros) - max_nombres} más"
    return ", ".join(primeros)


# =======================================================================
# 5) TABLA COMPARATIVA MENSUAL
# =======================================================================
def etiqueta_columna_abiertas(datos_por_mes):
    """Nombre de la columna que agrupa las solicitudes todavía abiertas.

    Esa columna suma TODAS las categorías abiertas que no son APROBADO
    (contrapropuesta, en revisión, análisis, pendiente...). Ponerle un
    nombre fijo de una sola categoría sería mentir en cuanto aparezca otra.

    Pero llamarla "En trámite" cuando mes tras mes la única categoría
    abierta es CONTRAPROPUESTA esconde información que sí se tiene. Así que
    el nombre se decide con los datos: si en todo el periodo solo hay una
    categoría abierta, se usa su nombre real; si hay dos o más, se vuelve al
    genérico porque ya no describe a ninguna en particular.
    """
    presentes = set()
    for mes in datos_por_mes:
        conteo = datos_por_mes[mes]["resumen"].get("conteo_categorias") or {}
        for clave, cantidad in conteo.items():
            if clave != "APROBADO" and int(cantidad) > 0 \
                    and clave in _est.claves_por_grupo(_est.ABIERTA):
                presentes.add(clave)
    if len(presentes) == 1:
        return _est.etiqueta(next(iter(presentes)))
    return "En trámite"


def construir_tabla_comparativa(datos_por_mes, orden_meses):
    col_abiertas = etiqueta_columna_abiertas(datos_por_mes)
    """Arma una tabla (una fila por mes, en orden cronológico) con los
    indicadores clave para comparar el periodo completo de un vistazo."""
    filas = []
    for mes in orden_meses:
        r = datos_por_mes[mes]["resumen"]
        total = r.get("total", 0)
        financiados = r.get("financiados", 0)
        aprobados = r.get("aprobados", 0)
        filas.append({
            "Mes": mes.title(),
            "Total": total,
            "Financiado": financiados,
            "Aprobado": aprobados,
            # Agrupa todo lo que quedó abierto (contrapropuesta, en proceso,
            # en revisión, pendiente...). El encabezado lleva el nombre real
            # cuando solo hay una categoría abierta en el periodo; ver
            # etiqueta_columna_abiertas().
            col_abiertas: r.get("en_tramite", 0),
            "Rechazado": r.get("rechazados", 0),
            "% Financiado": round(financiados / total * 100, 1) if total else 0.0,
            "Monto Total": r.get("monto_total", np.nan),
            "Monto Financiado": r.get("monto_financiado", np.nan),
            "Ticket Prom. Financiado": r.get("ticket_financiado", np.nan),
            "% GAP": round(r.get("pct_gap", np.nan), 1) if "pct_gap" in r else np.nan,
            "% GAP Financiado": round(r.get("pct_gap_financiado", np.nan), 1) if "pct_gap_financiado" in r else np.nan,
        })
    return pd.DataFrame(filas).set_index("Mes")


# =======================================================================
# 6) GRÁFICAS — utilidades comunes
# =======================================================================
# --- 6A) Gráficas AGREGADAS del periodo completo (mismas del avance
#         preliminar, aplicadas al DataFrame combinado de todos los meses) ---
def tabla_ticket_promedio_vendedor(df_combinado):
    """Ticket promedio (monto financiado ÷ créditos financiados) por vendedor.

    Se calcula sobre TODO el periodo y no mes a mes a propósito: con pocos
    créditos financiados al mes por persona, un promedio mensual lo mueve
    una sola operación y deja de significar algo.
    """
    req = {"Nombre del Vendedor", "Categoria", "Monto Total a Financiar"}
    if not req.issubset(df_combinado.columns):
        return None

    fin = df_combinado[df_combinado["Categoria"] == "FINANCIADO"]
    if fin.empty:
        return None

    tabla = fin.groupby("Nombre del Vendedor")["Monto Total a Financiar"].agg(
        Financiados="size", Monto="sum")
    tabla["Ticket"] = (tabla["Monto"] / tabla["Financiados"]).round(0)

    # GAP, pero solo el colocado DENTRO de créditos financiados: ese ya está
    # efectivamente vendido. El % de GAP sobre todas las solicitudes vive en
    # la tabla financiera por mes e incluye expedientes que aún pueden caerse,
    # así que mezclarlos aquí haría ver mejor a quien coloca GAP en
    # solicitudes que nunca cierran.
    if "¿Tiene GAP?" in fin.columns:
        con_gap = fin["¿Tiene GAP?"] == "SI"
        tabla["GAP"] = con_gap.groupby(fin["Nombre del Vendedor"]).sum()
        tabla["GAP"] = tabla["GAP"].fillna(0).astype(int)
        tabla["% GAP"] = (tabla["GAP"] / tabla["Financiados"] * 100).round(0)
        if "Monto GAP" in fin.columns:
            montos = fin.loc[con_gap].groupby("Nombre del Vendedor")["Monto GAP"].sum()
            tabla["Monto GAP"] = montos.reindex(tabla.index).fillna(0)

    return tabla.sort_values("Monto", ascending=False)


def tabla_variacion_vendedor(df_combinado, orden_meses):
    """Quién subió y quién bajó entre el primer y el último mes comparado."""
    if "Nombre del Vendedor" not in df_combinado.columns or "Mes" not in df_combinado.columns:
        return None
    pivote = pd.crosstab(df_combinado["Nombre del Vendedor"], df_combinado["Mes"])
    meses = [m for m in orden_meses if m in pivote.columns]
    if len(meses) < 2:
        return None

    primero, ultimo = meses[0], meses[-1]
    tabla = pd.DataFrame({
        "Inicio": pivote[primero],
        "Fin": pivote[ultimo],
    })
    tabla["Variación"] = tabla["Fin"] - tabla["Inicio"]
    # Partir de cero no es un aumento porcentual medible: se marca así en vez
    # de mostrar un infinito o un 100% inventado.
    tabla["% Cambio"] = np.where(
        tabla["Inicio"] > 0,
        (tabla["Variación"] / tabla["Inicio"] * 100).round(0),
        np.nan,
    )
    return tabla.sort_values("Variación", ascending=False), primero, ultimo


def _recortar_nombre(nombre, maximo=26):
    """Acorta un nombre largo para que no descuadre la tabla ni la etiqueta.

    Se conserva el primer nombre y se abrevian los apellidos, en vez de
    cortar a lo bruto: "Luis Valentin Salvidar De La Mora" queda como
    "Luis Valentin S. D. L. M." y sigue siendo identificable.
    """
    if len(nombre) <= maximo:
        return nombre
    partes = nombre.split()
    if len(partes) <= 2:
        return nombre[:maximo - 1] + "…"
    resultado = " ".join(partes[:2] + [f"{p[0]}." for p in partes[2:]])
    return resultado if len(resultado) <= maximo else resultado[:maximo - 1] + "…"


def tabla_promedio_vendedor(df_combinado, orden_meses):
    """Promedio de solicitudes por mes de cada vendedor.

    Devuelve un DataFrame con una columna por mes más Total, Promedio y
    Variación (último mes contra el primero). El promedio se divide entre
    TODOS los meses comparados, no solo entre los meses en que el vendedor
    tuvo actividad: un asesor que no ingresó nada en un mes debe cargar ese
    cero, porque es justo lo que el reporte busca mostrar.
    """
    if "Nombre del Vendedor" not in df_combinado.columns or "Mes" not in df_combinado.columns:
        return None

    pivote = pd.crosstab(df_combinado["Nombre del Vendedor"], df_combinado["Mes"])
    meses = [m for m in orden_meses if m in pivote.columns]
    if not meses:
        return None

    tabla = pivote[meses].copy()
    tabla["Total"] = tabla.sum(axis=1)
    tabla["Promedio"] = (tabla["Total"] / len(meses)).round(1)

    if len(meses) >= 2:
        primero, ultimo = tabla[meses[0]], tabla[meses[-1]]
        tabla["Variación"] = ultimo - primero

    return tabla.sort_values("Total", ascending=False)


# --- 6B) Gráficas COMPARATIVAS entre meses (nuevas de este reporte) ---
def grafica_comp_totales_por_mes(datos_por_mes, orden_meses, guardar_como=None):
    """Barras apiladas por mes: cuántas solicitudes cerraron en cada categoría."""
    meses_disp = [m for m in orden_meses if "Categoria" in datos_por_mes[m]["df"].columns]
    if not meses_disp:
        return None
    etiquetas = [m.title() for m in meses_disp]

    # Solo las categorías que aparecen en ALGUNO de los meses comparados,
    # para no meter series en cero a la leyenda cuando el catálogo tiene
    # muchos estatus posibles.
    cats_presentes = []
    for cat in ORDEN_CATEGORIAS:
        if any(cat in set(datos_por_mes[m]["df"]["Categoria"]) for m in meses_disp):
            cats_presentes.append(cat)

    fig, ax = plt.subplots(figsize=(max(7, len(meses_disp) * 1.3), 5.5))
    abajo = np.zeros(len(meses_disp))
    for cat in cats_presentes:
        valores = np.array([
            int(datos_por_mes[m]["df"]["Categoria"].value_counts().get(cat, 0))
            for m in meses_disp
        ])
        ax.bar(etiquetas, valores, bottom=abajo, color=COLOR_CATEGORIA.get(cat, MG_GRIS_CLARO),
               edgecolor="white", label=_est.etiqueta(cat))
        for i, (v, b) in enumerate(zip(valores, abajo)):
            if v > 0:
                ax.text(i, b + v / 2, str(int(v)), ha="center", va="center",
                         fontsize=8.5, color=_color_texto_legible(COLOR_CATEGORIA.get(cat, MG_GRIS_CLARO)))
        abajo += valores
    totales = [int(datos_por_mes[m]["resumen"].get("total", 0)) for m in meses_disp]
    for i, t in enumerate(totales):
        ax.text(i, t + max(totales) * 0.02, f"Total: {t}", ha="center", va="bottom",
                 fontsize=9, fontweight="bold", color=MG_GRIS_OSCURO)
    ax.set_ylim(0, max(totales) * 1.18 if totales else 1)
    rechazos = [int(datos_por_mes[m]["df"]["Categoria"].value_counts().get("RECHAZADO", 0)) for m in meses_disp]
    _h.titular(ax, _h.rechazo_por_mes(meses_disp, totales, rechazos),
               "Solicitudes por estatus de cierre, por mes")
    ax.set_ylabel("Número de solicitudes")
    ax.legend(loc="upper center", bbox_to_anchor=(0, -0.30, 1, 0.16),
              mode="expand", frameon=False, fontsize=8,
              handlelength=1.4, columnspacing=1.2,
              ncol=min(3, max(1, len(cats_presentes))))
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def grafica_comp_tasa_conversion(tabla_comp, guardar_como=None):
    """Línea: % Financiado y % Aprobado por mes (tendencia de conversión)."""
    if tabla_comp.empty or "% Financiado" not in tabla_comp.columns:
        return None
    meses = tabla_comp.index.tolist()
    pct_fin = tabla_comp["% Financiado"].values
    pct_apr = ((tabla_comp["Aprobado"] / tabla_comp["Total"]).fillna(0) * 100).values \
        if "Aprobado" in tabla_comp.columns else np.zeros(len(meses))

    fig, ax = plt.subplots(figsize=(max(7, len(meses) * 1.3), 5.5))
    ax.plot(meses, pct_fin, marker="o", linewidth=2.4, color=MG_ROJO_OSCURO, label="% Financiado")
    ax.plot(meses, pct_apr, marker="o", linewidth=2.0, color=INBURSA_AZUL,
             linestyle="--", label="% Aprobado")
    # Los rótulos se colocan al final (etiquetas_lineas), cuando ya se
    # conoce la escala: con desplazamientos fijos chocaban si dos líneas
    # andaban cerca (15% financiado y 8% aprobado quedaban pegados).
    rotulos = [(pct_fin, MG_ROJO_OSCURO, dict(fontsize=9, fontweight="bold")),
               (pct_apr, INBURSA_AZUL, dict(fontsize=8.5))]
    # Rechazo: la "Lectura del periodo" explica la caída de conversión con el
    # rechazo; ahora la gráfica muestra esa evidencia junto a la conversión.
    pct_rech = ((tabla_comp["Rechazado"] / tabla_comp["Total"]).fillna(0) * 100).values \
        if "Rechazado" in tabla_comp.columns else None
    if pct_rech is not None:
        color_rech = COLOR_CATEGORIA.get("RECHAZADO", "#F4A6B1")
        ax.plot(meses, pct_rech, marker="o", linewidth=2.0, color=color_rech, linestyle=":", label="% Rechazado")
        rotulos.append((pct_rech, color_rech, dict(fontsize=8.5)))
    tope = max([x.max() for x in (pct_fin, pct_apr, pct_rech) if x is not None and len(x)] or [0])
    ax.set_ylim(0, tope * 1.3 + 5)
    _h.etiquetas_lineas(ax, rotulos)
    _h.titular(ax, _h.por_mes_minimo(meses, list(pct_fin), "la conversión"),
               "% de las solicitudes de cada mes: financiadas, aprobadas y rechazadas")
    ax.set_ylabel("% de las solicitudes del mes")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False, ncol=3)
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def grafica_comp_montos_por_mes(tabla_comp, guardar_como=None):
    """Barras agrupadas: monto financiado vs monto aprobado, por mes."""
    if tabla_comp.empty or "Monto Financiado" not in tabla_comp.columns:
        return None
    meses = tabla_comp.index.tolist()
    monto_fin = tabla_comp["Monto Financiado"].fillna(0).values
    monto_tot = tabla_comp["Monto Total"].fillna(0).values
    x = np.arange(len(meses))
    ancho = 0.38
    fig, ax = plt.subplots(figsize=(max(7, len(meses) * 1.4), 5.5))
    ax.bar(x - ancho / 2, monto_fin, width=ancho, color=MG_ROJO_OSCURO, edgecolor="white", label="Monto Financiado")
    ax.bar(x + ancho / 2, monto_tot, width=ancho, color=MG_GRIS_CLARO, edgecolor="white", label="Monto Total a Financiar (todas)")
    for xi, v in zip(x - ancho / 2, monto_fin):
        ax.text(xi, v + max(monto_tot.max(), 1) * 0.015, _h.monto_corto(v), ha="center", fontsize=8, rotation=90 if len(meses) > 4 else 0, va="bottom",
                zorder=4, bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none"))
    for xi, v in zip(x + ancho / 2, monto_tot):
        ax.text(xi, v + max(monto_tot.max(), 1) * 0.015, _h.monto_corto(v), ha="center", fontsize=8, rotation=90 if len(meses) > 4 else 0, va="bottom",
                zorder=4, bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none"))
    # Referencia: el promedio mensual financiado, la misma cifra de la portada.
    promedio = float(monto_fin.mean()) if len(monto_fin) else 0
    if promedio:
        # En la leyenda y no como rótulo: chocaba con la etiqueta de un mes
        # cercano al promedio (junio financió $1.80 M con promedio de $1.79 M).
        ax.axhline(promedio, color=INBURSA_AZUL, linestyle=(0, (4, 3)), linewidth=1.1, zorder=3,
                   label=f"Promedio mensual financiado ({_h.monto_corto(promedio)})")
    ax.set_xticks(x)
    ax.set_xticklabels(meses)
    _h.formato_millones(ax, eje="y")
    _h.titular(ax, _h.montos_por_mes(meses, list(monto_fin)),
               "Monto financiado vs. monto total solicitado, por mes")
    ax.set_ylabel("Monto (millones de pesos)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False, ncol=3, fontsize=8.5)
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def grafica_comp_gap_vs_gap_financiado(tabla_comp, guardar_como=None):
    """Líneas: % GAP (todas las solicitudes) vs % GAP Financiado (solo dentro
    de los créditos ya FINANCIADOS), por mes. Compara si el GAP se está
    colocando también en las solicitudes que sí terminan dispersándose."""
    if tabla_comp.empty or "% GAP Financiado" not in tabla_comp.columns or \
       tabla_comp["% GAP Financiado"].isna().all():
        return None

    meses = tabla_comp.index.tolist()
    pct_gap = tabla_comp["% GAP"].fillna(0).values if "% GAP" in tabla_comp.columns else None
    pct_gap_fin = tabla_comp["% GAP Financiado"].fillna(0).values

    fig, ax = plt.subplots(figsize=(max(7, len(meses) * 1.3), 5.5))
    ax.plot(meses, pct_gap_fin, marker="o", linewidth=2.4, color=MG_ROJO_OSCURO,
             label="% GAP Financiado")
    rotulos = [(pct_gap_fin, MG_ROJO_OSCURO, dict(fontsize=9, fontweight="bold"))]

    maximo = pct_gap_fin.max() if len(pct_gap_fin) else 0
    if pct_gap is not None:
        ax.plot(meses, pct_gap, marker="o", linewidth=2.0, color=INBURSA_AZUL,
                 linestyle="--", label="% GAP (todas las solicitudes)")
        rotulos.append((pct_gap, INBURSA_AZUL, dict(fontsize=8.5)))
        maximo = max(maximo, pct_gap.max() if len(pct_gap) else 0)

    # Hasta 108 para que se vea la línea de "lo esperado: todas" (100%).
    ax.set_ylim(0, 108)
    # Rótulos sin choques: con +3 fijo, dos líneas en el mismo valor (o a
    # pocos puntos) dejaban un número encima del otro.
    _h.etiquetas_lineas(ax, rotulos)
    _h.referencia_alerta_gap(ax)
    _h.titular(ax, _h.gap_financiados_por_mes(meses, list(pct_gap_fin)),
               "% con GAP: en créditos financiados y en todas las solicitudes")
    ax.set_ylabel("% de solicitudes")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False, ncol=2, fontsize=8.5)
    plt.tight_layout()
    _guardar_si_procede(fig, guardar_como)
    plt.close(fig)
    return guardar_como


def generar_graficas_comparativas(datos_por_mes, orden_meses, tabla_comp, df_combinado, carpeta):
    # Vendedores y modelos cuentan cada folio una vez (ver folios.py). Las
    # gráficas por mes no usan df_combinado, así que siguen siendo la foto
    # de cada bitácora.
    # Colores con los estatus de TODOS los meses juntos (antes de consolidar,
    # porque las gráficas por mes muestran el estatus que tuvo cada folio en
    # cada bitácora). Así un estatus conserva su color en todo el reporte.
    _presentes = set()
    for _m in orden_meses:
        _df_m = datos_por_mes[_m]["df"]
        if "Categoria" in _df_m.columns:
            _presentes.update(_df_m["Categoria"].dropna().unique())
    if "Categoria" in df_combinado.columns:
        _presentes.update(df_combinado["Categoria"].dropna().unique())
    _est.asignar_colores(_presentes)
    df_combinado, _ = _folios.consolidar(df_combinado, orden_meses)
    print("=" * 72)
    print(" GENERANDO GRÁFICAS PARA EL REPORTE COMPARATIVO")
    print("=" * 72)
    especificaciones = [
        ("totales_mes",        lambda ruta: grafica_comp_totales_por_mes(datos_por_mes, orden_meses, ruta), "c01_totales_mes.png"),
        ("tasa_conversion",    lambda ruta: grafica_comp_tasa_conversion(tabla_comp, ruta),                   "c02_tasa_conversion.png"),
        ("montos_mes",         lambda ruta: grafica_comp_montos_por_mes(tabla_comp, ruta),                    "c03_montos_mes.png"),
        ("gap_vs_gap_fin_mes", lambda ruta: grafica_comp_gap_vs_gap_financiado(tabla_comp, ruta),              "c04b_gap_vs_gap_fin_mes.png"),
        ("vendedores",         lambda ruta: grafica_vendedores(df_combinado, ruta, " en el periodo"),"c06_vendedores.png"),
        ("vendedor_status",    lambda ruta: grafica_vendedor_status(df_combinado, ruta),                      "c07_vendedor_status.png"),
        ("gap_por_vendedor",   lambda ruta: grafica_gap_por_vendedor_total(df_combinado, ruta),               "c09_gap_vendedor.png"),
        ("gap_financiado_vend", lambda ruta: grafica_gap_financiado_por_vendedor(df_combinado, ruta),         "c10_gap_financiado_vendedor.png"),
        ("modelos",            lambda ruta: grafica_modelos(df_combinado, ruta, " en el periodo"),"c11_modelos.png"),
    ]
    rutas = {}
    for clave, funcion, nombre_png in especificaciones:
        ruta = os.path.join(carpeta, nombre_png)
        try:
            resultado = funcion(ruta)
        except Exception as e:
            print(f"  Aviso: no se pudo generar la gráfica '{clave}' ({e}).")
            resultado = None
        if resultado:
            rutas[clave] = resultado
            print(f"  OK  {clave}")
        else:
            print(f"  --  {clave} (sin datos suficientes, se omite)")
    print()

    # Guarda de seguridad: si NINGUNA gráfica se pudo generar, algo está mal
    # de fondo (carpeta borrada, permisos, columnas faltantes). Antes el
    # reporte se armaba igual y salía un PDF entero sin una sola gráfica, sin
    # ningún error visible. Es mejor fallar fuerte y decir por qué.
    if not rutas:
        raise RuntimeError(
            "No se pudo generar ninguna gráfica. Revisa que el archivo traiga "
            "las columnas esperadas (STATUS, Nombre del Vendedor, etc.) y que "
            f"la carpeta '{carpeta}' se pueda escribir."
        )

    return rutas


# =======================================================================
# 7) INSIGHTS AUTOMÁTICOS
# =======================================================================
# La redacción de "Lectura del periodo" y de "Conclusiones" vive ahora en
# herramientas/conclusiones.py, compartida con los otros tres reportes para
# que todos apliquen los mismos umbrales. Ver el docstring de ese módulo para
# los criterios; antes esta función producía una sola lista que se imprimía
# idéntica en las dos secciones.


# =======================================================================
# 8) GENERACIÓN DEL PDF
# =======================================================================
def generar_reporte_pdf_comparativo(datos_por_mes, orden_meses, tabla_comp,
                                     df_combinado, nombre_archivo=None,
                                     recolectar_elementos=None, datos=None,
                                     carpeta_graficas=None):
    """datos: PDV, implant y empresa (config.DatosReporte); por defecto, los de config."""
    datos = datos or DatosReporte()
    if nombre_archivo is None:
        fecha_archivo = _fechas.ahora().strftime("%Y%m%d_%H%M")
        rango = f"{orden_meses[0].title()}" if len(orden_meses) == 1 else \
                f"{orden_meses[0].title()}_a_{orden_meses[-1].title()}"
        nombre_archivo = f"Reporte_Comparativo_{rango}_{fecha_archivo}.pdf"

    print("=" * 72)
    print(" GENERANDO REPORTE PDF COMPARATIVO")
    print("=" * 72)

    # Las gráficas van en una carpeta junto al PDF (en la app, dentro del
    # temporal de la corrida, que se borra al terminar). Antes era una
    # carpeta fija en la raíz, compartida por todas las corridas.
    carpeta_graficas = carpeta_graficas or os.path.join(
        os.path.dirname(os.path.abspath(nombre_archivo)), "graficas")
    rutas_graficas = generar_graficas_comparativas(datos_por_mes, orden_meses, tabla_comp,
                                                   df_combinado, carpeta_graficas)
    lectura, conclusiones_fin = _conclusiones.lectura_y_conclusiones_comparativo(
        tabla_comp, orden_meses, df_combinado)

    # --- Estilos (idénticos al avance preliminar) ---
    _estilos = crear_estilos()
    styles = _estilos["styles"]
    estilo_kicker_portada = _estilos["kicker_portada"]
    estilo_titulo_portada = _estilos["titulo_portada"]
    estilo_subtitulo_portada = _estilos["subtitulo_portada"]
    estilo_meta_portada = _estilos["meta_portada"]
    estilo_h1 = _estilos["h1"]
    estilo_h2 = _estilos["h2"]
    estilo_cuerpo = _estilos["cuerpo"]
    estilo_nota = _estilos["nota"]
    estilo_encabezado_tabla = _estilos["encabezado_tabla"]
    # Tercer nivel: la sección de vendedores llegó a tener varias
    # subsecciones y con solo dos niveles se leían todas como iguales.
    estilo_h3 = ParagraphStyle(
        "H3MG", parent=styles["Heading3"], fontName=FUENTE_BOLD, fontSize=10.5,
        textColor=rl_colors.HexColor(INBURSA_AZUL), spaceBefore=8, spaceAfter=4)
    # Celda de tabla con texto que puede partirse en dos renglones. Las
    # celdas de texto plano nunca se parten: si no caben, se encimen con la
    # columna vecina (pasaba en "Folios que cruzaron de mes" al comparar
    # 4 o más meses: "Septiembre 2026: Financiado" no cabe en una línea).
    estilo_celda_tabla = ParagraphStyle(
        "CeldaTabla", parent=styles["Normal"], fontName=FUENTE_REGULAR, fontSize=8.8,
        leading=11, textColor=rl_colors.HexColor(MG_GRIS_OSCURO), alignment=TA_CENTER)

    FECHA_REPORTE = _fechas.hoy().strftime("%d/%m/%Y")
    PERIODO_TXT = orden_meses[0].title() if len(orden_meses) == 1 else \
        f"{orden_meses[0].title()} – {orden_meses[-1].title()}"

    def encabezado_pie_pagina(canvas_obj, doc):
        """Encabezado y pie: el dibujo vive en pdf_util.pintar_encabezado_pie,
        compartido por los cuatro reportes."""
        _pdf_util.pintar_encabezado_pie(
            canvas_obj, doc, datos.empresa, f"Reporte Comparativo Mensual · {datos.pdv}", FECHA_REPORTE, datos.analista,
            fuente_regular=FUENTE_REGULAR, fuente_bold=FUENTE_BOLD)

    def tabla_estilo_mg(data, col_widths=None, alinear_derecha_desde=1,
                        fila_total=False, compacta=False):
        """fila_total=True destaca el último renglón como resumen de la tabla.

        Mismo criterio que la versión de reporte_base.py: filete rojo arriba,
        fondo propio y negritas, para que el renglón más consultado no se
        pierda en el zebrado.
        """
        # compacta: letra y márgenes menores para tablas de muchas columnas.
        # Las del resumen ejecutivo caen en la columna angosta de la portada
        # (junto a las cifras clave) y ahí "Financiado" se partía a la mitad.
        estilo_enc = (estilo_encabezado_tabla.clone("EncabezadoTablaCompacta", fontSize=6.8, leading=8)
                      if compacta else estilo_encabezado_tabla)
        encabezado = [Paragraph(str(c), estilo_enc) for c in data[0]]
        data = [encabezado] + data[1:]
        data = _pdf_util.envolver_celdas_largas(
            data, col_widths, alinear_desde=alinear_derecha_desde, compacta=compacta,
            fila_total=fila_total, fuente_regular=FUENTE_REGULAR,
            fuente_bold=FUENTE_BOLD, color_texto=MG_GRIS_OSCURO)
        tabla = Table(data, colWidths=col_widths, repeatRows=1)
        n_filas = len(data)
        # Formato compartido (pdf_util.estilo_tabla): encabezado claro con
        # texto azul, sin zebrado ni recuadro, fila de totales en azul.
        estilo = _pdf_util.estilo_tabla(
            n_filas, alinear_desde=alinear_derecha_desde, compacta=compacta,
            fila_total=fila_total, fuente_regular=FUENTE_REGULAR,
            fuente_bold=FUENTE_BOLD, color_texto=MG_GRIS_OSCURO)
        tabla.setStyle(TableStyle(estilo))
        return tabla

    # --- Folios que cruzan de mes ---
    # De aquí en adelante df_combinado tiene una fila por folio (su último
    # estatus, en su mes de captura). Todo lo "del periodo" y "por vendedor"
    # sale de ahí; lo "por mes" sigue saliendo de tabla_comp. Ver folios.py.
    df_combinado, _res_folios = _folios.consolidar(df_combinado, orden_meses)

    # --- Datos clave para portada/KPIs ---
    # Por folio único. Antes el total sumaba las filas de cada mes (81 en
    # junio–agosto, contando dos veces 3 solicitudes) y la conversión era el
    # promedio simple de las tasas mensuales, sin ponderar por volumen.
    total_periodo = len(df_combinado)
    n_meses = len(orden_meses)
    # Sin contar "Sin vendedor asignado", que no es una persona.
    n_vendedores = (int(df_combinado.loc[df_combinado["Nombre del Vendedor"] != SIN_VENDEDOR,
                                         "Nombre del Vendedor"].nunique())
                    if "Nombre del Vendedor" in df_combinado.columns else 0)

    elementos = []

    # --- Portada ---
    elementos.append(Spacer(1, 0.2 * cm))
    elementos.append(Paragraph("REPORTE&nbsp;&nbsp;·&nbsp;&nbsp;COMPARATIVO MENSUAL DE BITÁCORA",
                                estilo_kicker_portada))
    elementos.append(Paragraph("Reporte Comparativo Mensual", estilo_titulo_portada))
    elementos.append(Paragraph(f"{datos.empresa} · {datos.pdv}", estilo_subtitulo_portada))
    elementos.append(Spacer(1, 0.12 * cm))
    elementos.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor(GRIS_LINEA),
                                 spaceBefore=6, spaceAfter=10, hAlign="LEFT"))
    elementos.append(Paragraph(
        f"Periodo comparado: <b>{PERIODO_TXT}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"{n_meses} mes{'es' if n_meses != 1 else ''} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Generado: {FECHA_REPORTE}",
        estilo_meta_portada
    ))
    elementos.append(Spacer(1, 0.5 * cm))

    intro_portada = Table(
        [[Paragraph(
            f"Este reporte compara <b>{n_meses} mes{'es' if n_meses != 1 else ''}</b> de la bitácora "
            f"de solicitudes de crédito automotriz ({PERIODO_TXT}), con un total de "
            f"<b>{total_periodo} solicitudes</b> en el periodo. Incluye la evolución del volumen y "
            f"las categorías de cierre, la tasa "
            f"de conversión mes a mes, el panorama financiero, la colocación del seguro GAP y el "
            f"desempeño acumulado por vendedor a lo largo del periodo.",
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
    elementos.append(_lateral.bloque_cifras(_lateral.cifras_comparativo(df_combinado, tabla_comp, n_meses)))
    elementos.append(Spacer(1, 0.5 * cm))

    # --- Resumen ejecutivo: tabla comparativa mensual ---
    elementos.append(Paragraph("Resumen Ejecutivo — Comparativo por Mes", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    if not tabla_comp.empty:
        # El nombre de la columna de solicitudes abiertas se toma de la propia
        # tabla, no se escribe a mano: construir_tabla_comparativa() decide si
        # va el nombre de la categoría (Contrapropuesta) o el genérico
        # (En trámite) según cuántas categorías abiertas trae el periodo.
        col_abiertas = etiqueta_columna_abiertas(datos_por_mes)
        # Los encabezados largos se parten en dos renglones para no ensanchar
        # la columna; "Contrapropuesta" es de una sola palabra, así que se
        # corta con guion en vez de dejarla desbordarse.
        enc_abiertas = (col_abiertas.replace(" ", "<br/>") if " " in col_abiertas
                        else ("Contra-<br/>propuesta" if col_abiertas == "Contrapropuesta"
                              else col_abiertas))
        encabezados_vol = ["Mes", "Total", "Financiado", "Aprobado", enc_abiertas, "Rechazado", "%<br/>Financiado"]
        filas_vol = []
        for mes, fila in tabla_comp.iterrows():
            filas_vol.append([
                mes, int(fila["Total"]), int(fila["Financiado"]), int(fila["Aprobado"]),
                int(fila[col_abiertas]), int(fila["Rechazado"]), f"{fila['% Financiado']:.1f}%",
            ])
        anchos_vol = _pdf_util.repartir(2.6 * cm, 6)
        elementos.append(tabla_estilo_mg([encabezados_vol] + filas_vol, col_widths=anchos_vol, compacta=True))
        elementos.append(Spacer(1, 0.35 * cm))

        encabezados_fin = ["Mes", "Monto Total", "Monto<br/>Financiado", "Ticket Prom.<br/>Financiado", "% GAP", "% GAP<br/>Financiado"]
        filas_fin = []
        for mes, fila in tabla_comp.iterrows():
            filas_fin.append([
                mes,
                f"${fila['Monto Total']:,.0f}" if pd.notna(fila.get('Monto Total')) else "—",
                f"${fila['Monto Financiado']:,.0f}" if pd.notna(fila.get('Monto Financiado')) else "—",
                f"${fila['Ticket Prom. Financiado']:,.0f}" if pd.notna(fila.get('Ticket Prom. Financiado')) else "—",
                f"{fila['% GAP']:.1f}%" if pd.notna(fila.get('% GAP')) else "—",
                f"{fila['% GAP Financiado']:.1f}%" if pd.notna(fila.get('% GAP Financiado')) else "—",
            ])
        anchos_fin = _pdf_util.repartir(2.4 * cm, 5)
        elementos.append(tabla_estilo_mg([encabezados_fin] + filas_fin, col_widths=anchos_fin, compacta=True))
    else:
        elementos.append(Paragraph("No se pudo construir la tabla comparativa mensual.", estilo_nota))
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph("Lectura del periodo", estilo_h2))
    for texto in lectura + _folios.texto_aviso(_res_folios):
        elementos.append(Paragraph(_pdf_util.resaltar("•  " + texto), estilo_cuerpo))
    # Salto condicional: si la lectura cabe en la portada, el reporte
    # detallado empieza en página nueva como siempre; si se desborda (por
    # ejemplo, con el aviso de folios entre meses), sigue en la misma página
    # en vez de dejar una hoja con tres renglones y el resto en blanco.
    elementos.append(CondPageBreak(14 * cm))

    # ===============================================================
    # REPORTE DETALLADO
    # ===============================================================
    elementos.append(Paragraph("Reporte Detallado", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))

    if "totales_mes" in rutas_graficas:
        elementos.append(Paragraph("1. Volumen y Categorías de Cierre por Mes", estilo_h2))
        elementos.append(Paragraph(
            "La siguiente gráfica apila, para cada mes comparado, cuántas solicitudes cerraron en "
            "cada estatus, para comparar de un "
            "vistazo tanto el volumen total como la calidad del cierre mes a mes.",
            estilo_cuerpo
        ))
        elementos.append(imagen_ajustada(rutas_graficas["totales_mes"], ancho_cm=16, alto_max_cm=11))
        elementos.append(Spacer(1, 0.4 * cm))

    if "tasa_conversion" in rutas_graficas:
        elementos.append(Paragraph("2. Tasa de Conversión por Mes", estilo_h2))
        elementos.append(Paragraph(
            "Evolución del % de solicitudes que terminaron FINANCIADAS y del % que quedó APROBADO "
            "(pendiente de dispersar) en cada mes. Una caída en el % Financiado sin caída en el % "
            "Aprobado suele indicar un problema de seguimiento a cierre más que de calidad de la "
            "solicitud entrante.",
            estilo_cuerpo
        ))
        elementos.append(imagen_ajustada(rutas_graficas["tasa_conversion"], ancho_cm=16, alto_max_cm=11))
        elementos.append(Spacer(1, 0.4 * cm))

    if "montos_mes" in rutas_graficas:
        elementos.append(Paragraph("3. Panorama Financiero por Mes", estilo_h2))
        elementos.append(Paragraph(
            "Comparación, mes a mes, del monto total a financiar de todas las solicitudes contra el "
            "monto que efectivamente se convirtió en crédito FINANCIADO (dispersado).",
            estilo_cuerpo
        ))
        elementos.append(imagen_ajustada(rutas_graficas["montos_mes"], ancho_cm=16, alto_max_cm=11))
        elementos.append(Spacer(1, 0.4 * cm))

    if "gap_mes" in rutas_graficas or "gap_vs_gap_fin_mes" in rutas_graficas or \
       "gap_categoria_mes" in rutas_graficas or \
       "gap_por_categoria" in rutas_graficas or "gap_por_vendedor" in rutas_graficas or \
       "gap_financiado_vend" in rutas_graficas:
        elementos.append(Paragraph("4. Seguro GAP", estilo_h2))
        elementos.append(Paragraph(
            "El seguro GAP cubre la diferencia entre el valor asegurado del vehículo y el saldo "
            "insoluto del crédito en caso de pérdida total, por lo que su colocación es un indicador "
            "de venta cruzada relevante. Esta sección compara su colocación entre meses y, para el "
            "periodo completo, por categoría de cierre y por vendedor.",
            estilo_cuerpo
        ))
        if "gap_mes" in rutas_graficas:
            elementos.append(imagen_ajustada(rutas_graficas["gap_mes"], ancho_cm=15, alto_max_cm=10))
            elementos.append(Spacer(1, 0.2 * cm))
        if "gap_vs_gap_fin_mes" in rutas_graficas:
            elementos.append(Paragraph(
                "La siguiente gráfica compara, mes a mes, el % de GAP sobre TODAS las solicitudes "
                "contra el % de GAP dentro de los créditos que sí llegaron a FINANCIARSE. Si la línea "
                "de GAP Financiado va por debajo de la línea general, se está colocando GAP en "
                "solicitudes que después no se dispersan; si van parejas, el GAP se está vendiendo "
                "bien justo donde más cuenta.",
                estilo_cuerpo
            ))
            elementos.append(imagen_ajustada(rutas_graficas["gap_vs_gap_fin_mes"], ancho_cm=15, alto_max_cm=10))
            elementos.append(Spacer(1, 0.2 * cm))
        if "gap_categoria_mes" in rutas_graficas:
            elementos.append(imagen_ajustada(rutas_graficas["gap_categoria_mes"], ancho_cm=16, alto_max_cm=11))
            elementos.append(Spacer(1, 0.2 * cm))
        if "gap_por_categoria" in rutas_graficas:
            elementos.append(Paragraph(
                "Colocación de GAP por categoría de cierre, sumando todos los meses comparados:",
                estilo_cuerpo
            ))
            elementos.append(imagen_ajustada(rutas_graficas["gap_por_categoria"], ancho_cm=13, alto_max_cm=10))
            elementos.append(Spacer(1, 0.2 * cm))
        if "gap_por_vendedor" in rutas_graficas:
            elementos.append(Paragraph(
                "Solicitudes con GAP por vendedor, comparadas contra el total de solicitudes de cada "
                "quien en todo el periodo:",
                estilo_cuerpo
            ))
            elementos.append(imagen_ajustada(rutas_graficas["gap_por_vendedor"], ancho_cm=16, alto_max_cm=13))
            elementos.append(Spacer(1, 0.2 * cm))
        if "gap_financiado_vend" in rutas_graficas:
            elementos.append(Paragraph(
                "Por último, la colocación de GAP dentro de los créditos ya <b>FINANCIADOS</b> "
                "en todo el periodo: es el indicador más relevante, porque ese GAP ya está vendido.",
                estilo_cuerpo
            ))
            elementos.append(imagen_ajustada(rutas_graficas["gap_financiado_vend"], ancho_cm=16, alto_max_cm=13))
        elementos.append(Spacer(1, 0.4 * cm))

    if "vendedores" in rutas_graficas or "vendedor_status" in rutas_graficas:
        elementos.append(Paragraph("5. Desempeño por Vendedor (Periodo Completo)", estilo_h2))
        elementos.append(Paragraph(
            f"Participan {n_vendedores} vendedores a lo largo de "
            f"{PERIODO_TXT}. Las siguientes gráficas muestran el total de solicitudes por vendedor y "
            f"su desglose por categoría de cierre, acumulando todos los meses comparados.",
            estilo_cuerpo
        ))
        if "vendedores" in rutas_graficas:
            elementos.append(imagen_ajustada(rutas_graficas["vendedores"], ancho_cm=16, alto_max_cm=13))
            elementos.append(Spacer(1, 0.2 * cm))
        if "vendedor_status" in rutas_graficas:
            elementos.append(imagen_ajustada(rutas_graficas["vendedor_status"], ancho_cm=16, alto_max_cm=13))

        # --- Resumen por vendedor: solicitudes + créditos + GAP en una tabla ---
        # Antes eran dos tablas con una fila por vendedor cada una
        # (solicitudes por mes y ticket/GAP). Fusionadas, todo lo de cada
        # persona se lee en un renglón. La columna "Variación" no se repite
        # aquí: la tabla "Quién subió y quién bajó" ya la muestra, con su %.
        # Con 5 meses o más no caben las columnas de meses: se regresa a las
        # dos tablas separadas.
        tabla_prom = tabla_promedio_vendedor(df_combinado, orden_meses)
        tabla_ticket = tabla_ticket_promedio_vendedor(df_combinado)
        fusionada = False
        if (tabla_prom is not None and not tabla_prom.empty and tabla_ticket is not None
                and not tabla_ticket.empty and len(orden_meses) <= 4):
            fusionada = True
            meses_cols = [c for c in tabla_prom.columns if c not in ("Total", "Promedio", "Variación")]
            hay_gap = "GAP" in tabla_ticket.columns
            hay_monto_gap = "Monto GAP" in tabla_ticket.columns
            n_m = len(meses_cols)

            enc = estilo_encabezado_tabla.clone("EncFusion", fontSize=6.9, leading=8.2)
            grp = estilo_encabezado_tabla.clone("GrupoFusion", fontSize=7.4, leading=9)
            P = lambda t, e=enc: Paragraph(t, e)
            grupo = ([P("Vendedor")] + [P("Solicitudes", grp)] + [""] * (n_m + 1)
                     + [P("Créditos financiados", grp), "", ""])
            sub = ([""] + [P(str(m).title()[:3]) for m in meses_cols] + [P("Total"), P("Prom.")]
                   + [P("Créditos"), P("Monto"), P("Ticket")])
            if hay_gap:
                grupo += [P("GAP en financiados", grp), ""] + ([""] if hay_monto_gap else [])
                sub += [P("Con GAP"), P("%")] + ([P("Monto")] if hay_monto_gap else [])
            filas_f = [grupo, sub]

            def _din(v):
                return f"${v:,.0f}"
            for vendedor, fila in tabla_prom.iterrows():
                t = tabla_ticket.loc[vendedor] if vendedor in tabla_ticket.index else None
                celdas = [_recortar_nombre(str(vendedor), maximo=20)]
                celdas += [str(int(fila[m])) for m in meses_cols]
                celdas += [str(int(fila["Total"])), f"{fila['Promedio']:.1f}"]
                if t is not None:
                    celdas += [str(int(t["Financiados"])), _din(t["Monto"]), _din(t["Ticket"])]
                    if hay_gap:
                        celdas += [str(int(t["GAP"])), f"{t['% GAP']:.0f}%"]
                        celdas += [_din(t["Monto GAP"])] if hay_monto_gap else []
                else:
                    # Sin créditos financiados: el ticket y el % de GAP no existen.
                    celdas += ["0", "—", "—"] + (["—", "—"] + (["—"] if hay_monto_gap else []) if hay_gap else [])
                filas_f.append(celdas)

            n_tot = int(tabla_ticket["Financiados"].sum())
            m_tot = float(tabla_ticket["Monto"].sum())
            tot = (["TOTAL EQUIPO"] + [str(int(tabla_prom[m].sum())) for m in meses_cols]
                   + [str(int(tabla_prom["Total"].sum())), f"{tabla_prom['Promedio'].sum():.1f}",
                      str(n_tot), _din(m_tot), _din(m_tot / n_tot) if n_tot else "—"])
            if hay_gap:
                g_tot = int(tabla_ticket["GAP"].sum())
                tot += [str(g_tot), f"{g_tot / n_tot * 100:.0f}%" if n_tot else "—"]
                tot += [_din(float(tabla_ticket["Monto GAP"].sum()))] if hay_monto_gap else []
            filas_f.append(tot)

            # Anchos: los bloques de créditos y GAP son fijos; los meses se
            # reparten lo que sobra del ancho útil.
            fijos = [3.3 * cm, 1.05 * cm, 1.05 * cm, 1.2 * cm, 1.85 * cm, 1.7 * cm]
            if hay_gap:
                fijos += [1.05 * cm, 0.95 * cm] + ([1.55 * cm] if hay_monto_gap else [])
            ancho_mes = (_pdf_util.ANCHO_UTIL - sum(fijos)) / n_m
            anchos_f = [fijos[0]] + [ancho_mes] * n_m + fijos[1:]

            c_cred = 1 + n_m + 2           # primera columna de "Créditos financiados"
            c_gap = c_cred + 3              # primera columna de "GAP en financiados"
            azul, linea, fondo = (rl_colors.HexColor(_pdf_util.AZUL), rl_colors.HexColor(_pdf_util.LINEA),
                                  rl_colors.HexColor(_pdf_util.FONDO_SUAVE))
            ult = len(filas_f) - 1
            estilo_f = [
                ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (c_cred - 1, 0)), ("SPAN", (c_cred, 0), (c_gap - 1, 0)),
                ("BACKGROUND", (0, 0), (-1, 1), fondo),
                ("LINEBELOW", (1, 0), (-1, 0), 0.4, linea),
                ("LINEBELOW", (0, 1), (-1, 1), 0.9, azul),
                ("LINEBEFORE", (c_cred, 0), (c_cred, -1), 0.5, linea),
                ("FONTNAME", (0, 2), (-1, -1), FUENTE_REGULAR), ("FONTSIZE", (0, 2), (-1, -1), 7.2),
                ("TEXTCOLOR", (0, 2), (-1, -1), rl_colors.HexColor(MG_GRIS_OSCURO)),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 2), (-1, ult - 1), 0.4, linea),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("LINEABOVE", (0, ult), (-1, ult), 1.0, azul), ("BACKGROUND", (0, ult), (-1, ult), fondo),
                ("FONTNAME", (0, ult), (-1, ult), FUENTE_BOLD), ("FONTSIZE", (0, ult), (-1, ult), 7.4),
                ("TEXTCOLOR", (0, ult), (-1, ult), azul),
            ]
            if hay_gap:
                estilo_f += [("SPAN", (c_gap, 0), (-1, 0)), ("LINEBEFORE", (c_gap, 0), (c_gap, -1), 0.5, linea)]
            tabla_f = Table(filas_f, colWidths=anchos_f, repeatRows=2)
            tabla_f.setStyle(TableStyle(estilo_f))

            elementos.append(Spacer(1, 0.35 * cm))
            elementos.append(Paragraph("Resumen por vendedor", estilo_h3))
            elementos.append(Paragraph(
                f"Solicitudes por mes de captura, créditos financiados y GAP colocado en ellos. "
                f"El promedio considera los {len(orden_meses)} meses, aunque alguno haya quedado "
                f"en cero; el GAP es el colocado en créditos ya financiados, es decir el "
                f"efectivamente vendido.",
                estilo_cuerpo
            ))
            elementos.append(KeepTogether(tabla_f))

        # Tabla de promedio mensual por vendedor (solo si no se fusionó)
        if not fusionada and tabla_prom is not None and not tabla_prom.empty:
            elementos.append(Spacer(1, 0.3 * cm))
            elementos.append(Paragraph(
                f"El promedio se calcula sobre los {len(orden_meses)} meses "
                f"comparados, no solo sobre los meses con actividad: un mes sin "
                f"solicitudes cuenta como cero.",
                estilo_cuerpo
            ))

            encabezados = ["Vendedor"] + [str(c).title() for c in tabla_prom.columns]
            filas = [encabezados]
            for vendedor, fila in tabla_prom.iterrows():
                celdas = [_recortar_nombre(str(vendedor))]
                for col in tabla_prom.columns:
                    valor = fila[col]
                    if col == "Promedio":
                        celdas.append(f"{valor:.1f}")
                    elif col == "Variación":
                        # El signo es la información: +3 y -3 se leen distinto.
                        celdas.append(f"{int(valor):+d}" if valor else "0")
                    else:
                        celdas.append(str(int(valor)))
                filas.append(celdas)

            # Fila de totales del equipo
            totales = ["TOTAL EQUIPO"]
            for col in tabla_prom.columns:
                if col == "Promedio":
                    totales.append(f"{tabla_prom[col].sum():.1f}")
                elif col == "Variación":
                    suma = int(tabla_prom[col].sum())
                    totales.append(f"{suma:+d}" if suma else "0")
                else:
                    totales.append(str(int(tabla_prom[col].sum())))
            filas.append(totales)

            elementos.append(KeepTogether(tabla_estilo_mg(filas, fila_total=True)))

        # --- Quién subió y quién bajó -------------------------------
        resultado_var = tabla_variacion_vendedor(df_combinado, orden_meses)
        if resultado_var is not None:
            tabla_var, mes_ini, mes_fin = resultado_var
            elementos.append(Spacer(1, 0.35 * cm))
            elementos.append(Paragraph("Quién subió y quién bajó", estilo_h3))
            elementos.append(Paragraph(
                f"Comparación directa entre {str(mes_ini).title()} y "
                f"{str(mes_fin).title()}, ordenada de mayor aumento a mayor "
                f"caída. Los meses intermedios no entran en esta lectura.",
                estilo_cuerpo
            ))
            filas_var = [["Vendedor", str(mes_ini).title(), str(mes_fin).title(),
                          "Variación", "% Cambio"]]
            for vendedor, fila in tabla_var.iterrows():
                var = int(fila["Variación"])
                pct = fila["% Cambio"]
                filas_var.append([
                    _recortar_nombre(str(vendedor)),
                    str(int(fila["Inicio"])),
                    str(int(fila["Fin"])),
                    f"{var:+d}" if var else "0",
                    "—" if pd.isna(pct) else f"{pct:+.0f}%",
                ])
            elementos.append(KeepTogether(tabla_estilo_mg(filas_var)))

        # --- Ticket promedio ----------------------------------------
        if not fusionada and tabla_ticket is not None and not tabla_ticket.empty:
            elementos.append(Spacer(1, 0.35 * cm))
            elementos.append(Paragraph("Ticket promedio y GAP por vendedor", estilo_h3))
            elementos.append(Paragraph(
                "El GAP que aquí se cuenta es el colocado dentro de créditos "
                "ya financiados, es decir el efectivamente vendido.",
                estilo_cuerpo
            ))
            hay_gap = "GAP" in tabla_ticket.columns
            hay_monto_gap = "Monto GAP" in tabla_ticket.columns

            cab = ["Vendedor", "Créditos", "Monto<br/>financiado", "Ticket<br/>promedio"]
            if hay_gap:
                cab += ["Con<br/>GAP", "% GAP"]
                if hay_monto_gap:
                    cab.append("Monto<br/>GAP")
            filas_t = [cab]

            for vendedor, fila in tabla_ticket.iterrows():
                celdas = [
                    _recortar_nombre(str(vendedor), maximo=22),
                    str(int(fila["Financiados"])),
                    f"${fila['Monto']:,.0f}",
                    f"${fila['Ticket']:,.0f}",
                ]
                if hay_gap:
                    celdas += [str(int(fila["GAP"])), f"{fila['% GAP']:.0f}%"]
                    if hay_monto_gap:
                        celdas.append(f"${fila['Monto GAP']:,.0f}")
                filas_t.append(celdas)

            n_tot = int(tabla_ticket["Financiados"].sum())
            m_tot = float(tabla_ticket["Monto"].sum())
            totales = ["TOTAL EQUIPO", str(n_tot), f"${m_tot:,.0f}",
                       f"${m_tot / n_tot:,.0f}" if n_tot else "—"]
            if hay_gap:
                g_tot = int(tabla_ticket["GAP"].sum())
                totales += [str(g_tot),
                            f"{g_tot / n_tot * 100:.0f}%" if n_tot else "—"]
                if hay_monto_gap:
                    totales.append(f"${float(tabla_ticket['Monto GAP'].sum()):,.0f}")
            filas_t.append(totales)
            elementos.append(KeepTogether(tabla_estilo_mg(filas_t, fila_total=True)))

        # --- Folios que cruzaron de mes -------------------------------
        cruces = _res_folios["cruces"]
        if not cruces.empty:
            elementos.append(Spacer(1, 0.35 * cm))
            elementos.append(Paragraph("Folios que cruzaron de mes", estilo_h3))
            elementos.append(Paragraph(
                "Solicitudes que aparecen en la bitácora de más de un mes. En las "
                "tablas de esta sección cuentan una sola vez, en el mes de captura "
                "y con su último estatus.",
                estilo_cuerpo
            ))
            nombres_campo = {"Nombre del Vendedor": "vendedor", "Vehículo": "vehículo",
                             "Monto Total a Financiar": "monto", "¿Tiene GAP?": "GAP"}
            filas_c = [["Folio", "Vendedor", "Captura", "Último<br/>estatus",
                        "Cambió"]]

            def _celda(txt):
                return Paragraph(_xml_escape(str(txt)), estilo_celda_tabla)

            def _mes_estatus(mes, estatus):
                # Dos renglones fijos (mes arriba, estatus abajo): así todas
                # las filas se ven igual sin importar cuántos meses se
                # comparen ni qué tan largo sea el nombre del mes.
                return Paragraph(
                    f"{_xml_escape(str(mes).title())}<br/>{_xml_escape(str(estatus).title())}",
                    estilo_celda_tabla)

            for _, fila in cruces.iterrows():
                cambios = ", ".join(nombres_campo.get(c, c) for c in fila["Cambios"]) or "—"
                filas_c.append([
                    str(fila["Folio"]),
                    _celda(_recortar_nombre(str(fila["Vendedor"]), maximo=30)),
                    _mes_estatus(fila["Mes de captura"], fila["Estatus al capturar"]),
                    _mes_estatus(fila["Mes del último estatus"], fila["Último estatus"]),
                    _celda(cambios),
                ])
            elementos.append(KeepTogether(tabla_estilo_mg(
                filas_c, col_widths=[2.0 * cm, 4.3 * cm, 3.5 * cm, 3.5 * cm, 3.3 * cm])))

        elementos.append(Spacer(1, 0.4 * cm))

    if "modelos" in rutas_graficas:
        elementos.append(Paragraph("6. Modelos de Vehículo Más Solicitados (Periodo)", estilo_h2))
        elementos.append(Paragraph(
            "Modelos con mayor número de solicitudes sumando todos los meses comparados.",
            estilo_cuerpo
        ))
        elementos.append(imagen_ajustada(rutas_graficas["modelos"], ancho_cm=16, alto_max_cm=13))
        elementos.append(Spacer(1, 0.4 * cm))

    # ===============================================================
    # CONCLUSIONES
    # ===============================================================
    elementos.append(Paragraph("Conclusiones y Factores Importantes", estilo_h1))
    elementos.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor(GRIS_LINEA), spaceAfter=8))
    for texto in conclusiones_fin:
        elementos.append(Paragraph(_pdf_util.resaltar("•  " + texto), estilo_cuerpo))

    # -------------------------------------------------------------
    doc = SimpleDocTemplate(
        nombre_archivo, pagesize=letter,
        topMargin=_pdf_util.MARGEN_SUPERIOR, bottomMargin=_pdf_util.MARGEN_INFERIOR, leftMargin=_pdf_util.MARGEN, rightMargin=_pdf_util.MARGEN,
        # Lo que muestra el lector de PDF en la pestaña y en "Propiedades".
        title=f"Reporte Comparativo Mensual — {datos.pdv} — {PERIODO_TXT}",
        author=datos.analista,
        subject=f"{datos.empresa} · Bitácora de solicitudes",
    )
    # `recolectar_elementos`: si el llamador pasa una lista, aquí se le
    # deja una copia de todos los flowables del PDF. Es lo que usa
    # docx_reportes.py para generar el Word a partir de ESTE mismo
    # contenido, en vez de volver a redactarlo por su cuenta.
    # Se copia ANTES de doc.build() porque ReportLab va vaciando la lista
    # que recibe conforme la maqueta.
    # Sin esto, un Spacer que no cabe al final de una página genera una
    # hoja en blanco antes del siguiente salto. Ver pdf_util.py.
    elementos[:] = _pdf_util.pulir(_pdf_util.quitar_espacios_antes_de_salto(elementos))
    if recolectar_elementos is not None:
        from . import flowables_a_docx as _fd
        recolectar_elementos.extend(_fd.capturar_guion(elementos))

    _pdf_util.construir_con_lateral(doc, elementos, encabezado_pie_pagina)

    print(f"\nReporte PDF generado: {nombre_archivo}")
    print(f"Archivo guardado en: {nombre_archivo}")
    return nombre_archivo
