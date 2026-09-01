# -*- coding: utf-8 -*-
"""
App de reportes — Bitácora de Solicitudes MG Colima (Autoexpress Inbursa)

Une, detrás de una interfaz simple de "sube el archivo y descarga el
resultado", los scripts de Colab que ya se usan para la bitácora mensual.
No hay que tocar este archivo para agregar una herramienta nueva más
adelante — ver las instrucciones en herramientas/__init__.py.
"""

import os
import traceback
from datetime import date

import streamlit as st

from herramientas import REGISTRO
from herramientas.avance_preliminar_original import (
    NOMBRE_ANALISTA as _ANALISTA_DEFECTO,
    SUBTITULO_EMPRESA as _PDV_DEFECTO,
)

CARPETA_ENTRADAS = os.path.abspath("entradas")
CARPETA_SALIDA = os.path.abspath("salida")
os.makedirs(CARPETA_ENTRADAS, exist_ok=True)
os.makedirs(CARPETA_SALIDA, exist_ok=True)

st.set_page_config(page_title="Reportes Bitácora MG Colima", page_icon="📋", layout="centered")

st.title("📋 Reportes — Bitácora MG Colima")
st.caption(
    "Sube el archivo que te pida cada herramienta y descarga el Excel o "
    "PDF ya generado. No hace falta saber programación ni tocar el código."
)


def _guardar_subidas(archivos_subidos, prefijo):
    """Guarda en disco los archivos que Streamlit recibe en memoria y
    devuelve la lista de rutas locales, en el mismo orden."""
    rutas = []
    for i, archivo in enumerate(archivos_subidos):
        ruta = os.path.join(CARPETA_ENTRADAS, f"{prefijo}_{i}_{archivo.name}")
        with open(ruta, "wb") as f:
            f.write(archivo.getbuffer())
        rutas.append(ruta)
    return rutas


tabs = st.tabs([h.nombre for h in REGISTRO])

for tab, herramienta in zip(tabs, REGISTRO):
    with tab:
        st.markdown(herramienta.descripcion)

        archivos_subidos = st.file_uploader(
            "Archivo" + ("s" if herramienta.multiple_archivos else ""),
            type=herramienta.tipos_permitidos,
            accept_multiple_files=herramienta.multiple_archivos,
            help=herramienta.ayuda_archivo,
            key=f"uploader_{herramienta.id}",
        )
        if archivos_subidos and not herramienta.multiple_archivos:
            archivos_subidos = [archivos_subidos]

        # --- Opciones extra específicas de cada herramienta ---
        opciones = {}

        if herramienta.id in ("avance_preliminar", "comparativo_mensual"):
            col_pdv, col_analista = st.columns(2)
            opciones["nombre_pdv"] = col_pdv.text_input(
                "Nombre del PDV", value=_PDV_DEFECTO, key=f"pdv_{herramienta.id}",
            )
            opciones["nombre_analista"] = col_analista.text_input(
                "Analista", value=_ANALISTA_DEFECTO, key=f"analista_{herramienta.id}",
            )

        if herramienta.id == "avance_preliminar":
            usar_hoy = st.checkbox("Usar la fecha de hoy como fecha de corte", value=True,
                                    key=f"hoy_{herramienta.id}")
            if not usar_hoy:
                fecha_elegida = st.date_input("Fecha de corte", value=date.today(),
                                               key=f"fecha_{herramienta.id}")
                opciones["fecha_corte"] = fecha_elegida.strftime("%d/%m/%Y")

        if herramienta.id == "comparativo_mensual":
            with st.expander("Etiquetas de mes (opcional)"):
                st.caption(
                    "Por default se usa el nombre de la hoja de cada Excel. "
                    "Si quieres forzar otra etiqueta, escribe una por línea, "
                    "en el mismo orden en que subiste los archivos."
                )
                texto_meses = st.text_area("Un mes por línea", key=f"meses_{herramienta.id}")
                if texto_meses.strip():
                    opciones["nombres_meses"] = [l.strip() for l in texto_meses.splitlines() if l.strip()]

        generar = st.button("Generar", key=f"generar_{herramienta.id}", type="primary",
                             disabled=not archivos_subidos)

        if generar and archivos_subidos:
            with st.spinner("Procesando... esto puede tardar uno o dos minutos."):
                try:
                    rutas_locales = _guardar_subidas(archivos_subidos, herramienta.id)
                    resultados = herramienta.ejecutar(
                        rutas_locales, carpeta_salida=CARPETA_SALIDA, **opciones
                    )
                except Exception as e:
                    st.error(f"Algo falló al generar el reporte: {e}")
                    with st.expander("Detalle técnico"):
                        st.code(traceback.format_exc())
                else:
                    if not resultados:
                        st.warning("Se terminó de procesar, pero no se encontró el archivo de salida.")
                    else:
                        st.success("¡Listo! Descarga tu archivo:")
                        for ruta in resultados:
                            with open(ruta, "rb") as f:
                                st.download_button(
                                    f"⬇️ Descargar {os.path.basename(ruta)}",
                                    data=f.read(),
                                    file_name=os.path.basename(ruta),
                                    key=f"descarga_{herramienta.id}_{os.path.basename(ruta)}",
                                )
