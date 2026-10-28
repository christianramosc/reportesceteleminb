# -*- coding: utf-8 -*-
"""
App de reportes — Bitácora de Solicitudes MG Colima (Autoexpress Inbursa)

Une, detrás de una interfaz simple de "sube el archivo y descarga el
resultado", los scripts de Colab que ya se usan para la bitácora mensual.
No hay que tocar este archivo para agregar una herramienta nueva más
adelante — ver las instrucciones en herramientas/__init__.py.
"""

import contextlib
import glob
import io
import os
import shutil
import tempfile
import traceback

import pandas as pd
import streamlit as st

import ui_estilos as ui
from herramientas import REGISTRO
from herramientas import estatus as _est
from herramientas import fechas as _fechas
from herramientas.avance_preliminar_original import (
    NOMBRE_ANALISTA as _ANALISTA_DEFECTO,
    SUBTITULO_EMPRESA as _PDV_DEFECTO,
)

# =======================================================================
# MANEJO DE ARCHIVOS — datos personales
# =======================================================================
# La bitácora trae datos personales de clientes (nombre completo, fecha de
# nacimiento, teléfono, correo). Antes el Excel se guardaba tal cual en una
# carpeta "entradas/" que persiste entre sesiones; en Streamlit Cloud ese
# disco es compartido y sobrevive días.
#
# Ahora cada corrida usa un directorio temporal propio que se borra SIEMPRE
# al terminar (incluso si el reporte truena), y los archivos generados se
# devuelven en memoria para que el botón de descarga no dependa del disco.
_CARPETAS_HEREDADAS = ("entradas", "salida")


def _borrar_carpetas_heredadas():
    """Limpia las carpetas de la versión anterior, que pueden traer Excel
    con datos de clientes de corridas pasadas."""
    for nombre in _CARPETAS_HEREDADAS:
        ruta = os.path.abspath(nombre)
        if os.path.isdir(ruta):
            shutil.rmtree(ruta, ignore_errors=True)


_borrar_carpetas_heredadas()

st.set_page_config(
    page_title="Reportes · MG Colima",
    page_icon=":material/bar_chart:",
    layout="centered",
    initial_sidebar_state="auto",   # abierto en computadora, cerrado en celular
)

ui.aplicar_estilos()

# Menú lateral: icono (Material Symbols de Streamlit) y nombre corto por
# herramienta. El nombre completo se sigue usando como título de la página.
_MENU = {
    "relacion_zip": (":material/folder_zip:", "Relación de clientes"),
    "avance_preliminar": (":material/trending_up:", "Avance preliminar"),
    "comparativo_mensual": (":material/compare_arrows:", "Comparativo mensual"),
    "resumen_mensual": (":material/calendar_month:", "Resumen mensual"),
    "resumen_vendedor": (":material/groups:", "Resumen por vendedor"),
    "modelo_datos": (":material/dataset:", "Modelo de datos"),
}


def _etiqueta_menu(h):
    icono, corto = _MENU.get(h.id, (":material/description:", ui.nombre_limpio(h.nombre)))
    return f"{icono} {corto}"


def _procesar(herramienta, archivos_subidos, opciones):
    """Ejecuta la herramienta en un directorio temporal y devuelve los
    resultados EN MEMORIA como [(nombre, bytes), ...].

    El directorio se borra en el `finally`, así que el Excel del cliente no
    sobrevive a la corrida ni siquiera cuando algo falla a medio camino.
    """
    carpeta = tempfile.mkdtemp(prefix=f"mg_{herramienta.id}_")
    registro = io.StringIO()
    try:
        rutas = []
        for i, archivo in enumerate(archivos_subidos):
            ruta = os.path.join(carpeta, f"{i}_{archivo.name}")
            with open(ruta, "wb") as f:
                f.write(archivo.getbuffer())
            rutas.append(ruta)

        carpeta_salida = os.path.join(carpeta, "salida")
        os.makedirs(carpeta_salida, exist_ok=True)

        with contextlib.redirect_stdout(registro):
            resultados = herramienta.ejecutar(
                rutas, carpeta_salida=carpeta_salida, **opciones
            )

        archivos = []
        for ruta in resultados or []:
            if os.path.exists(ruta):
                with open(ruta, "rb") as f:
                    archivos.append((os.path.basename(ruta), f.read()))
        return archivos, registro.getvalue()
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
        # Las gráficas intermedias se escriben junto al script y llevan
        # nombres de vendedores; tampoco tienen por qué quedarse.
        for temporal in glob.glob("graficas_temp_*"):
            shutil.rmtree(temporal, ignore_errors=True)


def _vista_previa(archivos_subidos):
    """Muestra qué trae el Excel ANTES de generar: cuántas filas y qué
    estatus se detectaron. Sirve para cachar una exportación incompleta o
    un estatus mal escrito sin esperar los dos minutos del reporte."""
    filas_totales = 0
    conteo = {}
    for archivo in archivos_subidos:
        try:
            archivo.seek(0)
            df = pd.read_excel(archivo)
        except Exception:
            continue
        finally:
            archivo.seek(0)
        filas_totales += len(df)
        columna = next((c for c in df.columns
                        if str(c).strip().upper() in ("STATUS", "ESTATUS")), None)
        if columna is None:
            continue
        for valor in df[columna]:
            clave = _est.clasificar_status(valor)
            conteo[clave] = conteo.get(clave, 0) + 1

    if not filas_totales:
        return

    if not conteo:
        ui.resumen_lectura(filas_totales, [])
        st.warning(
            "No se encontró una columna STATUS en el archivo. El reporte se "
            "generará sin el desglose por estatus."
        )
        return

    ui.resumen_lectura(filas_totales, [
        (_est.etiqueta(c), n, _est.COLOR_CATEGORIA.get(c, ui.TEXTO_TENUE))
        for c, n in sorted(conteo.items(), key=lambda x: -x[1])
    ])

    # Un estatus fuera del catálogo se grafica igual, pero sin color ni
    # etiqueta propios: conviene avisarlo aquí, no solo en la consola.
    sin_catalogar = [c for c in conteo if not _est.esta_catalogado(c)]
    if sin_catalogar:
        st.warning(
            "Estatus fuera del catálogo: **" + ", ".join(sorted(sin_catalogar)) + "**. "
            "El reporte los incluye con un color automático. Para fijarles "
            "color y etiqueta, agrégalos en `herramientas/estatus.py`."
        )


# =======================================================================
# BARRA LATERAL — marca y menú de herramientas
# =======================================================================
with st.sidebar:
    ui.marca("Reportes MG Colima", "Autoexpress Inbursa")
    ui.grupo("Herramientas")
    herramienta = st.radio(
        "Herramienta",
        REGISTRO,
        format_func=_etiqueta_menu,
        label_visibility="collapsed",
        key="herramienta_activa",
    )
    ui.nota_lateral(
        "Los archivos que subes se procesan en el momento y se borran al "
        "terminar. Nada se guarda en el servidor."
    )

# =======================================================================
# HERRAMIENTA ELEGIDA
# =======================================================================
etiquetas = ["." + t.upper() for t in herramienta.tipos_permitidos]
etiquetas.append("Varios archivos" if herramienta.multiple_archivos else "1 archivo")
ui.encabezado(ui.nombre_limpio(herramienta.nombre), herramienta.descripcion, etiquetas)

usa_datos_reporte = herramienta.id in ("avance_preliminar", "comparativo_mensual",
                                       "resumen_mensual", "resumen_vendedor")
usa_etiquetas_mes = herramienta.id in ("comparativo_mensual", "modelo_datos")
tiene_opciones = (usa_datos_reporte or usa_etiquetas_mes
                  or herramienta.id == "resumen_vendedor")
opciones = {}

# --- 1. Archivo ---------------------------------------------------------
with st.container(border=True, key="tarjeta_archivo"):
    ui.paso(1, "Sube el archivo" + ("s" if herramienta.multiple_archivos else ""),
            herramienta.ayuda_archivo or "")
    archivos_subidos = st.file_uploader(
        "Archivo" + ("s" if herramienta.multiple_archivos else ""),
        type=herramienta.tipos_permitidos,
        accept_multiple_files=herramienta.multiple_archivos,
        label_visibility="collapsed",
        key=f"uploader_{herramienta.id}",
    )
    if archivos_subidos and not herramienta.multiple_archivos:
        archivos_subidos = [archivos_subidos]

    if archivos_subidos and herramienta.id != "relacion_zip":
        _vista_previa(archivos_subidos)

    # El comparativo necesita al menos dos meses para poder comparar.
    if (herramienta.id == "comparativo_mensual" and archivos_subidos
            and len(archivos_subidos) < 2):
        st.warning("Sube al menos dos archivos para poder comparar meses.")

# --- 2. Datos del reporte (solo si la herramienta los pide) --------------
if tiene_opciones:
    with st.container(border=True, key="tarjeta_datos"):
        ui.paso(2, "Datos del reporte",
                "Aparecen en el encabezado y el pie de los documentos.")

        if usa_datos_reporte:
            col_pdv, col_analista = st.columns(2)
            opciones["nombre_pdv"] = col_pdv.text_input(
                "Nombre del PDV", value=_PDV_DEFECTO, key=f"pdv_{herramienta.id}",
            )
            opciones["nombre_analista"] = col_analista.text_input(
                "Implant", value=_ANALISTA_DEFECTO, key=f"analista_{herramienta.id}",
            )

        if herramienta.id == "avance_preliminar":
            usar_hoy = st.toggle("Usar la fecha de hoy como fecha de corte", value=True,
                                 key=f"hoy_{herramienta.id}")
            if not usar_hoy:
                fecha_elegida = st.date_input("Fecha de corte", value=_fechas.hoy(),
                                              format="DD/MM/YYYY",
                                              key=f"fecha_{herramienta.id}")
                opciones["fecha_corte"] = fecha_elegida.strftime("%d/%m/%Y")

        if herramienta.id == "resumen_vendedor":
            with st.expander("Generar solo para ciertos vendedores (opcional)",
                             icon=":material/filter_list:"):
                st.caption(
                    "Por default se genera el PDF de todos los vendedores que "
                    "aparezcan en el Excel. Para limitarlo, escribe un nombre "
                    "por línea, tal como viene en la columna Nombre del Vendedor."
                )
                texto_vend = st.text_area("Un vendedor por línea",
                                          key=f"vend_{herramienta.id}")
                if texto_vend.strip():
                    opciones["vendedores_incluir"] = [
                        l.strip() for l in texto_vend.splitlines() if l.strip()
                    ]

        if usa_etiquetas_mes:
            with st.expander("Etiquetas de mes (opcional)", icon=":material/label:"):
                st.caption(
                    "Por default se usa el nombre de la hoja de cada Excel. "
                    "Si quieres forzar otra etiqueta, escribe una por línea, "
                    "en el mismo orden en que subiste los archivos."
                )
                texto_meses = st.text_area("Un mes por línea", key=f"meses_{herramienta.id}")
                if texto_meses.strip():
                    opciones["nombres_meses"] = [l.strip() for l in texto_meses.splitlines() if l.strip()]

generar = st.button("Generar reporte", key=f"generar_{herramienta.id}",
                    type="primary", icon=":material/bolt:", width="stretch",
                    disabled=not archivos_subidos)

# Los resultados se guardan en session_state, NO se dibujan solo dentro
# del "if generar". st.button() solo devuelve True en el rerun inmediato al
# clic, y st.download_button() provoca un rerun al descargar: si los botones
# dependieran de "generar", al bajar el PDF desaparecería el botón del Word.
# Como la clave es por herramienta, el resultado sigue ahí si cambias de
# herramienta en el menú y regresas.
clave_resultado = f"resultado_{herramienta.id}"

if generar and archivos_subidos:
    with st.spinner("Generando el reporte. Puede tardar uno o dos minutos."):
        try:
            archivos, registro = _procesar(herramienta, archivos_subidos, opciones)
        except Exception as e:
            st.session_state.pop(clave_resultado, None)
            st.error(f"No se pudo generar el reporte: {e}", icon=":material/error:")
            with st.expander("Detalle técnico"):
                st.code(traceback.format_exc())
        else:
            st.session_state[clave_resultado] = {
                "archivos": archivos,
                "log": registro,
                "fecha": _fechas.ahora().strftime("%d/%m/%Y · %H:%M"),
            }

# --- 3. Descargas -------------------------------------------------------
resultado = st.session_state.get(clave_resultado)
if resultado:
    with st.container(border=True, key="tarjeta_descargas"):
        cuantos = len(resultado["archivos"])
        ui.paso(3 if tiene_opciones else 2, "Descargas",
                f"{cuantos} archivo{'s' if cuantos != 1 else ''} · generado el {resultado['fecha']}")

        if not resultado["archivos"]:
            st.warning("El proceso terminó, pero no se generó ningún archivo de salida.")

        # Los bytes ya están en memoria: no se lee del disco, porque el
        # archivo generado se borró junto con el temporal.
        for i, (nombre, contenido) in enumerate(resultado["archivos"]):
            with st.container(key=f"archivo_{herramienta.id}_{i}"):
                col_info, col_boton = st.columns([0.74, 0.26], vertical_alignment="center")
                with col_info:
                    ui.fila_archivo(nombre, contenido)
                with col_boton:
                    st.download_button(
                        "Descargar",
                        data=contenido,
                        file_name=nombre,
                        icon=":material/download:",
                        key=f"descarga_{herramienta.id}_{nombre}",
                        width="stretch",
                    )

        if resultado.get("log"):
            with st.expander("Detalle del proceso", icon=":material/terminal:"):
                st.code(resultado["log"], language=None)
