"""Validar recibos de nómina (CFDI) ante el SAT y revisar su vigencia.

Qué hace
--------
1. Lee cada recibo (PDF o XML; también dentro de un ZIP): folio fiscal,
   RFC emisor y receptor, periodo, percepciones brutas y total del CFDI.
2. Consulta su estatus en el servicio oficial del SAT (ConsultaCFDIService,
   el mismo que usa verificacfdi.facturaelectronica.sat.gob.mx, sin captcha).
3. Por persona: toma los recibos de los 2 meses más recientes según la
   frecuencia (8 semanales, 4 quincenales o 2 mensuales), suma el ingreso
   bruto de cada mes y toma el MES MÁS BAJO como ingreso mensual.
4. Vigencia: el último recibo vale hasta 10 días hábiles después de que
   termina el PERIODO SIGUIENTE (la nómina que ya debió timbrarse). Mientras
   esa nómina no se paga, no se exige (ver guía de crédito, F31 y C1).

Códigos del SAT (comprobados con pruebas controladas)
-----------------------------------------------------
  S          -> el CFDI existe con esos datos (Vigente o Cancelado).
  N - 602    -> el folio fiscal NO existe en el SAT.
  N - 601    -> el folio SÍ existe, pero el RFC o el TOTAL no coinciden.

Aviso con el IMSS (y otros "tarjetones")
----------------------------------------
El recibo que entrega el IMSS a sus trabajadores muestra un "Líquido" que NO
es el total del CFDI timbrado (ej. tarjetón $9,037.00 contra CFDI $7,431.81,
confirmado en el portal del SAT). Con esos PDF el SAT responde 601 aunque el
recibo sea auténtico: hay que subir el XML, que trae el total exacto.
"""

import calendar
import html
import io
import os
import re
import urllib.request
import zipfile
from datetime import date, timedelta

SAT_URL = "https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc"
SOAP_ACTION = "http://tempuri.org/IConsultaCFDIService/Consulta"
UUID_RE = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
RFC_RE = r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b"
NUM = r"\$?\s*([\d,]+\.\d{2})"
MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
         "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
DIAS_VIGENCIA = 10
INGRESO_MINIMO = 6500.0

ESTADO_OK = "Vigente"
ESTADO_CANCELADO = "Cancelado"
ESTADO_NO_EXISTE = "Folio no existe en el SAT"
ESTADO_NO_COINCIDE = "Folio existe, pero RFC o total no coinciden"
ESTADO_SIN_DATOS = "Sin datos suficientes"
ESTADO_ERROR = "Sin respuesta del SAT"


# ---------------------------------------------------------------------------
# Días hábiles (Ley Federal del Trabajo, art. 74)
# ---------------------------------------------------------------------------
def _lunes(y, mes, n):
    d = date(y, mes, 1)
    return d + timedelta(days=(7 - d.weekday()) % 7 + 7 * (n - 1))


def dias_inhabiles(y):
    dias = {date(y, 1, 1), _lunes(y, 2, 1), _lunes(y, 3, 3), date(y, 5, 1),
            date(y, 9, 16), _lunes(y, 11, 3), date(y, 12, 25)}
    if (y - 2024) % 6 == 0:          # transmisión del Poder Ejecutivo
        dias.add(date(y, 10, 1))
    return dias


def es_habil(d):
    return d.weekday() < 5 and d not in dias_inhabiles(d.year)


def vence(fin_periodo: date, dias=DIAS_VIGENCIA) -> date:
    d, n = fin_periodo, 0
    while n < dias:
        d += timedelta(days=1)
        if es_habil(d):
            n += 1
    return d


def habiles_entre(desde: date, hasta: date) -> int:
    """Días hábiles en (desde, hasta]."""
    n, d = 0, desde
    while d < hasta:
        d += timedelta(days=1)
        n += es_habil(d)
    return n


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def _texto_pdf(datos: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(datos)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _monto(t, etiquetas):
    for e in etiquetas:
        m = re.search(e + r"\s*:?\s*" + NUM, t, re.I)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def leer_periodo(t):
    """(inicio, fin) como date. Formatos: 'Del AAAA-MM-DD al AAAA-MM-DD',
    'Período de pago: 1A-SEP-2026' (1A = 1-15, 2A = 16-fin de mes),
    'Fecha inicial/final de pago' y 'DD/MM/AAAA al DD/MM/AAAA'."""
    m = re.search(r"Del\s+(\d{4}-\d{2}-\d{2})\s+al\s+(\d{4}-\d{2}-\d{2})", t)
    if m:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    m = re.search(r"Per[ií]odo de pago:?\s*([12])A-([A-Z]{3})-(\d{4})", t, re.I)
    if m and m.group(2).upper() in MESES:
        q, mes, y = int(m.group(1)), MESES[m.group(2).upper()], int(m.group(3))
        if q == 1:
            return date(y, mes, 1), date(y, mes, 15)
        return date(y, mes, 16), date(y, mes, calendar.monthrange(y, mes)[1])
    fi = re.search(r"Fecha\s*inicial\s*de\s*pago\D{0,5}(\d{4}-\d{2}-\d{2})", t, re.I)
    ff = re.search(r"Fecha\s*final\s*de\s*pago\D{0,5}(\d{4}-\d{2}-\d{2})", t, re.I)
    if fi and ff:
        return date.fromisoformat(fi.group(1)), date.fromisoformat(ff.group(1))
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*(?:al|a|-)\s*(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        d1, m1, y1, d2, m2, y2 = map(int, m.groups())
        return date(y1, m1, d1), date(y2, m2, d2)
    return None, None


def _ordenar_rfcs(rfcs):
    """Emisor y receptor. Si hay uno de persona moral (12) y uno de persona
    física (13), el de 12 es el patrón; si no, el orden de aparición."""
    if len(rfcs) == 2:
        cortos = [r for r in rfcs if len(r) == 12]
        largos = [r for r in rfcs if len(r) == 13]
        if len(cortos) == 1 and len(largos) == 1:
            return cortos[0], largos[0]
    return (rfcs + [None, None])[:2]


def datos_de_texto(nombre, t):
    plano = t.replace("\n", "")
    uuid = re.search(UUID_RE, t)
    pac = None
    m = re.search(r"\|\|1\.1\|[^|]+\|[^|]+\|([^|]+)\|", plano)   # timbre 1.1 trae RFC del PAC
    if m:
        pac = m.group(1)
    rfcs = [r for r in dict.fromkeys(re.findall(RFC_RE, t)) if r != pac]
    emisor, receptor = _ordenar_rfcs(rfcs)
    ini, fin = leer_periodo(t)
    nombre_receptor = re.search(r"Nombre:\s*([A-ZÁÉÍÓÚÑ ]{6,})\s+(?:Pases|Retardos|Faltas|$)", t)
    return {
        "archivo": nombre,
        "origen": "PDF",
        "uuid": uuid.group(0).upper() if uuid else None,
        "rfc_emisor": emisor,
        "rfc_receptor": receptor,
        "nombre": nombre_receptor.group(1).strip() if nombre_receptor else "",
        "percepciones": _monto(t, [r"Total de Percepciones", r"Total Percepciones", r"Subtotal"]),
        "total": _monto(t, [r"\bTotal:", r"L[ií]quido", r"Neto a pagar", r"Total a pagar", r"Neto del recibo"]),
        "inicio": ini,
        "fin": fin,
    }


def datos_de_xml(nombre, datos: bytes):
    t = datos.decode("utf-8", "ignore")

    def g(pat):
        m = re.search(pat, t)
        return m.group(1) if m else None

    num = lambda pat: float(g(pat)) if g(pat) else None   # noqa: E731
    fi, ff = g(r'FechaInicialPago="([^"]+)"'), g(r'FechaFinalPago="([^"]+)"')
    return {
        "archivo": nombre,
        "origen": "XML",
        "uuid": (g(r'UUID="([^"]+)"') or "").upper() or None,
        "rfc_emisor": g(r'<cfdi:Emisor[^>]*\bRfc="([^"]+)"'),
        "rfc_receptor": g(r'<cfdi:Receptor[^>]*\bRfc="([^"]+)"'),
        "nombre": g(r'<cfdi:Receptor[^>]*\bNombre="([^"]+)"') or "",
        "percepciones": num(r'\bTotalPercepciones="([^"]+)"'),
        "total": num(r'<cfdi:Comprobante[^>]*\bTotal="([^"]+)"'),
        "inicio": date.fromisoformat(fi[:10]) if fi else None,
        "fin": date.fromisoformat(ff[:10]) if ff else None,
    }


def leer_archivos(rutas, nombres=None):
    """[(nombre, bytes)] o rutas -> lista de dicts, uno por recibo."""
    pendientes = []
    for i, r in enumerate(rutas):
        with open(r, "rb") as f:
            pendientes.append(((nombres or [None] * len(rutas))[i] or os.path.basename(r), f.read()))
    filas = []
    while pendientes:
        nombre, datos = pendientes.pop(0)
        bajo = nombre.lower()
        if bajo.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(datos)) as z:
                for n in z.namelist():
                    if n.lower().endswith((".pdf", ".xml")) and "__MACOSX" not in n:
                        pendientes.append((os.path.basename(n), z.read(n)))
        elif bajo.endswith(".xml"):
            filas.append(datos_de_xml(nombre, datos))
        elif bajo.endswith(".pdf"):
            filas.append(datos_de_texto(nombre, _texto_pdf(datos)))
    # Si hay PDF y XML del mismo folio, manda el XML (trae el total exacto).
    por_uuid = {}
    for f in filas:
        clave = f["uuid"] or f["archivo"]
        if clave not in por_uuid or f["origen"] == "XML":
            if clave in por_uuid and por_uuid[clave]["origen"] == "PDF":
                f["percepciones"] = f["percepciones"] or por_uuid[clave]["percepciones"]
                f["nombre"] = f["nombre"] or por_uuid[clave]["nombre"]
            por_uuid[clave] = f
    return list(por_uuid.values())


# ---------------------------------------------------------------------------
# SAT
# ---------------------------------------------------------------------------
def _soap(expresion, timeout=30):
    cuerpo = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:tem="http://tempuri.org/"><soapenv:Header/><soapenv:Body><tem:Consulta>'
        f"<tem:expresionImpresa><![CDATA[{expresion}]]></tem:expresionImpresa>"
        "</tem:Consulta></soapenv:Body></soapenv:Envelope>"
    ).encode("utf-8")
    req = urllib.request.Request(SAT_URL, data=cuerpo, headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": SOAP_ACTION})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (URL fija del SAT)
        return html.unescape(r.read().decode("utf-8", "ignore"))


def interpretar(respuesta: str) -> dict:
    val = lambda tag: (re.search(rf"<a:{tag}>(.*?)</a:{tag}>", respuesta) or [None, ""])[1]   # noqa: E731
    cod, estado = val("CodigoEstatus"), val("Estado")
    if cod.startswith("N - 602"):
        estado = ESTADO_NO_EXISTE
    elif cod.startswith("N - 601"):
        estado = ESTADO_NO_COINCIDE
    return {"estado_sat": estado or ESTADO_ERROR, "codigo_sat": cod,
            "cancelable": val("EsCancelable"), "estatus_cancelacion": val("EstatusCancelacion"),
            "efos": val("ValidacionEFOS")}


def consultar(fila, soap=_soap) -> dict:
    faltan = [k for k in ("uuid", "rfc_emisor", "rfc_receptor", "total") if not fila.get(k)]
    if faltan:
        return {"estado_sat": ESTADO_SIN_DATOS, "codigo_sat": "Falta: " + ", ".join(faltan)}
    expresion = (f"?re={fila['rfc_emisor']}&rr={fila['rfc_receptor']}"
                 f"&tt={fila['total']:.2f}&id={fila['uuid']}")
    try:
        return interpretar(soap(expresion))
    except Exception as e:   # sin red, SAT caído, timeout
        return {"estado_sat": ESTADO_ERROR, "codigo_sat": type(e).__name__}


# ---------------------------------------------------------------------------
# Análisis por persona
# ---------------------------------------------------------------------------
def frecuencia(inicio, fin):
    dias = (fin - inicio).days + 1
    if dias <= 8:
        return "Semanal", 8
    if dias <= 16:
        return "Quincenal", 4
    return "Mensual", 2


def fin_siguiente(inicio: date, fin: date, freq: str) -> date:
    """Fecha en que termina el periodo que sigue al último recibo."""
    if freq == "Quincenal" and inicio.day in (1, 16):
        if fin.day <= 15:
            return date(fin.year, fin.month, calendar.monthrange(fin.year, fin.month)[1])
        y, m = (fin.year + 1, 1) if fin.month == 12 else (fin.year, fin.month + 1)
        return date(y, m, 15)
    if freq == "Mensual" and inicio.day == 1:
        y, m = (fin.year + 1, 1) if fin.month == 12 else (fin.year, fin.month + 1)
        return date(y, m, calendar.monthrange(y, m)[1])
    return fin + timedelta(days=(fin - inicio).days + 1)


def analizar_persona(recibos, hoy: date):
    """recibos: dicts de UNA persona, ya consultados. Devuelve el resumen."""
    con_fecha = sorted([r for r in recibos if r.get("fin")], key=lambda r: r["fin"])
    if not con_fecha:
        return {"recibos": recibos, "frecuencia": "", "seleccion": [], "avisos": ["Ningún recibo trae periodo legible."]}
    freq, n = frecuencia(con_fecha[-1]["inicio"], con_fecha[-1]["fin"])
    sel = con_fecha[-n:]
    avisos = []
    if len(sel) < n:
        avisos.append(f"Hay {len(sel)} de {n} recibos {freq.lower()}es para cubrir 2 meses.")
    for a, b in zip(sel, sel[1:]):
        if (b["inicio"] - a["fin"]).days > 1:
            avisos.append(f"Falta el periodo entre {a['fin']:%d/%m} y {b['inicio']:%d/%m}.")
    no_ok = [r for r in sel if r.get("estado_sat") != ESTADO_OK]
    if no_ok:
        avisos.append(f"{len(no_ok)} recibo(s) del periodo no salen vigentes en el SAT.")
    mitad = len(sel) // 2 or 1
    mes1, mes2 = sel[:mitad], sel[mitad:]
    suma = lambda rs: round(sum(r.get("percepciones") or 0 for r in rs), 2)   # noqa: E731
    ultimo = sel[-1]
    sig = fin_siguiente(ultimo["inicio"], ultimo["fin"], freq)
    vto = vence(sig)
    restantes = habiles_entre(hoy, vto) if hoy <= vto else -habiles_entre(vto, hoy)
    b1, b2 = suma(mes1), (suma(mes2) if mes2 else None)
    ingreso = min(b1, b2) if b2 is not None else b1
    if len(sel) == n and ingreso < INGRESO_MINIMO:
        avisos.append(f"El ingreso mensual con nómina (mes más bajo) es ${ingreso:,.2f}: no llega al mínimo de "
                      f"${INGRESO_MINIMO:,.0f} brutos. Los ingresos adicionales no lo completan.")
    return {
        "recibos": con_fecha, "frecuencia": freq, "seleccion": sel, "avisos": avisos,
        "bruto_mes1": b1, "bruto_mes2": b2, "ingreso_mensual": ingreso,
        "periodo_mes1": (mes1[0]["inicio"], mes1[-1]["fin"]),
        "periodo_mes2": (mes2[0]["inicio"], mes2[-1]["fin"]) if mes2 else None,
        "ultimo_fin": ultimo["fin"], "siguiente_fin": sig, "vence": vto, "habiles_restantes": restantes,
    }


def analizar(filas, hoy: date):
    personas = {}
    for f in filas:
        personas.setdefault(f.get("rfc_receptor") or "Sin RFC", []).append(f)
    salida = []
    for rfc, rs in personas.items():
        res = analizar_persona(rs, hoy)
        res["rfc"] = rfc
        res["nombre"] = next((r["nombre"] for r in rs if r.get("nombre")), "")
        salida.append(res)
    return salida


# ---------------------------------------------------------------------------
# Excel de salida
# ---------------------------------------------------------------------------
def a_excel(filas, personas, ruta):
    import pandas as pd
    cols = ["archivo", "origen", "inicio", "fin", "uuid", "rfc_emisor", "rfc_receptor",
            "percepciones", "total", "estado_sat", "codigo_sat", "cancelable", "efos"]
    df = pd.DataFrame(filas).reindex(columns=cols).sort_values(["rfc_receptor", "fin"])
    resumen = pd.DataFrame([{
        "RFC": p["rfc"], "Nombre": p["nombre"], "Frecuencia": p["frecuencia"],
        "Bruto mes 1": p.get("bruto_mes1"), "Bruto mes 2": p.get("bruto_mes2"),
        "Ingreso mensual (mes más bajo)": p.get("ingreso_mensual"),
        "Último periodo termina": p.get("ultimo_fin"), "Periodo siguiente termina": p.get("siguiente_fin"),
        "Vigencia hasta": p.get("vence"),
        "Días hábiles restantes": p.get("habiles_restantes"), "Avisos": " | ".join(p["avisos"]),
    } for p in personas])
    with pd.ExcelWriter(ruta) as w:
        resumen.to_excel(w, sheet_name="Resumen", index=False)
        df.to_excel(w, sheet_name="Recibos", index=False)
    return ruta


def main(rutas, carpeta_salida, nombres=None, hoy=None, soap=_soap):
    from . import fechas as _fechas
    hoy = hoy or _fechas.hoy()
    filas = leer_archivos(rutas, nombres)
    for f in filas:
        f.update(consultar(f, soap=soap))
    personas = analizar(filas, hoy)
    os.makedirs(carpeta_salida, exist_ok=True)
    ruta = a_excel(filas, personas, os.path.join(carpeta_salida, f"Validacion_nomina_SAT_{hoy:%Y%m%d}.xlsx"))
    return [ruta], {"filas": filas, "personas": personas, "hoy": hoy}
