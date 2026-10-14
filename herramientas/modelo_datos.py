# -*- coding: utf-8 -*-
"""MODELO DE DATOS DE LA BITÁCORA (esquema estrella)

Junta las bitácoras mensuales en una sola base histórica, ordenada como
un modelo de datos que se puede cargar en Power BI, en Power Pivot de
Excel o consultar desde Python sin volver a leer hoja por hoja.

Por qué un esquema estrella
---------------------------
Cada bitácora es una tabla plana: en cada renglón se repite el nombre
completo del vendedor, la versión del vehículo, el estatus escrito a mano...
Al juntar meses, ese texto repetido se vuelve el problema: "FINANCIADOS" y
"FINANCIADO" cuentan como dos estatus, un vendedor escrito distinto cuenta
como dos personas y un folio que cruzó de mes se suma dos veces.

El modelo separa los datos en:

  HECHOS (lo que pasó, con importes)
    hechos_solicitud    una fila por FOLIO. Su último estatus, el mes en
                        que se capturó y los importes de su última versión.
                        Es la tabla para "¿cuántas solicitudes y cuántas se
                        financiaron?" sin contar dos veces los cruces.
    hechos_estatus_mes  una fila por FOLIO y MES: la foto de cada bitácora.
                        Sirve para cuadrar contra los reportes mensuales y
                        para ver cómo avanzó cada folio (Aprobado → Financiado).

  DIMENSIONES (catálogos para filtrar y agrupar)
    dim_mes, dim_vendedor, dim_vehiculo, dim_estatus, dim_cliente

  CALIDAD
    calidad_datos       lo que el modelo detectó y conviene revisar en la
                        bitácora (folios repetidos, fechas inválidas...).

Datos personales
----------------
El modelo NO guarda nombre, teléfono ni correo del cliente. Cada cliente se
identifica con una clave seudónima (id_cliente) calculada a partir de su
nombre y fecha de nacimiento, que permite saber si la misma persona volvió a
solicitar sin exponer quién es. De la fecha de nacimiento solo queda la
edad al momento de la solicitud y su rango.

Uso
---
    from herramientas import modelo_datos as md
    modelo = md.construir_modelo_desde_archivos(["JUNIO.xlsx", "JULIO.xlsx"])
    modelo["hechos_solicitud"].head()

El modelo se reconstruye completo cada vez con todos los meses que se le
den, así que las claves (id_vendedor, id_vehiculo) son consistentes dentro
de un mismo archivo generado. Para agregar un mes nuevo se vuelve a generar
con todos los meses.
"""

import hashlib
import os
import re
import unicodedata
from datetime import date
try:
    from . import fechas as _fechas   # hora de México, no la del servidor
except ImportError:  # ejecución suelta (Colab)
    import fechas as _fechas

import numpy as np
import pandas as pd

try:
    from . import estatus as _est
except ImportError:  # ejecución directa en Colab
    import estatus as _est


# =======================================================================
# 1) CONSTANTES
# =======================================================================
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Columnas de la bitácora tal como las exporta el sistema.
C_FOLIO = "Folio CCK"
C_STATUS = "STATUS"
C_NOMBRE = "Nombre Completo"
C_NACIMIENTO = "Fecha de Nacimiento"
C_VENDEDOR = "Nombre del Vendedor"
C_VEHICULO = "Vehículo"
C_ANIO = "Año Modelo"

# columna de la bitácora -> columna del modelo
COLUMNAS_MONEDA = {
    "Precio Venta (c/IVA)": "precio_venta",
    "Enganche": "enganche",
    "Monto GAP": "monto_gap",
    "Monto Total a Financiar": "monto_financiar",
    "Mensualidad Mínima": "mensualidad_min",
    "Mensualidad Máxima": "mensualidad_max",
}
# Columnas que el sistema fue agregando con el tiempo (agosto y septiembre
# 2026). En los meses que no las traen quedan como "SIN DATO", no vacías,
# para que en un filtro se distinga "no se capturaba" de "NO".
COLUMNAS_TEXTO_OPCIONALES = {
    "Tipo de Persona": "tipo_persona",
    "Aseguradora": "aseguradora",
    "Tipo de Seguro": "tipo_seguro",
    "Garantía Extendida": "garantia_extendida",
    "Accesorios": "accesorios",
}
SIN_DATO = "SIN DATO"

# Datos de contacto que nunca pasan al modelo.
COLUMNAS_PERSONALES = [C_NOMBRE, C_NACIMIENTO, "Teléfono Móvil", "Correo Electrónico"]

RANGOS_ENGANCHE = [(0.00, 0.20, "Menos de 20%"), (0.20, 0.30, "20% a 29%"),
                   (0.30, 0.40, "30% a 39%"), (0.40, 9.99, "40% o más")]
RANGOS_EDAD = [(18, 26, "18 a 25"), (26, 36, "26 a 35"), (36, 46, "36 a 45"),
               (46, 56, "46 a 55"), (56, 66, "56 a 65"), (66, 120, "66 o más")]

# Líneas de MG que se reconocen en el texto de la versión.
_LINEAS = ["MG3", "MG4", "MG5", "MG7", "ZS", "HS", "RX5", "RX8", "RX9", "GT",
           "ONE", "CYBERSTER"]
_TRANSMISIONES = ["CVT", "DCT", "AT", "MT"]

NOMBRE_GRUPO = {
    _est.CERRADA_POSITIVA: "Cerrada positiva",
    _est.ABIERTA: "Abierta",
    _est.CERRADA_NEGATIVA: "Cerrada negativa",
}


# =======================================================================
# 2) UTILIDADES DE LIMPIEZA
# =======================================================================
def _sin_acentos(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _texto(valor):
    """Texto limpio en mayúsculas, o None si la celda viene vacía."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    t = re.sub(r"\s+", " ", str(valor)).strip()
    return None if t.upper() in ("", "NAN", "NONE", "NAT") else t.upper()


def _moneda(valor):
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return np.nan
    if isinstance(valor, (int, float, np.number)):
        return float(valor)
    t = str(valor).replace("$", "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return np.nan


def _tasa(valor):
    """'18.99%', 18.99 o 0.1899 -> 0.1899 (fracción, para formato %)."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return np.nan
    if isinstance(valor, str):
        t = valor.replace("%", "").strip()
        try:
            n = float(t)
        except ValueError:
            return np.nan
    else:
        n = float(valor)
    return n / 100 if n > 1 else n


def _fecha(valor):
    """Fecha de nacimiento. La bitácora la trae como texto dd/mm/aaaa y a
    veces como fecha de Excel; las dos se leen igual."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return pd.NaT
    if isinstance(valor, (pd.Timestamp, date)):
        return pd.Timestamp(valor)
    return pd.to_datetime(str(valor).strip(), dayfirst=True, errors="coerce")


def normalizar_folio(valor):
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    t = str(valor).strip()
    if t.endswith(".0"):
        t = t[:-2]
    return t or None


def nombre_titulo(nombre):
    t = _texto(nombre)
    return t.title() if t else None


def nombre_corto(nombre):
    """'Jessica Elizabeth Machuca Roque' -> 'Jessica Elizabeth M. R.'"""
    if not nombre:
        return nombre
    partes = str(nombre).split()
    if len(partes) <= 2:
        return nombre
    return " ".join(partes[:2] + [f"{p[0]}." for p in partes[2:]])


def es_persona(nombre):
    """Mismo criterio que los reportes: un asesor tiene nombre y apellido.
    'Casa' o 'Gerencia' son capturas genéricas."""
    return len(str(nombre or "").split()) >= 2


def _rango(valor, rangos):
    if valor is None or pd.isna(valor):
        return SIN_DATO
    for desde, hasta, etiqueta in rangos:
        if desde <= valor < hasta:
            return etiqueta
    return SIN_DATO


def descomponer_vehiculo(version):
    """'NEW ZS 1.5T COM TURBO EXCITE AT' -> ('ZS', 'AT', 'NO')."""
    t = _texto(version) or ""
    palabras = re.findall(r"[A-Z0-9]+", t)
    linea = next((p for p in palabras if p in _LINEAS), "OTRO" if t else SIN_DATO)
    transmision = next((p for p in palabras if p in _TRANSMISIONES), SIN_DATO)
    hibrido = "SI" if any(p in ("HEV", "PHEV", "EV") for p in palabras) else "NO"
    return linea, transmision, hibrido


def clave_cliente(nombre, nacimiento):
    """Clave seudónima y estable del cliente (no se puede leer el nombre).

    Se calcula con nombre (sin acentos ni espacios dobles) + fecha de
    nacimiento, así la misma persona tiene la misma clave en todos los meses
    aunque la fecha venga como texto en uno y como fecha de Excel en otro.
    """
    n = _sin_acentos(_texto(nombre) or "")
    f = nacimiento.strftime("%Y-%m-%d") if pd.notna(nacimiento) else ""
    if not n:
        return None
    return "C" + hashlib.sha256(f"{n}|{f}".encode("utf-8")).hexdigest()[:10].upper()


# =======================================================================
# 3) PERIODO DE CADA BITÁCORA
# =======================================================================
def interpretar_periodo(*textos, anio_defecto=None):
    """Busca mes y año en la etiqueta de la hoja o en el nombre del archivo.

    'SEPTIEMBRE 2026' -> (2026, 9). Si ningún texto trae el año se usa
    anio_defecto (o el año actual) y se avisa en la hoja de calidad.
    Devuelve (anio, mes, anio_supuesto).
    """
    mes = anio = None
    for texto in textos:
        t = _sin_acentos(str(texto or "")).lower()
        if mes is None:
            for i, nombre in enumerate(MESES_ES):
                if nombre in t:
                    mes = i + 1
                    break
        if anio is None:
            m = re.search(r"(20\d{2})", t)
            if m:
                anio = int(m.group(1))
    supuesto = anio is None
    if anio is None:
        anio = anio_defecto or _fechas.hoy().year
    return anio, mes, supuesto


# =======================================================================
# 4) CARGA
# =======================================================================
def cargar_bitacoras(rutas, etiquetas=None):
    """Lee la primera hoja de cada Excel. Devuelve [(etiqueta, ruta, df)].

    etiquetas: opcional, una por archivo (ej. ["JUNIO 2026", ...]). Si no se
    da, se usa el nombre de la hoja; si la hoja no dice el mes, el nombre
    del archivo.
    """
    if etiquetas and len(etiquetas) != len(rutas):
        etiquetas = None
    resultado = []
    for i, ruta in enumerate(rutas):
        xls = pd.ExcelFile(ruta)
        hoja = xls.sheet_names[0]
        df = pd.read_excel(ruta, sheet_name=hoja)
        df.columns = [str(c).strip() for c in df.columns]
        etiqueta = etiquetas[i] if etiquetas else hoja
        resultado.append((str(etiqueta).strip(), os.path.basename(ruta), df))
    return resultado


# =======================================================================
# 5) CONSTRUCCIÓN DEL MODELO
# =======================================================================
def _filas_limpias(etiqueta, archivo, df, calidad):
    """Convierte una bitácora en filas normalizadas (todavía con nombre del
    cliente; se descarta al armar las tablas finales)."""
    anio, mes, supuesto = interpretar_periodo(etiqueta, archivo)
    if mes is None:
        raise ValueError(
            f"No se reconoce el mes de '{archivo}' (hoja '{etiqueta}'). "
            "Nombra la hoja como 'SEPTIEMBRE 2026' o escribe la etiqueta del mes.")
    id_mes = anio * 100 + mes
    if supuesto:
        calidad.append(("Periodo", None, id_mes,
                        f"'{archivo}' no indica el año; se supuso {anio}."))

    faltantes = [c for c in (C_FOLIO, C_STATUS, C_VENDEDOR) if c not in df.columns]
    if faltantes:
        raise ValueError(f"A '{archivo}' le faltan columnas indispensables: {faltantes}")
    # Columnas que el sistema agregó después: no es un error, pero explica
    # por qué esos meses salen como "SIN DATO" en los filtros.
    ausentes = [c for c in COLUMNAS_TEXTO_OPCIONALES if c not in df.columns]
    if ausentes:
        calidad.append(("Columnas que no existían", None, id_mes,
                        f"'{archivo}' no trae: {', '.join(ausentes)}. Quedan como '{SIN_DATO}'."))

    filas = []
    for pos, (_, r) in enumerate(df.iterrows()):
        # Renglones totalmente vacíos al final del Excel.
        if all(_texto(v) is None for v in r.values):
            continue
        folio = normalizar_folio(r.get(C_FOLIO))
        if folio is None:
            folio = f"SIN-FOLIO-{id_mes}-{pos + 1}"
            calidad.append(("Folio vacío", folio, id_mes,
                            f"Renglón {pos + 2} de '{archivo}' sin folio; se le asignó una clave provisional."))

        status_crudo = _texto(r.get(C_STATUS))
        nacimiento = _fecha(r.get(C_NACIMIENTO)) if C_NACIMIENTO in df.columns else pd.NaT
        if C_NACIMIENTO in df.columns and pd.isna(nacimiento) and _texto(r.get(C_NACIMIENTO)):
            calidad.append(("Fecha de nacimiento", folio, id_mes,
                            f"No se pudo leer '{r.get(C_NACIMIENTO)}'."))

        fila = {
            "folio": folio,
            "id_mes": id_mes,
            "_pos": pos,
            "_archivo": archivo,
            "status_original": status_crudo or "",
            "clave_estatus": _est.clasificar_status(status_crudo or ""),
            "vendedor": nombre_titulo(r.get(C_VENDEDOR)) or "Sin Vendedor",
            "version": _texto(r.get(C_VEHICULO)) or SIN_DATO,
            "anio_modelo": pd.to_numeric(r.get(C_ANIO), errors="coerce"),
            "_nombre": r.get(C_NOMBRE),
            "_nacimiento": nacimiento,
            "tiene_gap": 1 if (_texto(r.get("¿Tiene GAP?")) or "") in ("SI", "SÍ", "S", "X") else 0,
            "plazo_meses": pd.to_numeric(r.get("Plazo (meses)"), errors="coerce"),
            "tasa_anual": _tasa(r.get("Tasa Interés Anual")),
        }
        for origen, destino in COLUMNAS_MONEDA.items():
            fila[destino] = _moneda(r.get(origen))
        for origen, destino in COLUMNAS_TEXTO_OPCIONALES.items():
            fila[destino] = (_texto(r.get(origen)) or SIN_DATO) if origen in df.columns else SIN_DATO
        filas.append(fila)
    return filas


def _revisar_valores(h, calidad):
    """Reglas de negocio sencillas que delatan errores de captura."""
    for _, r in h.iterrows():
        if pd.notna(r.precio_venta) and pd.notna(r.enganche) and r.enganche > r.precio_venta:
            calidad.append(("Enganche mayor al precio", r.folio, r.id_mes_captura,
                            f"Enganche ${r.enganche:,.0f} contra precio ${r.precio_venta:,.0f}."))
        if pd.notna(r.tasa_anual) and not (0.05 <= r.tasa_anual <= 0.40):
            calidad.append(("Tasa fuera de rango", r.folio, r.id_mes_captura,
                            f"Tasa anual de {r.tasa_anual:.2%}."))
        if pd.notna(r.edad_cliente) and not (18 <= r.edad_cliente <= 90) and r.tipo_persona != "MORAL":
            calidad.append(("Edad fuera de rango", r.folio, r.id_mes_captura,
                            f"Edad calculada de {r.edad_cliente:.0f} años; revisar fecha de nacimiento."))
        if r.tiene_gap == 1 and not (pd.notna(r.monto_gap) and r.monto_gap > 0):
            calidad.append(("GAP sin monto", r.folio, r.id_mes_captura,
                            "Marcado con GAP pero sin monto de GAP."))


def construir_modelo(bitacoras):
    """bitacoras: [(etiqueta_mes, nombre_archivo, df_crudo)] -> dict de tablas."""
    calidad = []
    filas = []
    for etiqueta, archivo, df in bitacoras:
        filas.extend(_filas_limpias(etiqueta, archivo, df, calidad))
    if not filas:
        raise ValueError("Las bitácoras no traen ninguna solicitud.")

    base = pd.DataFrame(filas)

    # Dos archivos del mismo mes: se avisa (se tratarían como un solo mes).
    meses_archivo = base.groupby("id_mes")["_archivo"].nunique()
    for id_mes, n in meses_archivo[meses_archivo > 1].items():
        archivos = sorted(base.loc[base.id_mes == id_mes, "_archivo"].unique())
        calidad.append(("Mes duplicado", None, int(id_mes),
                        f"{n} archivos del mismo mes: {', '.join(archivos)}. Se juntaron."))

    # Estatus que no está en el catálogo: se respeta, pero se avisa.
    for clave in sorted(base.clave_estatus.unique()):
        if not _est.esta_catalogado(clave) and clave != _est.CLAVE_SIN_ESTATUS:
            calidad.append(("Estatus no catalogado", None, None,
                            f"'{clave}' no está en estatus.py; se tomó como estatus propio."))
    _est.registrar_categorias(base.clave_estatus.unique())

    # Un folio dos veces en el mismo mes: se conserva el último renglón.
    base = base.sort_values(["id_mes", "_archivo", "_pos"], kind="stable")
    dup = base.duplicated(["folio", "id_mes"], keep="last")
    for _, r in base[dup].iterrows():
        calidad.append(("Folio repetido en el mes", r.folio, int(r.id_mes),
                        "Aparece más de una vez en la misma bitácora; se tomó el último renglón."))
    base = base[~dup].reset_index(drop=True)

    # Seudónimo del cliente y edad al momento de esa bitácora.
    base["id_cliente"] = [clave_cliente(n, f) for n, f in zip(base._nombre, base._nacimiento)]
    fin_mes = pd.to_datetime(base.id_mes.astype(str) + "01", format="%Y%m%d") + pd.offsets.MonthEnd(0)
    base["edad_cliente"] = ((fin_mes - base._nacimiento).dt.days / 365.25).apply(
        lambda d: float(np.floor(d)) if pd.notna(d) else np.nan)
    base.loc[base.tipo_persona == "MORAL", "edad_cliente"] = np.nan

    # ------------------------------------------------------------- dim_mes
    meses = sorted(base.id_mes.unique())
    dim_mes = pd.DataFrame({
        "id_mes": meses,
        "anio": [m // 100 for m in meses],
        "num_mes": [m % 100 for m in meses],
        "mes": [MESES_ES[m % 100 - 1].title() for m in meses],
        "mes_anio": [f"{MESES_ES[m % 100 - 1].title()} {m // 100}" for m in meses],
        "mes_corto": [f"{MESES_ES[m % 100 - 1][:3].title()} {str(m // 100)[2:]}" for m in meses],
        "trimestre": [f"T{(m % 100 - 1) // 3 + 1} {m // 100}" for m in meses],
        "fecha_inicio": [pd.Timestamp(year=m // 100, month=m % 100, day=1) for m in meses],
        "orden": range(1, len(meses) + 1),
    })

    # ------------------------------------------------------- dim_vendedor
    vend = (base.groupby("vendedor").agg(primer_mes=("id_mes", "min"), ultimo_mes=("id_mes", "max"))
            .reset_index().sort_values("vendedor").reset_index(drop=True))
    vend.insert(0, "id_vendedor", [f"V{i:03d}" for i in range(1, len(vend) + 1)])
    vend["vendedor_corto"] = vend.vendedor.map(nombre_corto)
    vend["es_persona"] = vend.vendedor.map(lambda v: "SI" if es_persona(v) else "NO")
    dim_vendedor = vend[["id_vendedor", "vendedor", "vendedor_corto", "es_persona",
                         "primer_mes", "ultimo_mes"]]
    mapa_vend = dict(zip(vend.vendedor, vend.id_vendedor))
    base["id_vendedor"] = base.vendedor.map(mapa_vend)

    # ------------------------------------------------------- dim_vehiculo
    versiones = sorted(base.version.unique())
    partes = [descomponer_vehiculo(v) for v in versiones]
    dim_vehiculo = pd.DataFrame({
        "id_vehiculo": [f"H{i:03d}" for i in range(1, len(versiones) + 1)],
        "version": versiones,
        "linea": [p[0] for p in partes],
        "transmision": [p[1] for p in partes],
        "hibrido": [p[2] for p in partes],
    })
    base["id_vehiculo"] = base.version.map(dict(zip(dim_vehiculo.version, dim_vehiculo.id_vehiculo)))

    # -------------------------------------------------------- dim_estatus
    # Todo el catálogo (no solo lo presente) para que un estatus nuevo en un
    # mes futuro ya tenga su renglón, más los no catalogados que aparecieron.
    _est.asignar_colores(base.clave_estatus)
    claves = list(_est.ORDEN_CATEGORIAS)
    if _est.CLAVE_SIN_ESTATUS not in claves:
        claves.append(_est.CLAVE_SIN_ESTATUS)
    grupos = [_est.GRUPO_CATEGORIA.get(c, _est.ABIERTA) for c in claves]
    dim_estatus = pd.DataFrame({
        "clave_estatus": claves,
        "estatus": [_est.etiqueta(c) for c in claves],
        "grupo": [NOMBRE_GRUPO.get(g, g) for g in grupos],
        "es_financiado": [1 if c == "FINANCIADO" else 0 for c in claves],
        "es_cerrada": [0 if g == _est.ABIERTA else 1 for g in grupos],
        "orden": range(1, len(claves) + 1),
        "color": [_est.COLOR_CATEGORIA.get(c, "") for c in claves],
        "presente_en_datos": ["SI" if c in set(base.clave_estatus) else "NO" for c in claves],
    })

    # -------------------------------------------------- hechos_estatus_mes
    base = base.sort_values(["folio", "id_mes"], kind="stable").reset_index(drop=True)
    g = base.groupby("folio", sort=False)
    base["es_captura"] = (g.cumcount() == 0).astype(int)
    base["es_ultimo"] = (g.cumcount(ascending=False) == 0).astype(int)
    base["estatus_anterior"] = g.clave_estatus.shift(1).fillna("")
    base["cambio_estatus"] = ((base.estatus_anterior != "") &
                              (base.estatus_anterior != base.clave_estatus)).astype(int)
    hechos_estatus_mes = base[[
        "id_mes", "folio", "clave_estatus", "status_original", "estatus_anterior",
        "cambio_estatus", "es_captura", "es_ultimo", "id_vendedor", "id_vehiculo",
        "monto_financiar", "tiene_gap",
    ]].sort_values(["id_mes", "folio"]).reset_index(drop=True)

    # --------------------------------------------------- hechos_solicitud
    primero = base[base.es_captura == 1].set_index("folio")
    ultimo = base[base.es_ultimo == 1].set_index("folio")
    n_meses = g.id_mes.nunique()

    h = ultimo.copy()
    h["id_mes_captura"] = primero.id_mes
    h["id_mes_ultimo"] = ultimo.id_mes
    h["estatus_captura"] = primero.clave_estatus
    h["estatus_final"] = ultimo.clave_estatus
    h["meses_en_bitacora"] = n_meses
    h["cruzo_mes"] = (n_meses > 1).astype(int)
    h["edad_cliente"] = primero.edad_cliente     # edad cuando se capturó
    grupo_final = h.estatus_final.map(lambda c: _est.GRUPO_CATEGORIA.get(c, _est.ABIERTA))
    h["financiado"] = (h.estatus_final == "FINANCIADO").astype(int)
    h["aprobado_o_financiado"] = h.estatus_final.isin(["FINANCIADO", "APROBADO"]).astype(int)
    h["rechazado"] = (h.estatus_final == "RECHAZADO").astype(int)
    h["abierta"] = (grupo_final == _est.ABIERTA).astype(int)

    def _cambios(folio):
        a, b = primero.loc[folio], ultimo.loc[folio]
        cambios = []
        if a.id_vendedor != b.id_vendedor:
            cambios.append("vendedor")
        if a.id_vehiculo != b.id_vehiculo:
            cambios.append("vehículo")
        if not (pd.isna(a.monto_financiar) and pd.isna(b.monto_financiar)) and \
                abs((a.monto_financiar or 0) - (b.monto_financiar or 0)) >= 1:
            cambios.append("monto")
        if a.tiene_gap != b.tiene_gap:
            cambios.append("GAP")
        return ", ".join(cambios)

    h["cambios_al_cruzar"] = [(_cambios(f) if c else "") for f, c in zip(h.index, h.cruzo_mes)]

    h["pct_enganche"] = np.where(h.precio_venta > 0, h.enganche / h.precio_venta, np.nan)
    h["rango_enganche"] = h.pct_enganche.map(lambda v: _rango(v, RANGOS_ENGANCHE))
    h["rango_edad"] = h.edad_cliente.map(lambda v: _rango(v, RANGOS_EDAD))
    h.loc[h.tipo_persona == "MORAL", "rango_edad"] = "Persona moral"

    # Recaptura: la misma persona ya tenía un folio en un mes anterior.
    h = h.reset_index()
    h = h.sort_values(["id_mes_captura", "folio"]).reset_index(drop=True)
    h["solicitud_num_cliente"] = h.groupby("id_cliente", dropna=False).cumcount() + 1
    h.loc[h.id_cliente.isna(), "solicitud_num_cliente"] = 1
    h["es_recaptura"] = (h.solicitud_num_cliente > 1).astype(int)

    _revisar_valores(h, calidad)

    hechos_solicitud = h[[
        "folio", "id_mes_captura", "id_mes_ultimo", "meses_en_bitacora", "cruzo_mes",
        "cambios_al_cruzar", "estatus_captura", "estatus_final", "financiado",
        "aprobado_o_financiado", "rechazado", "abierta", "id_vendedor", "id_vehiculo",
        "anio_modelo", "id_cliente", "solicitud_num_cliente", "es_recaptura",
        "tipo_persona", "edad_cliente", "rango_edad", "precio_venta", "enganche",
        "pct_enganche", "rango_enganche", "monto_financiar", "plazo_meses",
        "tasa_anual", "mensualidad_min", "mensualidad_max", "tiene_gap", "monto_gap",
        "aseguradora", "tipo_seguro", "garantia_extendida", "accesorios",
    ]].reset_index(drop=True)

    # -------------------------------------------------------- dim_cliente
    cli = h[h.id_cliente.notna()]
    dim_cliente = (cli.groupby("id_cliente")
                   .agg(tipo_persona=("tipo_persona", "last"),
                        rango_edad=("rango_edad", "first"),
                        primer_mes=("id_mes_captura", "min"),
                        solicitudes=("folio", "nunique"),
                        financiadas=("financiado", "sum"))
                   .reset_index())

    # ------------------------------------------------------ calidad_datos
    calidad_datos = pd.DataFrame(calidad, columns=["tipo", "folio", "id_mes", "detalle"])

    return {
        "hechos_solicitud": hechos_solicitud,
        "hechos_estatus_mes": hechos_estatus_mes,
        "dim_mes": dim_mes,
        "dim_vendedor": dim_vendedor,
        "dim_vehiculo": dim_vehiculo,
        "dim_estatus": dim_estatus,
        "dim_cliente": dim_cliente,
        "calidad_datos": calidad_datos,
    }


def construir_modelo_desde_archivos(rutas, etiquetas=None):
    return construir_modelo(cargar_bitacoras(rutas, etiquetas))


# =======================================================================
# 6) RELACIONES Y DICCIONARIO (los usa el exportador y sirven de documentación)
# =======================================================================
# (tabla, columna, tabla relacionada, columna, activa)
# Todas son "muchos a uno" con filtro en una sola dirección (de la dimensión
# a los hechos). Las inactivas se dejan así para no crear dos caminos entre
# las mismas tablas, que Power BI no permite; se activan en una medida con
# USERELATIONSHIP cuando se necesitan.
RELACIONES = [
    ("hechos_solicitud", "id_mes_captura", "dim_mes", "id_mes", True),
    ("hechos_solicitud", "id_vendedor", "dim_vendedor", "id_vendedor", True),
    ("hechos_solicitud", "id_vehiculo", "dim_vehiculo", "id_vehiculo", True),
    ("hechos_solicitud", "estatus_final", "dim_estatus", "clave_estatus", True),
    ("hechos_solicitud", "id_cliente", "dim_cliente", "id_cliente", True),
    ("hechos_estatus_mes", "id_mes", "dim_mes", "id_mes", True),
    ("hechos_estatus_mes", "id_vendedor", "dim_vendedor", "id_vendedor", True),
    ("hechos_estatus_mes", "id_vehiculo", "dim_vehiculo", "id_vehiculo", True),
    ("hechos_estatus_mes", "clave_estatus", "dim_estatus", "clave_estatus", True),
    ("hechos_solicitud", "id_mes_ultimo", "dim_mes", "id_mes", False),
    ("hechos_estatus_mes", "folio", "hechos_solicitud", "folio", False),
]

DESCRIPCION_TABLAS = {
    "hechos_solicitud": "Una fila por folio. Último estatus, mes de captura e importes de su última versión. "
                        "Úsala para conteos del periodo, conversión y análisis por vendedor, modelo o perfil.",
    "hechos_estatus_mes": "Una fila por folio y mes: la foto de cada bitácora. Cuadra con los reportes "
                          "mensuales y muestra cómo avanzó cada folio entre meses.",
    "dim_mes": "Calendario de los meses cargados.",
    "dim_vendedor": "Asesores. es_persona = NO para capturas genéricas como 'Casa'.",
    "dim_vehiculo": "Versiones tal como vienen en la bitácora, con línea, transmisión e híbrido.",
    "dim_estatus": "Catálogo completo de estatus (estatus.py) con su grupo y color de reporte.",
    "dim_cliente": "Clientes seudónimos: sin nombre ni contacto. Permite ver recapturas.",
    "calidad_datos": "Lo que conviene revisar en las bitácoras de origen.",
}

DICCIONARIO = {
    "folio": "Folio CCK de la solicitud (clave de hechos_solicitud).",
    "id_mes": "Mes como número AAAAMM (202609 = septiembre 2026).",
    "id_mes_captura": "Primer mes en que aparece el folio. Las solicitudes del periodo se cuentan aquí.",
    "id_mes_ultimo": "Mes de la bitácora de la que sale el último estatus.",
    "meses_en_bitacora": "En cuántas bitácoras aparece el folio.",
    "cruzo_mes": "1 si el folio aparece en más de un mes (ej. aprobado en junio, financiado en julio).",
    "cambios_al_cruzar": "Qué cambió entre la captura y el último estatus: vendedor, vehículo, monto, GAP.",
    "estatus_captura": "Estatus con el que se capturó.",
    "estatus_final": "Último estatus conocido (clave de dim_estatus).",
    "clave_estatus": "Estatus normalizado con el catálogo de estatus.py.",
    "status_original": "Estatus tal como se escribió en la bitácora.",
    "estatus_anterior": "Estatus del mismo folio en su aparición anterior (vacío si es la primera).",
    "cambio_estatus": "1 si el estatus cambió respecto a la aparición anterior.",
    "es_captura": "1 en la primera aparición del folio.",
    "es_ultimo": "1 en la aparición que define el estatus final. Filtrar es_ultimo = 1 equivale a hechos_solicitud.",
    "financiado": "1 si el estatus final es FINANCIADO. Sumarlo da financiados; promediarlo da conversión.",
    "aprobado_o_financiado": "1 si terminó APROBADO o FINANCIADO.",
    "rechazado": "1 si el estatus final es RECHAZADO.",
    "abierta": "1 si el estatus final sigue abierto (aprobado, contrapropuesta, en proceso...).",
    "id_vendedor": "Clave del asesor (dim_vendedor).",
    "id_vehiculo": "Clave de la versión (dim_vehiculo).",
    "anio_modelo": "Año modelo del vehículo.",
    "id_cliente": "Clave seudónima del cliente (no permite leer su nombre).",
    "solicitud_num_cliente": "1 = primera solicitud de ese cliente en el histórico, 2 = segunda...",
    "es_recaptura": "1 si el cliente ya tenía otro folio en un mes anterior.",
    "tipo_persona": "FÍSICA / MORAL. 'SIN DATO' en meses en que no se capturaba.",
    "edad_cliente": "Edad en años al cierre del mes de captura.",
    "rango_edad": "Rango de edad del cliente.",
    "precio_venta": "Precio de venta con IVA.",
    "enganche": "Enganche en pesos.",
    "pct_enganche": "Enganche / precio de venta.",
    "rango_enganche": "Rango del porcentaje de enganche.",
    "monto_financiar": "Monto total a financiar.",
    "plazo_meses": "Plazo del crédito en meses.",
    "tasa_anual": "Tasa de interés anual (fracción: 0.1899 = 18.99%).",
    "mensualidad_min": "Mensualidad mínima.",
    "mensualidad_max": "Mensualidad máxima.",
    "tiene_gap": "1 si la solicitud lleva seguro GAP.",
    "monto_gap": "Monto del seguro GAP.",
    "aseguradora": "Aseguradora del seguro de auto.",
    "tipo_seguro": "Contado anual / multianual fraccionado.",
    "garantia_extendida": "SI / NO.",
    "accesorios": "SI / NO.",
}
