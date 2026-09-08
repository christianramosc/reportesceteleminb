# -*- coding: utf-8 -*-
"""
Relación de clientes por STATUS — MG Colima (versión módulo, sin Colab)

Refactor de Relacion_de_clientes_ZIP_DEL_MES.ipynb: toda la lógica de
extracción de PDFs y armado del Excel es EXACTAMENTE la misma que en el
notebook original; lo único que cambia es que en vez de subir el ZIP con
`files.upload()` (Colab), la función `procesar_zip_a_excel()` recibe la
ruta del ZIP como parámetro, para poder llamarse desde la app de Streamlit.

Para leer los PDFs usa el binario `pdftotext` (poppler) si está disponible;
si no, cae automáticamente a pdfplumber (Python puro). Ver extraer_texto_pdf().
"""

import os
import re
import glob
import shutil
import zipfile
import subprocess
import unicodedata
import pandas as pd
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# Normalización de nombres de carpeta -> STATUS (plural/singular, variantes).
# Si aparece una carpeta nueva que no está aquí, se usa su nombre en mayúsculas
# tal cual, así que el notebook funciona aunque agreguen carpetas nuevas.
# ─────────────────────────────────────────────
MAPEO_STATUS = {
    "APROBADOS":        "APROBADO",
    "APROBADO":         "APROBADO",
    "RECHAZADOS":       "RECHAZADO",
    "RECHAZADO":        "RECHAZADO",
    "CONTRAPROPUESTAS": "CONTRAPROPUESTA",
    "CONTRAPROPUESTA":  "CONTRAPROPUESTA",
    "PENDIENTES":       "PENDIENTE",
    "PENDIENTE":        "PENDIENTE",
    "CANCELADOS":       "CANCELADO",
    "CANCELADO":        "CANCELADO",
    "EN PROCESO":       "EN PROCESO",
    "EN REVISION":      "EN REVISIÓN",
}

LIMPIAR_TEMPORAL = True   # borra los PDFs extraídos al terminar

MESES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}


def normalizar_status(nombre_carpeta: str) -> str:
    """Convierte el nombre de una carpeta en el valor de STATUS a usar."""
    nombre = nombre_carpeta.strip().upper()
    nombre = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("utf-8")
    return MAPEO_STATUS.get(nombre, nombre)


def detectar_mes_anio(texto: str) -> str:
    """Detecta el mes (y el año, si viene) dentro de un texto —típicamente
    el nombre del ZIP o el de su carpeta raíz, ej. 'JUNIO', 'Junio_2026',
    'bitacora-julio-2026'— y devuelve el nombre de hoja en formato
    'MES AAAA'. Si no encuentra un mes reconocible en el texto, usa el mes
    y año actuales como respaldo. Si encuentra mes pero no año, usa el año
    actual."""
    t = texto.strip().upper()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    t = re.sub(r"[_\-.]", " ", t)

    mes_detectado = next((m for m in MESES_ES.values() if m in t), None)

    m_anio = re.search(r"(20\d{2})", t)
    anio_detectado = m_anio.group(1) if m_anio else None

    ahora = datetime.now()
    if not mes_detectado:
        print(f"  ⚠ No se detectó un mes en '{texto}'; se usa el mes actual como respaldo.")
        mes_detectado = MESES_ES[ahora.month]

    if not anio_detectado:
        anio_detectado = str(ahora.year)

    return f"{mes_detectado} {anio_detectado}"


def extraer_zip(ruta_zip: str, carpeta_destino: str) -> str:
    """Extrae el ZIP y devuelve la ruta de la carpeta que contiene las
    subcarpetas de estatus (soporta ZIPs con una carpeta raíz envolvente,
    como 'JUNIO/Aprobados/...', y ZIPs sin ella)."""
    if os.path.isdir(carpeta_destino):
        shutil.rmtree(carpeta_destino)
    os.makedirs(carpeta_destino, exist_ok=True)

    with zipfile.ZipFile(ruta_zip, "r") as z:
        z.extractall(carpeta_destino)

    contenido = [
        os.path.join(carpeta_destino, n)
        for n in os.listdir(carpeta_destino)
        if not n.startswith("__MACOSX") and not n.startswith(".")
    ]
    subdirs = [c for c in contenido if os.path.isdir(c)]

    # Si el ZIP trae una única carpeta raíz envolviendo todo, se usa esa.
    if len(subdirs) == 1 and len(contenido) == 1:
        return subdirs[0]
    return carpeta_destino


def detectar_carpetas_status(carpeta_raiz: str) -> dict:
    """Detecta automáticamente las subcarpetas de estatus dentro de la carpeta raíz.
    Devuelve {nombre_carpeta_original: STATUS_normalizado}."""
    carpetas = {}
    for nombre in sorted(os.listdir(carpeta_raiz)):
        ruta = os.path.join(carpeta_raiz, nombre)
        if os.path.isdir(ruta) and not nombre.startswith(".") and not nombre.startswith("__MACOSX"):
            carpetas[nombre] = normalizar_status(nombre)
    return carpetas


def _hay_pdftotext() -> bool:
    """True si el binario pdftotext (poppler) está disponible en el sistema."""
    return shutil.which("pdftotext") is not None


def _extraer_con_pdftotext(ruta: str) -> str:
    resultado = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", ruta, "-"],
        capture_output=True
    )
    if resultado.returncode != 0:
        print(f"  ⚠ pdftotext falló (código {resultado.returncode}): {os.path.basename(ruta)}")
        return ""
    return resultado.stdout.decode("utf-8", errors="replace")


def _extraer_con_pdfplumber(ruta: str) -> str:
    """Equivalente en Python puro de `pdftotext -layout`.

    `extract_text(layout=True)` respeta la posición horizontal y vertical del
    texto igual que la opción -layout, que es de lo que dependen las
    expresiones regulares de parsear_solicitud() y parsear_amortizacion()
    (label en una línea, valor en la siguiente). Las páginas se separan con
    "\\f" igual que pdftotext.
    """
    try:
        import pdfplumber
    except ImportError:
        print("  ⚠ No hay pdftotext ni pdfplumber instalado; no se puede leer el PDF.")
        return ""

    try:
        with pdfplumber.open(ruta) as pdf:
            paginas = [(p.extract_text(layout=True) or "") for p in pdf.pages]
        return "\n\f".join(paginas)
    except Exception as e:
        print(f"  ⚠ pdfplumber falló ({e}): {os.path.basename(ruta)}")
        return ""


def extraer_texto_pdf(ruta: str) -> str:
    """Extrae el texto de un PDF conservando el acomodo visual.

    Usa el binario `pdftotext` (poppler) si está instalado —es más rápido y es
    con el que se calibraron las expresiones regulares—; si no está, cae a
    pdfplumber, que hace lo mismo en Python puro.

    Este fallback existe porque Streamlit Community Cloud ya no puede instalar
    paquetes de sistema vía packages.txt (el repositorio bullseye-security de
    Debian quedó vencido y apt-get aborta el despliegue completo).
    """
    if _hay_pdftotext():
        return _extraer_con_pdftotext(ruta)
    return _extraer_con_pdfplumber(ruta)


def limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def extraer_monto(cadena: str) -> str:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", cadena)
    return f"${match.group(1)}" if match else cadena.strip()


def extraer_monto_float(cadena: str) -> float:
    """Convierte un monto tipo '$ 8,800.00' a float (0.0 si no hay monto)."""
    match = re.search(r"\$\s*([\d,]+\.?\d*)", cadena)
    return float(match.group(1).replace(",", "")) if match else 0.0


def normalizar_tipo_seguro(texto_tipo: str) -> str:
    """Normaliza el campo 'Tipo' de seguro a una de 3 categorías:
    MULTIANUAL FRACCIONADO, MULTIANUAL FINANCIADO o CONTADO ANUAL.
    Si aparece una variante nueva no reconocida, se devuelve el texto
    original en mayúsculas (así no se pierde información)."""
    t = texto_tipo.strip().upper()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    if "FRACCIONADO" in t:
        return "MULTIANUAL FRACCIONADO"
    if "FINANCIADO" in t:
        return "MULTIANUAL FINANCIADO"
    if "CONTADO" in t and "ANUAL" in t:
        return "CONTADO ANUAL"
    return t


def _extraer_apellidos(texto: str) -> tuple:
    """Devuelve (primer_apellido, segundo_apellido) del solicitante.

    En la forma CTL-008, ambas etiquetas viven en la MISMA línea, una en cada
    columna, y los dos valores en la línea de abajo:

        Primer apellido:                    Segundo apellido:
        ARROYO                              BUSTOS

    Por eso no sirve buscar "Primer apellido:" seguido de salto de línea: lo
    que sigue a esa etiqueta no es un salto sino la etiqueta de la derecha.
    Aquí se localiza la línea con AMBAS etiquetas y se parte la línea de
    valores en la posición donde arranca la columna derecha, usando la
    posición de "Segundo apellido:" como punto de corte. Funciona igual con
    pdftotext y con pdfplumber porque ambos conservan la alineación de
    columnas, aunque usen anchos de espaciado distintos.
    """
    lineas = texto.split("\n")
    for i, linea in enumerate(lineas[:-1]):
        bajo = linea.lower()
        if "primer apellido:" in bajo and "segundo apellido:" in bajo:
            corte = bajo.index("segundo apellido:")
            valores = lineas[i + 1]
            # Margen de 2 caracteres: la columna de valores puede quedar
            # desplazada un carácter respecto a la de etiquetas.
            izq = limpiar(valores[:max(0, corte - 2)])
            der = limpiar(valores[max(0, corte - 2):])
            return izq, der

    # Respaldo: si en algún formato las etiquetas sí van en líneas separadas,
    # se usa la lectura de toda la vida.
    m1 = re.search(r"Primer apellido:\s*\n\s*([A-Z\xc0-\xff ]+)", texto)
    m2 = re.search(r"Segundo apellido:\s*\n\s*([A-Z\xc0-\xff ]+)", texto)
    return (limpiar(m1.group(1)) if m1 else "",
            limpiar(m2.group(1)) if m2 else "")


def parsear_solicitud(texto: str) -> dict:
    if not texto:
        return {}

    datos = {}

    m = re.search(r"Folio CCK:\s*(\d+)", texto)
    datos["folio_cck"] = m.group(1).strip() if m else ""

    m_nombres = re.search(r"Nombre\(s\):\s*\n\s*([A-Z\xc0-\xff ]+)", texto)
    nombres = limpiar(m_nombres.group(1)) if m_nombres else ""

    apellido1, apellido2 = _extraer_apellidos(texto)

    # Se unen con " ".join filtrando los vacíos: si algún apellido falta, no
    # queda un espacio doble en medio del nombre.
    datos["nombre_completo"] = " ".join(x for x in (nombres, apellido1, apellido2) if x)
    datos["primer_apellido"]  = apellido1
    datos["segundo_apellido"] = apellido2

    m = re.search(
        r"Fecha de nacimiento\(dd/mm/aaaa\):.*?\n\s*(\d{2}/\d{2}/\d{4})",
        texto, re.IGNORECASE
    )
    datos["fecha_nacimiento"] = m.group(1).strip() if m else ""

    m = re.search(r"Tel[eé]fono m[oó]vil:.*?\n\s*\d+\s+(\d+)", texto, re.IGNORECASE)
    datos["telefono_movil"] = m.group(1).strip() if m else ""

    m = re.search(
        r"Correo electr[oó]nico:\s*\n\s*[\d\s]+\s+([\w._%+\-]+@[\w.\-]+)",
        texto, re.IGNORECASE
    )
    datos["correo_electronico"] = m.group(1).strip() if m else ""

    m = re.search(
        r"Nombre del vendedor:\s*\n\s*\d+\s+\w+\s+([A-Z\xc0-\xff ]+)",
        texto, re.IGNORECASE
    )
    datos["nombre_vendedor"] = limpiar(m.group(1)) if m else ""



    return datos


def _primera_columna(linea: str) -> str:
    """Devuelve solo la columna izquierda de una línea a dos columnas.

    Corta en el hueco de 4+ espacios que separa las columnas, y como respaldo
    en cualquier hueco de 2+ espacios seguido de una etiqueta ("Tipo:",
    "Tipo resto del plazo:"). El respaldo importa porque pdfplumber usa huecos
    más angostos que pdftotext y no siempre llega a 4 espacios.
    """
    trozo = re.split(r"\s{4,}", linea)[0]

    # Corte por ETIQUETA, no por espacios. Cuando el nombre del vehículo es
    # largo ("NEW ZS 1.5T COM TURBO EXCITE AT") el hueco entre columnas se
    # reduce a UN solo espacio y cualquier corte que cuente espacios falla.
    # Las etiquetas de la columna derecha ("Tipo:", "Tipo resto del plazo:",
    # "Importe primer año:", "Aseguradora:") empiezan con mayúscula seguida
    # de minúsculas y terminan en dos puntos; los nombres de vehículo van en
    # MAYÚSCULAS y nunca llevan ":". Esa diferencia es la que se aprovecha.
    m = re.search(r"\s+(?=[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+[\w áéíóúñÁÉÍÓÚÑ]*:)", trozo)
    if m:
        trozo = trozo[:m.start()]
    return trozo.strip()


def parsear_amortizacion(texto: str) -> dict:
    if not texto:
        return {}

    datos = {}

    m = re.search(r"Folio CCK:\s*(\d+)", texto)
    datos["folio_cck"] = m.group(1).strip() if m else ""

    # Marca y Vehículo viven en un layout de 2 columnas: a la derecha de su
    # valor viene la columna del seguro ("Tipo:", "Tipo resto del plazo:").
    # Se usa [ \t]+ y no \s{2,} porque pdftotext alinea las columnas con
    # muchos espacios ("Marca:         MG MOTOR") mientras que pdfplumber los
    # comprime a uno solo ("Marca: MG MOTOR"); exigir 2+ espacios dejaba estos
    # dos campos vacíos al leer sin poppler.
    m = re.search(r"^[ \t]*Marca:[ \t]+([^\n]+)", texto, re.IGNORECASE | re.MULTILINE)
    datos["marca"] = _primera_columna(m.group(1)) if m else ""

    m = re.search(r"^[ \t]*Veh[íi]culo:[ \t]+([^\n]+)", texto, re.IGNORECASE | re.MULTILINE)
    datos["vehiculo"] = _primera_columna(m.group(1)) if m else ""

    m = re.search(r"Modelo:\s*(\d{4})", texto, re.IGNORECASE)
    datos["modelo_anio"] = m.group(1).strip() if m else ""

    m = re.search(r"Precio de venta \(con IVA\):\s*(\$\s*[\d,]+\.?\d*)", texto, re.IGNORECASE)
    datos["precio_venta_iva"] = extraer_monto(m.group(1)) if m else ""

    m = re.search(r"Enganche\*?:\s*[\d.]+%\s*(\$\s*[\d,]+\.?\d*)", texto, re.IGNORECASE)
    datos["enganche"] = extraer_monto(m.group(1)) if m else ""

    # GAP (monto financiado o de contado, dentro de FINANCIAMIENTO)
    m = re.search(r"GAP:\s*(\$\s*[\d,]+\.?\d*)", texto, re.IGNORECASE)
    gap_raw = m.group(1) if m else ""
    datos["gap_monto"] = extraer_monto(gap_raw) if gap_raw else "$0"
    datos["tiene_gap"] = "SI" if extraer_monto_float(gap_raw) > 0 else "NO"

    m = re.search(r"Plazo:\s*(\d+)\s*meses", texto, re.IGNORECASE)
    datos["plazo_meses"] = m.group(1).strip() if m else ""

    m = re.search(
        r"Tasa de Inter[eé]s \(en t[eé]rminos anuales simples\):\s*([\d.]+%)",
        texto, re.IGNORECASE
    )
    datos["tasa_interes_anual"] = m.group(1).strip() if m else ""

    m = re.search(r"Monto total a financiar:\s*(\$\s*[\d,]+\.?\d*)", texto, re.IGNORECASE)
    datos["monto_total_financiar"] = extraer_monto(m.group(1)) if m else ""

    m_min = re.search(
        r"Mensualidad con seguro primer a[ñn]o \(meses 1-12\):\s*(\$\s*[\d,]+\.?\d*)",
        texto, re.IGNORECASE
    )
    m_max = re.search(
        r"Mensualidad con seguro resto del plazo\s+(\$\s*[\d,]+\.?\d*)",
        texto, re.IGNORECASE
    )

    datos["mensualidad_minima"] = extraer_monto(m_min.group(1)) if m_min else ""
    datos["mensualidad_maxima"] = extraer_monto(m_max.group(1)) if m_max else ""

    # Tipo de seguro (Contado Anual / Multianual Financiado / Multianual Fraccionado)
    m = re.search(r"\bTipo:\s*([^\n]+)", texto, re.IGNORECASE)
    datos["tipo_seguro"] = normalizar_tipo_seguro(m.group(1)) if m else ""

    # Aseguradora (texto libre, ej. INBURSA)
    m = re.search(r"Aseguradora:\s*([^\n]+)", texto, re.IGNORECASE)
    datos["aseguradora"] = limpiar(m.group(1)) if m else ""

    # Accesorios: SI/NO según el monto "Accesorios (10% máximo)"
    m = re.search(
        r"Accesorios\s*\(10%\s*m[aá]ximo\):\s*(\$\s*[\d,]+\.?\d*)",
        texto, re.IGNORECASE
    )
    accesorios_raw = m.group(1) if m else ""
    datos["tiene_accesorios"] = "SI" if extraer_monto_float(accesorios_raw) > 0 else "NO"

    # Garantía extendida: SI/NO según el monto
    m = re.search(r"Garant[ií]a extendida:\s*(\$\s*[\d,]+\.?\d*)", texto, re.IGNORECASE)
    garantia_raw = m.group(1) if m else ""
    datos["tiene_garantia_extendida"] = "SI" if extraer_monto_float(garantia_raw) > 0 else "NO"

    return datos


def procesar_carpeta(carpeta_pdf: str, status: str) -> list:
    archivos = glob.glob(os.path.join(carpeta_pdf, "*.pdf"))
    solicitudes_raw    = [f for f in archivos if "solicitud"    in os.path.basename(f).lower()]
    amortizaciones_raw = [f for f in archivos if "amortizacion" in os.path.basename(f).lower()]

    print(f"\n  ── STATUS: {status} ──")
    print(f"  Solicitudes encontradas   : {len(solicitudes_raw)}")
    print(f"  Amortizaciones encontradas: {len(amortizaciones_raw)}")

    dict_solicitudes = {}
    for ruta in solicitudes_raw:
        datos = parsear_solicitud(extraer_texto_pdf(ruta))
        folio = datos.get("folio_cck", "")
        if folio:
            dict_solicitudes[folio] = datos
            print(f"  ✔ Solicitud  [{folio}] → {datos.get('nombre_completo', 'N/D')}")
        else:
            print(f"  ⚠ No se encontró Folio CCK en: {os.path.basename(ruta)}")

    dict_amortizaciones = {}
    for ruta in amortizaciones_raw:
        datos = parsear_amortizacion(extraer_texto_pdf(ruta))
        folio = datos.get("folio_cck", "")
        if folio:
            dict_amortizaciones[folio] = datos
            print(f"  ✔ Amortización [{folio}] → {datos.get('vehiculo', 'N/D')} {datos.get('modelo_anio', '')}")
        else:
            print(f"  ⚠ No se encontró Folio CCK en: {os.path.basename(ruta)}")

    registros = []
    todos_los_folios = sorted(set(dict_solicitudes) | set(dict_amortizaciones))

    for folio in todos_los_folios:
        sol = dict_solicitudes.get(folio, {})
        amo = dict_amortizaciones.get(folio, {})

        registro = {
            "Folio CCK":               folio,
            "STATUS":                  status,
            "Nombre Completo":         sol.get("nombre_completo", ""),
            "Fecha de Nacimiento":     sol.get("fecha_nacimiento", ""),
            "Teléfono Móvil":          sol.get("telefono_movil", ""),
            "Correo Electrónico":      sol.get("correo_electronico", ""),
            "Nombre del Vendedor":     sol.get("nombre_vendedor", ""),
            "Marca":                   amo.get("marca", ""),
            "Vehículo":                amo.get("vehiculo", ""),
            "Año Modelo":              amo.get("modelo_anio", ""),
            "Accesorios":              amo.get("tiene_accesorios", "NO"),
            "Tipo de Seguro":          amo.get("tipo_seguro", ""),
            "Aseguradora":             amo.get("aseguradora", ""),
            "Precio Venta (c/IVA)":    amo.get("precio_venta_iva", ""),
            "Enganche":                amo.get("enganche", ""),
            "¿Tiene GAP?":            amo.get("tiene_gap", "NO"),
            "Monto GAP":               amo.get("gap_monto", ""),
            "Garantía Extendida":      amo.get("tiene_garantia_extendida", "NO"),
            "Plazo (meses)":           amo.get("plazo_meses", ""),
            "Tasa Interés Anual":      amo.get("tasa_interes_anual", ""),
            "Monto Total a Financiar": amo.get("monto_total_financiar", ""),
            "Mensualidad Mínima":      amo.get("mensualidad_minima", ""),
            "Mensualidad Máxima":      amo.get("mensualidad_maxima", ""),
        }
        registros.append(registro)

        estado_sol = "✔" if folio in dict_solicitudes else "✘ SIN SOLICITUD"
        estado_amo = "✔" if folio in dict_amortizaciones else "✘ SIN AMORTIZACIÓN"
        print(f"  [{folio}] Sol:{estado_sol}  Amor:{estado_amo}  — {registro['Nombre Completo']}")

    return registros



# =======================================================================
# FUNCIÓN PRINCIPAL — punto de entrada para la app (reemplaza a la celda
# "▶️ PROCESAR ZIP DEL MES" del notebook original)
# =======================================================================
def procesar_zip_a_excel(ruta_zip: str, nombre_base: str = None,
                          carpeta_salida: str = ".", limpiar_temporal: bool = True) -> str:
    """
    Recibe la ruta de un ZIP (con la misma estructura de siempre: una
    subcarpeta por STATUS, cada una con sus PDFs de solicitud/amortización)
    y devuelve la ruta del archivo Excel de la bitácora ya generado.

    nombre_base: nombre a usar para el archivo/hoja de salida. Si no se
        indica, se toma del nombre del ZIP (igual que en el notebook).
    carpeta_salida: carpeta donde se guarda el Excel resultante.
    limpiar_temporal: si True, borra los PDFs extraídos al terminar
        (el ZIP de entrada NO se borra, a diferencia del notebook original,
        porque aquí lo maneja Streamlit).
    """
    nombre_base = nombre_base or Path(ruta_zip).stem
    carpeta_trabajo = os.path.join(
        os.path.dirname(carpeta_salida) or ".", f"_extraido_{nombre_base}"
    )
    fecha_proceso = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(carpeta_salida, exist_ok=True)
    archivo_salida = os.path.join(
        carpeta_salida, f"{nombre_base}_{fecha_proceso}_BITACORA.xlsx"
    )

    print(f"\n{'='*60}")
    print(f"   RELACIÓN DE CLIENTES — MG COLIMA ({nombre_base})")
    print(f"{'='*60}")

    carpeta_raiz = extraer_zip(ruta_zip, carpeta_trabajo)

    # El nombre de la hoja se toma del mes del ZIP: si el ZIP trae una
    # carpeta raíz envolvente (ej. 'JUNIO/Aprobados/...') se usa el nombre
    # de esa carpeta; si no, se usa el nombre del archivo ZIP.
    fuente_nombre_mes = (
        os.path.basename(carpeta_raiz)
        if os.path.normpath(carpeta_raiz) != os.path.normpath(carpeta_trabajo)
        else nombre_base
    )
    nombre_hoja = detectar_mes_anio(fuente_nombre_mes)

    carpetas_status = detectar_carpetas_status(carpeta_raiz)

    if not carpetas_status:
        raise RuntimeError("No se encontraron subcarpetas de estatus dentro del ZIP.")

    print(f"\n  Carpetas de estatus detectadas: {list(carpetas_status.values())}")

    registros_totales = []
    for nombre_carpeta, status in carpetas_status.items():
        registros_totales.extend(
            procesar_carpeta(os.path.join(carpeta_raiz, nombre_carpeta), status)
        )

    df = pd.DataFrame(registros_totales)

    # --- Exportar a Excel (con formato de encabezado, igual que el original) ---
    from openpyxl.styles import PatternFill, Font, Alignment

    with pd.ExcelWriter(archivo_salida, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=nombre_hoja)
        ws = writer.sheets[nombre_hoja]

        for col in ws.columns:
            max_len = max(
                len(str(cell.value)) if cell.value else 0
                for cell in col
            )
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 45)

        header_fill = PatternFill("solid", fgColor="CC0000")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill      = header_fill
            cell.font      = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.row_dimensions[1].height = 35
        ws.freeze_panes = "A2"

    if limpiar_temporal:
        shutil.rmtree(carpeta_trabajo, ignore_errors=True)

    print(f"\n{'='*60}")
    print(f"  Reporte generado: {archivo_salida}")
    print(f"  Total de clientes : {len(registros_totales)}")
    print(f"  Fecha de proceso  : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*60}")

    return archivo_salida
