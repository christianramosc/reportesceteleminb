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
from datetime import date

import pandas as pd
import streamlit as st

from herramientas import REGISTRO
from herramientas import estatus as _est
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

st.set_page_config(page_title="Reportes Bitácora MG Colima", page_icon="📋", layout="centered")

st.title("📋 Reportes — Bitácora MG Colima")
st.caption(
    "Sube el archivo que te pida cada herramienta y descarga el Excel o "
    "PDF ya generado."
)


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
    st.info(f"Se leyeron **{filas_totales}** solicitudes.")

    if not conteo:
        st.warning(
            "No se encontró una columna STATUS en el archivo. El reporte se "
            "generará sin el desglose por estatus."
        )
        return

    resumen = ", ".join(f"{_est.etiqueta(c)}: {n}"
                        for c, n in sorted(conteo.items(), key=lambda x: -x[1]))
    st.caption(f"Estatus detectados — {resumen}")

    # Un estatus fuera del catálogo se grafica igual, pero sin color ni
    # etiqueta propios: conviene avisarlo aquí, no solo en la consola.
    sin_catalogar = [c for c in conteo if not _est.esta_catalogado(c)]
    if sin_catalogar:
        st.warning(
            "Estatus fuera del catálogo: **" + ", ".join(sorted(sin_catalogar)) + "**. "
            "El reporte los incluye con un color automático. Para fijarles "
            "color y etiqueta, agrégalos en `herramientas/estatus.py`."
        )


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

        if archivos_subidos and herramienta.id != "relacion_zip":
            _vista_previa(archivos_subidos)

        # El comparativo necesita al menos dos meses para poder comparar.
        if (herramienta.id == "comparativo_mensual" and archivos_subidos
                and len(archivos_subidos) < 2):
            st.warning("Sube al menos dos archivos para poder comparar meses.")

        # --- Opciones extra específicas de cada herramienta ---
        opciones = {}

        if herramienta.id in ("avance_preliminar", "comparativo_mensual", "resumen_mensual"):
            col_pdv, col_analista = st.columns(2)
            opciones["nombre_pdv"] = col_pdv.text_input(
                "Nombre del PDV", value=_PDV_DEFECTO, key=f"pdv_{herramienta.id}",
            )
            opciones["nombre_analista"] = col_analista.text_input(
                "Implant", value=_ANALISTA_DEFECTO, key=f"analista_{herramienta.id}",
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

        # Los resultados se guardan en session_state, NO se dibujan solo
        # dentro del "if generar". st.button() solo devuelve True en el rerun
        # inmediato al clic, y st.download_button() provoca un rerun al
        # descargar: si los botones dependieran de "generar", al bajar el PDF
        # desaparecería el botón del Word.
        clave_resultado = f"resultado_{herramienta.id}"

        if generar and archivos_subidos:
            with st.spinner("Procesando... esto puede tardar uno o dos minutos."):
                try:
                    archivos, registro = _procesar(herramienta, archivos_subidos, opciones)
                except Exception as e:
                    st.session_state.pop(clave_resultado, None)
                    st.error(f"Algo falló al generar el reporte: {e}")
                    with st.expander("Detalle técnico"):
                        st.code(traceback.format_exc())
                else:
                    st.session_state[clave_resultado] = {
                        "archivos": archivos,
                        "log": registro,
                        "fecha": date.today().strftime("%d/%m/%Y"),
                    }

        resultado = st.session_state.get(clave_resultado)
        if resultado:
            if not resultado["archivos"]:
                st.warning("Se terminó de procesar, pero no se encontró el archivo de salida.")
            else:
                st.success("¡Listo! Descarga tus archivos:")
                # Los bytes ya están en memoria: no se lee del disco, porque
                # el archivo generado se borró junto con el temporal.
                columnas = st.columns(min(len(resultado["archivos"]), 3))
                for i, (nombre, contenido) in enumerate(resultado["archivos"]):
                    icono = "📄" if nombre.lower().endswith(".pdf") else "📝"
                    columnas[i % len(columnas)].download_button(
                        f"{icono} {nombre.rsplit('.', 1)[-1].upper()}",
                        data=contenido,
                        file_name=nombre,
                        key=f"descarga_{herramienta.id}_{nombre}",
                        use_container_width=True,
                    )

            if resultado.get("log"):
                with st.expander("Detalle del proceso"):
                    st.code(resultado["log"])
