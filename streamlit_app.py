"""
Reportes y Herramientas — Bitácora de Solicitudes (Autoexpress Inbursa)

Sirve para cualquier PDV: el nombre del PDV y del implant se capturan en
cada reporte.

Une, detrás de una interfaz simple de "sube el archivo y descarga el
resultado", los reportes de la bitácora mensual y el validador de CSF.
No hay que tocar este archivo para agregar una herramienta nueva más
adelante — ver las instrucciones en herramientas/__init__.py.
"""

import os
import shutil
import tempfile
import traceback

import io
import zipfile

import pandas as pd
import streamlit as st

import ui_estilos as ui
from herramientas import REGISTRO
from herramientas import estatus as _est
from herramientas import fechas as _fechas
from herramientas import vista_bitacora as _vista
from herramientas.ejecucion import ejecutar_aislado
from herramientas.config import ANALISTA_DEFECTO as _ANALISTA_DEFECTO
from herramientas.config import PDV_DEFECTO as _PDV_DEFECTO

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
    page_title="Reportes y Herramientas",
    page_icon=":material/bar_chart:",
    layout="centered",
    initial_sidebar_state="auto",   # abierto en computadora, cerrado en celular
)

ui.aplicar_estilos()

def _etiqueta_menu(h):
    """Menú lateral: icono y nombre corto que declara cada herramienta
    (registro.py). El nombre completo se usa como título de la página."""
    return f"{h.icono} {h.nombre_corto or ui.nombre_limpio(h.nombre)}"


def _procesar(herramienta, archivos_subidos, opciones, archivos_anteriores=()):
    """Ejecuta la herramienta en un directorio temporal y devuelve los
    resultados EN MEMORIA como [(nombre, bytes), ...], el log y, si la
    herramienta lo da, un resumen para dibujar en la página.

    El directorio se borra en el `finally`, así que el Excel del cliente no
    sobrevive a la corrida ni siquiera cuando algo falla a medio camino.

    La herramienta corre con un candado (herramientas/ejecucion.py): si otra
    persona está generando, este reporte espera su turno en vez de mezclarse
    con el suyo.
    """
    carpeta = tempfile.mkdtemp(prefix=f"mg_{herramienta.id}_")
    aviso_fila = st.empty()
    try:
        rutas = []
        for i, archivo in enumerate(archivos_subidos):
            ruta = os.path.join(carpeta, f"{i}_{archivo.name}")
            with open(ruta, "wb") as f:
                f.write(archivo.getbuffer())
            rutas.append(ruta)

        # Meses anteriores (opcionales): siguen la numeración para que dos
        # archivos con el mismo nombre no se pisen.
        rutas_anteriores = []
        for j, archivo in enumerate(archivos_anteriores, start=len(rutas)):
            ruta = os.path.join(carpeta, f"{j}_{archivo.name}")
            with open(ruta, "wb") as f:
                f.write(archivo.getbuffer())
            rutas_anteriores.append(ruta)
        if rutas_anteriores:
            opciones = {**opciones, "rutas_anteriores": rutas_anteriores}

        carpeta_salida = os.path.join(carpeta, "salida")
        os.makedirs(carpeta_salida, exist_ok=True)

        resultados, log = ejecutar_aislado(
            herramienta, rutas, carpeta_salida,
            al_esperar=lambda: aviso_fila.info(
                "Hay otro reporte generándose. El tuyo empieza en cuanto termine.",
                icon=":material/hourglass_top:",
            ),
            **opciones,
        )

        # Una herramienta puede regresar {"archivos": [...], "resumen": obj}
        # además de la lista simple de rutas (ver registro.py).
        resumen = None
        if isinstance(resultados, dict):
            resumen = resultados.get("resumen")
            resultados = resultados.get("archivos")

        archivos = []
        for ruta in resultados or []:
            if os.path.exists(ruta):
                with open(ruta, "rb") as f:
                    archivos.append((os.path.basename(ruta), f.read()))
        return archivos, log, resumen
    finally:
        aviso_fila.empty()
        # Se lleva también las gráficas: cada reporte las dibuja dentro de
        # esta carpeta, junto a su PDF.
        shutil.rmtree(carpeta, ignore_errors=True)


def _vista_previa(archivos_subidos):
    """Muestra qué trae el Excel ANTES de generar: cuántas filas, qué
    estatus se detectaron y qué columnas faltan. Sirve para cachar una
    exportación incompleta o un estatus mal escrito sin esperar los dos
    minutos del reporte.

    Devuelve los vendedores del primer archivo (para el filtro del Resumen
    por Vendedor).
    """
    filas_totales = 0
    conteo = {}
    varias_hojas = []
    faltantes, otras = {}, []
    vendedores = None
    for archivo in archivos_subidos:
        try:
            archivo.seek(0)
            xls = pd.ExcelFile(archivo)
            df = xls.parse(xls.sheet_names[0])
        except Exception:
            continue
        finally:
            archivo.seek(0)
        if len(xls.sheet_names) > 1:
            varias_hojas.append(f"**{archivo.name}** → «{xls.sheet_names[0]}»")
        revision = _vista.revisar(df)
        filas_totales += revision["filas"]
        for clave, n in revision["conteo"].items():
            conteo[clave] = conteo.get(clave, 0) + n
        for columna, consecuencia in revision["faltantes"]:
            faltantes.setdefault(columna, (consecuencia, []))[1].append(archivo.name)
        otras += [c for c in revision["otras"] if c not in otras]
        if vendedores is None:
            vendedores = revision["vendedores"]

    # Los reportes leen solo la primera hoja: si los datos están en otra, el
    # reporte saldría con datos equivocados o vacío.
    if varias_hojas:
        st.info(
            "El archivo trae varias hojas; se usará solo la primera: "
            + "; ".join(varias_hojas) + ". Si los datos están en otra hoja, "
            "muévela al principio del libro.",
            icon=":material/tab:",
        )

    if not filas_totales:
        return vendedores or []

    if not conteo:
        ui.resumen_lectura(filas_totales, [])
        st.warning(
            "No se encontró una columna STATUS en el archivo. El reporte se "
            "generará sin el desglose por estatus."
        )
    else:
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

    # Columnas que faltan: antes solo se sabía al abrir el PDF y ver que una
    # sección no estaba. Se dice aquí, con lo que se pierde por cada una.
    if faltantes:
        varios = len(archivos_subidos) > 1
        renglones = []
        for columna, (consecuencia, nombres) in faltantes.items():
            donde = f" (en {', '.join(nombres)})" if varios else ""
            renglones.append(f"- **{columna}**{donde}: {consecuencia}.")
        st.warning(
            "Faltan columnas en la bitácora. El reporte se genera, pero sin estas partes:\n\n"
            + "\n".join(renglones),
            icon=":material/view_column:",
        )
    if otras:
        st.caption("También faltan, sin afectar las cifras: " + ", ".join(otras) + ".")

    return vendedores or []


def _zip_de(archivos, respaldo):
    """(nombre, bytes) de un ZIP con todos los archivos generados.

    El nombre sale de lo que tienen en común ("Resumen_Oct26.pdf",
    "Resumen_Oct26_datos.xlsx" -> "Resumen_Oct26_completo.zip")."""
    comun = os.path.commonprefix([nombre for nombre, _ in archivos]).rstrip(" ._-")
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, contenido in archivos:
            zf.writestr(nombre, contenido)
    return f"{comun or respaldo}_completo.zip", memoria.getvalue()


# =======================================================================
# BARRA LATERAL — marca y menú de herramientas
# =======================================================================
with st.sidebar:
    ui.marca("Reportes y Herramientas", "Autoexpress Inbursa", logo="RH")
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


@st.cache_data(show_spinner=False)
def _leer_guia(ruta):
    """Bytes de la guía (PDF o imagen). Se leen una vez por proceso, no en
    cada clic de la página."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta), "rb") as f:
        return f.read()


# --- Guía de uso (si la herramienta trae una) ------------------------------
if herramienta.guia:
    with st.expander(herramienta.guia_titulo, icon=":material/map:"):
        if herramienta.guia_vista:
            st.image(_leer_guia(herramienta.guia_vista), width="stretch")
        st.download_button(
            "Descargar guía completa (PDF)",
            data=_leer_guia(herramienta.guia),
            file_name=os.path.basename(herramienta.guia),
            mime="application/pdf",
            icon=":material/download:",
            key=f"guia_{herramienta.id}",
        )

# Qué campos mostrar lo declara cada herramienta (registro.py), no una
# lista de ids aquí: una herramienta nueva no obliga a tocar este archivo.
tiene_opciones = herramienta.tiene_opciones
opciones = {}

# Los resultados se guardan en session_state, NO se dibujan solo dentro
# del "if generar". st.button() solo devuelve True en el rerun inmediato al
# clic, y st.download_button() provoca un rerun al descargar: si los botones
# dependieran de "generar", al bajar el PDF desaparecería el botón del Word.
# Como la clave es por herramienta, el resultado sigue ahí si cambias de
# herramienta en el menú y regresas.
clave_resultado = f"resultado_{herramienta.id}"


def _olvidar_resultado(clave, *otras_claves):
    """Al subir, cambiar o quitar el archivo, las descargas anteriores ya no
    corresponden a lo que está en pantalla. Antes seguían visibles hasta
    volver a generar y era fácil bajar el reporte del archivo anterior.

    otras_claves: lo que también depende del archivo (los vendedores
    elegidos: con otro Excel pueden no existir)."""
    for c in (clave, *otras_claves):
        st.session_state.pop(c, None)


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
        on_change=_olvidar_resultado,
        args=(clave_resultado, f"vend_{herramienta.id}"),
    )
    if archivos_subidos and not herramienta.multiple_archivos:
        archivos_subidos = [archivos_subidos]

    # La vista previa lee la bitácora en Excel; no aplica a ZIP ni a CSF en PDF.
    vendedores_del_archivo = []
    if archivos_subidos and herramienta.vista_previa_bitacora:
        vendedores_del_archivo = _vista_previa(archivos_subidos)

    # El comparativo, por ejemplo, necesita al menos dos meses para comparar.
    if archivos_subidos and len(archivos_subidos) < herramienta.minimo_archivos:
        st.warning(f"Sube al menos {herramienta.minimo_archivos} archivos para poder comparar.")

    # Meses anteriores: opcionales, para comparar contra ellos.
    archivos_anteriores = []
    if herramienta.meses_anteriores:
        varios_meses = herramienta.meses_anteriores == "varios"
        with st.expander("Comparar con " + ("meses anteriores" if varios_meses else "el mes anterior")
                         + " (opcional)", icon=":material/history:"):
            if herramienta.ayuda_meses_anteriores:
                st.caption(herramienta.ayuda_meses_anteriores)
            anteriores = st.file_uploader(
                "Bitácoras anteriores" if varios_meses else "Bitácora del mes anterior",
                type=["xlsx"],
                accept_multiple_files=varios_meses,
                label_visibility="collapsed",
                key=f"anteriores_{herramienta.id}",
                on_change=_olvidar_resultado,
                args=(clave_resultado,),
            )
            if anteriores:
                archivos_anteriores = anteriores if varios_meses else [anteriores]

# --- 2. Datos del reporte (solo si la herramienta los pide) --------------
if tiene_opciones:
    with st.container(border=True, key="tarjeta_datos"):
        ui.paso(2, "Datos del reporte",
                "Aparecen en el encabezado y el pie de los documentos.")

        if herramienta.pide_pdv_e_implant:
            col_pdv, col_analista = st.columns(2)
            opciones["nombre_pdv"] = col_pdv.text_input(
                "Nombre del PDV", value=_PDV_DEFECTO, key=f"pdv_{herramienta.id}",
            )
            opciones["nombre_analista"] = col_analista.text_input(
                "Implant", value=_ANALISTA_DEFECTO, key=f"analista_{herramienta.id}",
            )

        if herramienta.pide_fecha_corte:
            usar_hoy = st.toggle("Usar la fecha de hoy como fecha de corte", value=True,
                                 key=f"hoy_{herramienta.id}")
            if not usar_hoy:
                fecha_elegida = st.date_input("Fecha de corte", value=_fechas.hoy(),
                                              format="DD/MM/YYYY",
                                              key=f"fecha_{herramienta.id}")
                opciones["fecha_corte"] = fecha_elegida.strftime("%d/%m/%Y")

        if herramienta.pide_vendedores:
            # Los nombres salen del Excel que se subió: antes se escribían a
            # mano, uno por línea, y un error de dedo dejaba fuera a alguien
            # sin avisar.
            elegidos = st.multiselect(
                "Vendedores",
                vendedores_del_archivo,
                key=f"vend_{herramienta.id}",
                placeholder=("Todos los vendedores" if vendedores_del_archivo
                             else "Sube primero el archivo"),
                disabled=not vendedores_del_archivo,
                help="Déjalo vacío para generar el PDF de todos. Elige uno o "
                     "varios para limitarlo.",
            )
            if elegidos:
                opciones["vendedores_incluir"] = elegidos

        if herramienta.pide_etiquetas_mes:
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

if generar and archivos_subidos:
    with st.spinner("Generando el reporte. Puede tardar uno o dos minutos."):
        try:
            archivos, registro, resumen = _procesar(herramienta, archivos_subidos, opciones,
                                                    archivos_anteriores)
        except Exception as e:
            st.session_state.pop(clave_resultado, None)
            st.error(f"No se pudo generar el reporte: {e}", icon=":material/error:")
            with st.expander("Detalle técnico"):
                st.code(traceback.format_exc())
        else:
            st.session_state[clave_resultado] = {
                "archivos": archivos,
                "log": registro,
                "resumen": resumen,
                "fecha": _fechas.ahora().strftime("%d/%m/%Y · %H:%M"),
                # Todo junto en un ZIP, armado una sola vez (no en cada clic).
                "zip": _zip_de(archivos, herramienta.id) if len(archivos) > 1 else None,
            }

# --- 3. Resultado en la página (si la herramienta lo ofrece) --------------
resultado = st.session_state.get(clave_resultado)
paso_siguiente = 3 if tiene_opciones else 2
if resultado and resultado.get("resumen") is not None and herramienta.mostrar_resumen:
    with st.container(border=True, key="tarjeta_resumen"):
        ui.paso(paso_siguiente, "Resultado",
                f"Generado el {resultado['fecha']} · el detalle completo está en el PDF de Descargas.")
        herramienta.mostrar_resumen(resultado["resumen"])
    paso_siguiente += 1

# --- Descargas -----------------------------------------------------------
if resultado:
    with st.container(border=True, key="tarjeta_descargas"):
        cuantos = len(resultado["archivos"])
        ui.paso(paso_siguiente, "Descargas",
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

        if resultado.get("zip"):
            nombre_zip, contenido_zip = resultado["zip"]
            st.download_button(
                f"Descargar todo en un ZIP ({cuantos} archivos)",
                data=contenido_zip,
                file_name=nombre_zip,
                mime="application/zip",
                icon=":material/folder_zip:",
                key=f"todo_{herramienta.id}",
                width="stretch",
            )

        if resultado.get("log"):
            with st.expander("Detalle del proceso", icon=":material/terminal:"):
                st.code(resultado["log"], language=None)
