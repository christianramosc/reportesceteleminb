# -*- coding: utf-8 -*-
"""
VALIDADOR DE CONSTANCIA DE SITUACIÓN FISCAL (CSF) — candados anti-alteración
============================================================================

Sube una CSF (PDF descargado del portal del SAT) y el script revisa, punto
por punto, los "candados" que una constancia auténtica trae y que una
alterada —editada a mano, re-impresa, armada desde cero o generada con IA—
casi nunca logra reproducir todos a la vez.

Se basa en el boletín BMGFS "Mejores Prácticas de Prevención de Fraudes —
Constancia Fiscal" (Dirección de Riesgos, octubre 2026):

    1. La constancia debe estar emitida recientemente (último mes).
    2. El 1er QR debe coincidir con el documento: nombre, RFC, CURP,
       situación, régimen y fecha de inicio, domicilio.
    3. El 2do QR debe coincidir con la cadena original: fecha y RFC.
    Y: el PDV no debe generar, editar ni manipular el documento.

Lo que este script NO puede hacer (y por eso el reporte siempre trae los
links de los QR): consultar con certeza la base del SAT. El veredicto
"SIN INDICIOS DE ALTERACIÓN" significa que el archivo pasó todos los
candados técnicos; la validación definitiva sigue siendo escanear el QR
y comparar contra lo que muestra el portal del SAT.

Cómo leer los resultados de cada candado
----------------------------------------
    OK     el candado se cumple.
    AVISO  algo raro que tiene explicación legítima posible: revisar a mano.
    FALLA  indicio fuerte de alteración o fabricación.
    INFO   dato informativo, no suma ni resta.

Las "Políticas" (vigencia y estatus ACTIVO) se reportan aparte: una CSF de
hace tres meses es auténtica, pero no sirve para el expediente.

Uso
---
- En la app de Streamlit: pestaña "Validar CSF".
- En Colab:   !pip install pdfplumber pypdf pypdfium2 zxing-cpp reportlab
              import validar_csf;  validar_csf.main()
- Por código: analisis = analizar_csf("csf.pdf");  generar_pdf(analisis, "salida.pdf")
"""

import base64
import hashlib
import html
import io
import os
import re
import unicodedata
from html.parser import HTMLParser
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List

try:
    from . import fechas as _fechas
except ImportError:  # ejecución suelta (Colab)
    _fechas = None


# ===========================================================================
#  CONSTANTES — huellas de una CSF auténtica
# ===========================================================================
# Todas salen de analizar CSF reales descargadas del portal del SAT (persona
# física y moral, plantilla anterior y plantilla gob.mx 2026). Si el SAT
# cambia su motor de generación, el candado 1.2 empezará a marcar AVISO en
# todas las constancias: ese es el momento de actualizar estas constantes.

# 1.2 — El SAT genera la CSF con Oracle BI/XML Publisher. Word, Canva,
# iLovePDF, Acrobat, "Imprimir a PDF", Chrome, LibreOffice, Python
# (reportlab/pypdf) o un generador con IA dejan SU nombre aquí.
PRODUCTOR_SAT = "Oracle XML Publisher"

# 1.7 — Fuentes que usa la plantilla. Oracle NO incrusta Helvetica (es una
# de las 14 fuentes estándar del PDF); la plantilla 2026 solo incrusta un
# subconjunto de "Noto Sans Medium" para el "Página 1 de 2". Cualquier otra
# fuente (ArialMT, Calibri, TimesNewRoman, una Helvetica incrustada, etc.)
# entró al editar el archivo.
FUENTES_SAT = ("Helvetica", "Helvetica-Bold", "Noto Sans Medium")

# 1.10 — Tamaños de letra que usa la plantilla (puntos).
TAMANOS_SAT = (8.0, 10.0, 12.0)

# 2.x — Los dos QR apuntan al validador del SAT. Un QR alterado suele llevar
# a una página clonada (sat-gob-mx.com, siat-sat.mx, bit.ly/...) que muestra
# lo que el defraudador quiera.
DOMINIO_QR = "siat.sat.gob.mx"
RUTA_QR = "/app/qr/faces/pages/mobile/validadorqr.jsf"
# Sufijos de hospedaje gratuito: un QR que lleva aquí es una página hecha por
# un particular, nunca del SAT (el SAT solo usa dominios .gob.mx).
HOSTING_GRATUITO = {".web.app": "Firebase Hosting de Google", ".firebaseapp.com": "Firebase Hosting de Google",
                    ".vercel.app": "Vercel", ".netlify.app": "Netlify", ".github.io": "GitHub Pages",
                    ".pages.dev": "Cloudflare Pages", ".onrender.com": "Render",
                    ".glitch.me": "Glitch", ".000webhostapp.com": "000webhost", ".wixsite.com": "Wix",
                    ".blogspot.com": "Blogger", ".replit.app": "Replit"}
D1_QR_CEDULA = "10"   # 1er QR (cédula): D3 = idCIF_RFC
D1_QR_SELLO = "26"    # 2do QR (sello):  D3 = folio_RFC

# 3.10 — Número de certificado con que el SAT sella la cadena original.
# Es el mismo en todas las CSF revisadas (2026). Si algún día cambia en
# constancias legítimas, actualízalo aquí; mientras, un valor distinto es
# AVISO, no FALLA.
CERTIFICADO_SAT = "200001088888800000041"

# 4.1 — Política del boletín: "emitida recientemente (último mes)".
DIAS_VIGENCIA = 30

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
         "NOVIEMBRE": 11, "DICIEMBRE": 12}

# 3.9 — Primeros dos dígitos del código postal por entidad (SEPOMEX).
CP_POR_ENTIDAD = {
    "AGUASCALIENTES": [(20, 20)], "BAJA CALIFORNIA SUR": [(23, 23)],
    "BAJA CALIFORNIA": [(21, 22)], "CAMPECHE": [(24, 24)],
    "COAHUILA": [(25, 27)], "COLIMA": [(28, 28)], "CHIAPAS": [(29, 30)],
    "CHIHUAHUA": [(31, 33)], "CIUDAD DE MEXICO": [(1, 16)],
    "DISTRITO FEDERAL": [(1, 16)], "DURANGO": [(34, 35)],
    "GUANAJUATO": [(36, 38)], "GUERRERO": [(39, 41)], "HIDALGO": [(42, 43)],
    "JALISCO": [(44, 49)], "MICHOACAN": [(58, 61)], "MORELOS": [(62, 62)],
    "NAYARIT": [(63, 63)], "NUEVO LEON": [(64, 67)], "OAXACA": [(68, 71)],
    "PUEBLA": [(72, 75)], "QUERETARO": [(76, 76)], "QUINTANA ROO": [(77, 77)],
    "SAN LUIS POTOSI": [(78, 79)], "SINALOA": [(80, 82)], "SONORA": [(83, 85)],
    "TABASCO": [(86, 86)], "TAMAULIPAS": [(87, 89)], "TLAXCALA": [(90, 90)],
    "VERACRUZ": [(91, 96)], "YUCATAN": [(97, 97)], "ZACATECAS": [(98, 99)],
    # Va al final: "MEXICO" también aparece dentro de "CIUDAD DE MEXICO".
    "MEXICO": [(50, 57)],
}

# 3.3 — Claves de entidad de nacimiento válidas en la CURP (NE = extranjero).
ENTIDADES_CURP = set("AS BC BS CC CL CM CS CH DF DG GT GR HG JC MC MN MS NT NL OC "
                     "PL QT QR SP SL SR TC TS TL VZ YN ZS NE".split())

# 3.8 — Regímenes que solo existen para un tipo de persona. ("Régimen
# Simplificado de Confianza" existe para ambas, por eso no está aquí.)
REGIMENES_SOLO_FISICA = ("SUELDOS Y SALARIOS", "ACTIVIDADES EMPRESARIALES Y PROFESIONALES",
                         "ARRENDAMIENTO", "PLATAFORMAS TECNOLOGICAS", "INCORPORACION FISCAL",
                         "INGRESOS POR DIVIDENDOS", "INGRESOS POR INTERESES",
                         "ENAJENACION O ADQUISICION DE BIENES", "DEMAS INGRESOS",
                         "ACTIVIDADES AGRICOLAS, GANADERAS, SILVICOLAS Y PESQUERAS PF")
REGIMENES_SOLO_MORAL = ("GENERAL DE LEY PERSONAS MORALES", "PERSONAS MORALES CON FINES NO LUCRATIVOS",
                        "SOCIEDADES COOPERATIVAS", "COORDINADOS", "OPCIONAL PARA GRUPOS")

# Estados y sus nombres para el reporte.
OK, AVISO, FALLA, INFO = "OK", "AVISO", "FALLA", "INFO"

SECCIONES = {
    1: "Archivo y estructura del PDF",
    2: "Códigos QR y código de barras",
    3: "Coherencia de los datos fiscales",
    4: "Políticas de la financiera",
}


# ===========================================================================
#  ESTRUCTURAS DE RESULTADO
# ===========================================================================
@dataclass
class Candado:
    clave: str        # "1.2", "2.3", ...
    titulo: str
    estado: str       # OK / AVISO / FALLA / INFO
    detalle: str      # qué se encontró en ESTE archivo
    previene: str = ""  # qué fraude detecta este candado (para el reporte)

    @property
    def seccion(self):
        return int(self.clave.split(".")[0])


@dataclass
class Analisis:
    archivo: str
    sha256: str
    tipo_archivo: str                       # "pdf" o "imagen"
    datos: Dict[str, object] = field(default_factory=dict)
    candados: List[Candado] = field(default_factory=list)
    urls_qr: List[str] = field(default_factory=list)

    # --- veredictos -------------------------------------------------------
    def _de_seccion(self, secciones):
        return [c for c in self.candados if c.seccion in secciones]

    @property
    def veredicto(self):
        """Autenticidad: secciones 1 a 3. La 4 (políticas) va aparte."""
        tecnicos = self._de_seccion((1, 2, 3))
        if self.tipo_archivo != "pdf":
            return "NO VERIFICABLE"
        if any(c.estado == FALLA for c in tecnicos):
            return "ALTERADA / NO CONFIABLE"
        if any(c.estado == AVISO for c in tecnicos):
            return "REVISAR MANUALMENTE"
        return "SIN INDICIOS DE ALTERACIÓN"

    @property
    def cumple_politicas(self):
        return not any(c.estado in (FALLA, AVISO) for c in self._de_seccion((4,)))

    def conteo(self):
        return Counter(c.estado for c in self.candados)


# ===========================================================================
#  UTILIDADES
# ===========================================================================
def _norm(texto):
    """Mayúsculas, sin acentos (conserva la Ñ), espacios simples."""
    t = str(texto or "").upper().replace("Ñ", "\0")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).replace("\0", "Ñ")
    return re.sub(r"\s+", " ", t).strip()


def _compacto(texto):
    """Para comparar sin que importen espacios ni acentos."""
    return re.sub(r"[^A-Z0-9Ñ&]", "", _norm(texto))


def _fecha_texto(texto):
    """'25 DE JULIO DE 2022' o '25/07/2022' -> date; si no, None."""
    t = _norm(texto)
    m = re.search(r"(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})", t)
    if m and m.group(2) in MESES:
        try:
            return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _fecha_aammdd(aammdd, referencia=None):
    """'041111' -> date(2004,11,11). El siglo se elige para no caer en el futuro."""
    try:
        aa, mm, dd = int(aammdd[:2]), int(aammdd[2:4]), int(aammdd[4:6])
        hoy_ = referencia or date.today()
        anio = 2000 + aa if 2000 + aa <= hoy_.year else 1900 + aa
        return date(anio, mm, dd)
    except (ValueError, TypeError):
        return None


def _hoy():
    return _fechas.hoy() if _fechas else date.today()


def _fmt(fecha):
    return fecha.strftime("%d/%m/%Y") if fecha else "—"


# ===========================================================================
#  ALGORITMOS OFICIALES DE DÍGITO VERIFICADOR (RFC y CURP)
# ===========================================================================
# Un RFC o CURP inventado —o "corregido" a mano en el PDF— casi nunca cuadra
# con su dígito verificador. Una IA que genera una constancia "realista"
# tampoco suele calcularlo. Ambos algoritmos son públicos (SAT / RENAPO).
_VAL_RFC = {**{str(i): i for i in range(10)},
            **{c: 10 + i for i, c in enumerate("ABCDEFGHIJKLMN")}, "&": 24,
            **{c: 25 + i for i, c in enumerate("OPQRSTUVWXYZ")}, " ": 37, "Ñ": 38}


def digito_rfc(rfc):
    """Dígito verificador que DEBERÍA tener el RFC (último carácter)."""
    base = rfc[:-1]
    if len(base) == 11:      # persona moral: se rellena a 12 con un espacio
        base = " " + base
    suma = sum(_VAL_RFC.get(c, 0) * (13 - i) for i, c in enumerate(base))
    residuo = suma % 11
    if residuo == 0:
        return "0"
    d = 11 - residuo
    return "A" if d == 10 else str(d)


_VAL_CURP = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"


def digito_curp(curp):
    suma = sum(_VAL_CURP.index(c) * (18 - i) for i, c in enumerate(curp[:17]) if c in _VAL_CURP)
    return str((10 - suma % 10) % 10)


PAT_RFC_FISICA = re.compile(r"^[A-ZÑ&]{4}\d{6}[A-Z0-9]{2}[0-9A]$")
PAT_RFC_MORAL = re.compile(r"^[A-ZÑ&]{3}\d{6}[A-Z0-9]{2}[0-9A]$")
PAT_CURP = re.compile(r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d$")

# Partículas que el SAT omite al formar las letras del RFC.
_PARTICULAS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "MC", "MAC", "VON", "VAN", "MI", "EL", "E"}
_PARTICULAS_MORAL = _PARTICULAS | {"SA", "CV", "SC", "SAPI", "SAB", "S", "A", "C", "V", "R", "L",
                                   "SRL", "RL", "COMPAÑIA", "CIA", "SOCIEDAD", "COOPERATIVA",
                                   "THE", "OF", "AND", "AL", "EN", "CON", "POR", "PARA"}


def letras_rfc_fisica(paterno, materno, nombres):
    """Las 4 letras que el SAT asigna a una persona física (regla general).
    Excepciones (palabras altisonantes, nombres de una letra, extranjeros)
    hacen que a veces no cuadre: por eso este candado es AVISO, no FALLA."""
    def limpiar(t):
        palabras = [p for p in _norm(t).replace("Ñ", "X").split() if p not in _PARTICULAS]
        return palabras
    pat, mat, nom = limpiar(paterno), limpiar(materno), limpiar(nombres)
    if not pat or not nom:
        return None
    if len(nom) > 1 and nom[0] in ("JOSE", "J", "MARIA", "MA", "MA.", "M"):
        nom = nom[1:]
    p = pat[0]
    vocal = next((c for c in p[1:] if c in "AEIOU"), "X")
    return (p[0] + vocal + (mat[0][0] if mat else "X") + nom[0][0])


def letras_rfc_moral(denominacion):
    """Las 3 letras de una persona moral (regla general, mismas salvedades)."""
    palabras = [p for p in re.split(r"[\s,.]+", _norm(denominacion))
                if p and p not in _PARTICULAS_MORAL]
    if not palabras:
        return None
    if len(palabras) >= 3:
        return "".join(p[0] for p in palabras[:3])
    if len(palabras) == 2:
        return palabras[0][0] + palabras[1][:2]
    return palabras[0][:3]


def entidad_de_texto(texto):
    t = _norm(texto)
    for ent in CP_POR_ENTIDAD:
        if ent in t:
            return ent
    return None


def cp_coincide_entidad(cp, entidad):
    if not (cp and cp.isdigit() and len(cp) == 5):
        return None
    ent = entidad_de_texto(entidad)
    if not ent:
        return None
    pref = int(cp[:2])
    return any(a <= pref <= b for a, b in CP_POR_ENTIDAD[ent])


# ===========================================================================
#  LECTURA DE CÓDIGOS (QR y código de barras)
# ===========================================================================
def _leer_codigos(imagen_pil):
    """Lista de (formato, texto) en una imagen. Usa zxing-cpp (pip, sin
    dependencias del sistema; funciona en Streamlit Cloud)."""
    try:
        import zxingcpp
    except ImportError:
        return None
    try:
        return [(str(r.format).split(".")[-1].replace(" ", ""), r.text)
                for r in zxingcpp.read_barcodes(imagen_pil.convert("RGB"))]
    except Exception:
        return []


def parse_qr_sat(url):
    """Desarma la URL del QR del SAT. Devuelve dict o None."""
    try:
        u = urllib.parse.urlsplit(url.strip())
    except Exception:
        return None
    q = dict(urllib.parse.parse_qsl(u.query))
    d3 = q.get("D3", "")
    folio, _, rfc = d3.partition("_")
    return {"esquema": u.scheme, "dominio": (u.hostname or "").lower(), "ruta": u.path,
            "D1": q.get("D1"), "D2": q.get("D2"), "D3": d3, "folio": folio, "rfc": rfc,
            "extra": sorted(set(q) - {"D1", "D2", "D3"}), "url": url}


# ===========================================================================
#  EXTRACCIÓN DEL CONTENIDO DEL PDF
# ===========================================================================
def _extraer_pdf(ruta):
    """Lee TODO lo que necesitan los candados, una sola vez."""
    import pdfplumber
    import pypdf

    crudo = open(ruta, "rb").read()
    info = {"crudo": crudo}

    # --- Estructura (pypdf) ------------------------------------------------
    lector = pypdf.PdfReader(io.BytesIO(crudo), strict=False)
    info["cifrado"] = lector.is_encrypted
    if lector.is_encrypted:
        try:
            lector.decrypt("")
        except Exception:
            pass
    info["n_paginas"] = len(lector.pages)
    meta = {}
    try:
        meta = {str(k): str(v) for k, v in (lector.metadata or {}).items()}
    except Exception:
        pass
    info["metadatos"] = meta
    trailer = lector.trailer
    ids = trailer.get("/ID")
    info["ids"] = [bytes(getattr(x, "original_bytes", b"")).hex() for x in (ids or [])]
    raiz = trailer["/Root"]
    info["claves_raiz"] = sorted(str(k) for k in raiz.keys())
    paginas = []
    xobjetos = {}
    for i, pg in enumerate(lector.pages):
        contenidos = pg.get("/Contents")
        n_contenidos = len(contenidos.get_object()) if isinstance(
            contenidos.get_object(), pypdf.generic.ArrayObject) else (1 if contenidos else 0)
        fuentes = []
        recursos = pg.get("/Resources") or {}
        recursos = recursos.get_object() if hasattr(recursos, "get_object") else recursos
        for _, f in (recursos.get("/Font") or {}).items():
            f = f.get_object()
            base = str(f.get("/BaseFont", ""))
            incrustada = False
            desc = f.get("/FontDescriptor")
            if desc is None and f.get("/DescendantFonts"):
                desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
            if desc is not None:
                desc = desc.get_object()
                incrustada = any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))
            fuentes.append((base.lstrip("/"), incrustada))
        for nombre, xo in (recursos.get("/XObject") or {}).items():
            xo = xo.get_object()
            xobjetos[str(nombre)] = (str(xo.get("/Subtype")), int(xo.get("/Width", 0) or 0),
                                     int(xo.get("/Height", 0) or 0), str(xo.get("/Filter")))
        paginas.append({"n_contenidos": n_contenidos, "fuentes": fuentes,
                        "anotaciones": len(pg.get("/Annots") or []),
                        "caja": [float(x) for x in pg.mediabox]})
    info["paginas"] = paginas
    info["xobjetos"] = xobjetos

    # Imágenes incrustadas (para leer QR/código de barras "de origen").
    imagenes = []
    for i, pg in enumerate(lector.pages):
        try:
            for im in pg.images:
                imagenes.append({"pagina": i, "nombre": im.name, "pil": im.image})
        except Exception:
            pass
    info["imagenes"] = imagenes

    # --- Texto, tablas y caracteres (pdfplumber) ---------------------------
    tablas, textos, caracteres, colocadas, maquetacion = [], [], [], [], []
    emision = ""
    with pdfplumber.open(io.BytesIO(crudo)) as pdf:
        for i, pg in enumerate(pdf.pages):
            textos.append(pg.extract_text(x_tolerance=1) or "")
            for t in pg.extract_tables({"text_x_tolerance": 1}):
                tablas.append((i, t))
            for ch in pg.chars:
                caracteres.append({"pagina": i, "texto": ch["text"], "fuente": ch["fontname"],
                                   "tam": round(float(ch["size"]), 1), "x0": ch["x0"],
                                   "x1": ch["x1"], "top": ch["top"], "bottom": ch["bottom"],
                                   "color": ch.get("non_stroking_color")})
            for im in pg.images:
                colocadas.append({"pagina": i, "nombre": im.get("name"),
                                  "x0": im["x0"], "top": im["top"],
                                  "ancho": im["width"], "alto": im["height"],
                                  "src": tuple(int(round(v)) for v in (im.get("srcsize") or ()))})
            # Lugar y fecha de emisión: se lee SOLO dentro de su recuadro (a su
            # izquierda está la cédula y sus renglones se intercalan).
            if i == 0 and not emision:
                rotulo = pg.search("Lugar y Fecha de Emisi")
                if rotulo:
                    r = rotulo[0]
                    marcos = [m for m in pg.rects if m["x0"] <= r["x0"] and m["x1"] >= r["x1"]
                              and m["top"] <= r["top"] and m["bottom"] >= r["bottom"]]
                    if marcos:
                        m = min(marcos, key=lambda m: m["width"] * m["height"])
                        caja = (m["x0"], r["bottom"], m["x1"], m["bottom"])
                    else:
                        caja = (max(r["x0"] - 60, 0), r["bottom"], pg.width,
                                min(r["bottom"] + 40, pg.height))
                    emision = pg.within_bbox(caja).extract_text(x_tolerance=1) or ""
            maquetacion.extend(_anomalias_maquetacion(pg, i))
    info["textos"] = textos
    info["texto"] = "\n".join(textos)
    info["tablas"] = tablas
    info["caracteres"] = caracteres
    info["colocadas"] = colocadas
    info["emision_texto"] = re.sub(r"\s+", " ", emision).strip()
    info["maquetacion"] = maquetacion

    # --- Lo que "se ve": página renderizada (lo que escanearía un celular) --
    info["render_codigos"] = []
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(crudo)
        for i in range(len(doc)):
            img = doc[i].render(scale=3).to_pil()
            for fmt, txt in (_leer_codigos(img) or []):
                info["render_codigos"].append({"pagina": i, "formato": fmt, "texto": txt})
        doc.close()
    except Exception as e:  # sin pypdfium2: el candado 2.6 se reporta como INFO
        info["render_error"] = str(e)
    return info


def _caja_que_contiene(pg, x0, top, x1, bottom):
    """El recuadro más chico de la página que encierra el área dada."""
    marcos = [m for m in pg.rects if m["x0"] <= x0 + 0.5 and m["x1"] >= x1 - 0.5
              and m["top"] <= top + 0.5 and m["bottom"] >= bottom - 0.5]
    return min(marcos, key=lambda m: m["width"] * m["height"]) if marcos else None


def _centros_de_lineas(chars):
    lineas = {}
    for c in chars:
        lineas.setdefault(round(c["bottom"], 1), []).append(c)
    return [((min(c["x0"] for c in l) + max(c["x1"] for c in l)) / 2,
             "".join(c["text"] for c in sorted(l, key=lambda c: c["x0"])).strip())
            for _, l in sorted(lineas.items())]


def _anomalias_maquetacion(pg, i):
    """Candado 1.13 (ver explicación allá). Devuelve [(página, texto, motivo)]."""
    anomalias = []
    TOL_CENTRO, TOL_ESPACIO = 0.15, 0.05

    # (a) Textos CENTRADOS: cédula (junto al 1er QR) y "Lugar y Fecha de Emisión".
    bloques = []
    if i == 0:
        caja_em = None
        r = pg.search("Lugar y Fecha de Emisi")
        if r:
            caja_em = _caja_que_contiene(pg, r[0]["x0"], r[0]["top"], r[0]["x1"], r[0]["bottom"])
            if caja_em:
                bloques.append(("lugar y fecha de emisión", pg.within_bbox(
                    (caja_em["x0"], caja_em["top"], caja_em["x1"], caja_em["bottom"])).chars))
        # La columna de texto de la cédula: a la derecha del 1er QR, desde el
        # RFC hasta "VALIDA TU INFORMACIÓN FISCAL", sin invadir el recuadro
        # de emisión.
        qrs = [im for im in pg.images if tuple(int(round(v)) for v in (im.get("srcsize") or ())) == (150, 150)]
        valida = pg.search("VALIDA TU INFORMACI")
        if qrs and caja_em:
            qr = min(qrs, key=lambda im: im["top"])
            abajo = valida[0]["bottom"] + 12 if valida else qr["bottom"] + 30
            bloques.append(("cédula", [c for c in pg.chars if c["x0"] >= qr["x1"] and c["x1"] <= caja_em["x0"]
                                       and qr["top"] - 15 <= c["top"] and c["bottom"] <= abajo]))
    for nombre, chars in bloques:
        centros = _centros_de_lineas(chars)
        if len(centros) < 2:
            continue
        moda = Counter(round(c, 1) for c, _ in centros).most_common(1)[0][0]
        for c, texto in centros:
            if abs(c - moda) > TOL_CENTRO:
                anomalias.append((i, texto, f"descentrado {c - moda:+.2f} pt en {nombre}"))

    # (b) ESPACIADO entre palabras en celdas de UN renglón: Oracle pone cada
    # palabra a exactamente un espacio (o varios) de la anterior.
    try:
        palabras = pg.extract_words(x_tolerance=1, extra_attrs=["size"])
        tablas = pg.find_tables()
    except Exception:
        return anomalias
    for t in tablas:
        for (x0, top, x1, bot) in t.cells:
            ws = sorted((w for w in palabras if w["x0"] >= x0 - 0.5 and w["x1"] <= x1 + 0.5
                         and w["top"] >= top - 0.5 and w["bottom"] <= bot + 0.5), key=lambda w: w["x0"])
            if len(ws) < 2 or len({round(w["bottom"], 1) for w in ws}) != 1:
                continue
            for a, b in zip(ws, ws[1:]):
                espacio = a["size"] * 0.278          # ancho del espacio en Helvetica
                hueco = b["x0"] - a["x1"]
                k = round(hueco / espacio)
                if k < 1 or abs(hueco - k * espacio) > TOL_ESPACIO:
                    anomalias.append((i, f"{a['text']} {b['text']}",
                                      f"espacio de {hueco:.2f} pt (debería ser {espacio:.2f})"))
    return anomalias


def _campos(info):
    """Convierte las tablas en un diccionario {etiqueta normalizada: valor}."""
    campos, actividades, regimenes, obligaciones = {}, [], [], []
    cedula = []
    modo = None
    for _, tabla in info["tablas"]:
        for fila in tabla:
            celdas = [c for c in fila if c is not None]
            if not celdas:
                continue
            primera = _norm(celdas[0])
            if primera.startswith("CEDULA DE IDENTIFICACION"):
                modo = "cedula"
                continue
            if primera.startswith("ACTIVIDADES ECONOMICAS"):
                modo = "act"
                continue
            if primera.startswith("REGIMENES"):
                modo = "reg"
                continue
            if primera.startswith("OBLIGACIONES"):
                modo = "obl"
                continue
            if primera.startswith("DATOS DE IDENTIFICACION") or primera.startswith("DATOS DEL DOMICILIO"):
                modo = "kv"
                continue
            if primera in ("ORDEN", "REGIMEN", "DESCRIPCION DE LA OBLIGACION"):
                continue   # renglón de encabezados
            if modo == "cedula":
                cedula.extend(str(celdas[0]).splitlines())
            elif modo == "act" and len(celdas) >= 3:
                actividades.append({"actividad": celdas[1], "porcentaje": celdas[2],
                                    "inicio": celdas[3] if len(celdas) > 3 else "",
                                    "fin": celdas[4] if len(celdas) > 4 else ""})
            elif modo == "reg" and len(celdas) >= 2:
                regimenes.append({"regimen": celdas[0], "inicio": celdas[1],
                                  "fin": celdas[2] if len(celdas) > 2 else ""})
            elif modo == "obl" and len(celdas) >= 3:
                obligaciones.append({"obligacion": celdas[0], "inicio": celdas[2] if len(celdas) > 2 else ""})
            else:
                # Tabla de datos: "Etiqueta:" | "valor"  o  "Etiqueta: valor" en una celda.
                # (Si la 2a celda también trae ":", son dos campos en un
                # renglón: "Nombre de la Localidad:" vacío | "Municipio: COLIMA".)
                if (len(celdas) == 2 and str(celdas[0]).rstrip().endswith(":")
                        and ":" not in str(celdas[1] or "")):
                    campos[_norm(celdas[0]).rstrip(":").replace(" ", "")] = re.sub(
                        r"\s+", " ", str(celdas[1] or "")).strip()
                    continue
                for c in celdas:
                    if ":" in str(c):
                        etq, _, val = str(c).partition(":")
                        campos[_norm(etq).replace(" ", "")] = re.sub(r"\s+", " ", val).strip()
    return campos, actividades, regimenes, obligaciones, cedula


def _extraer_datos(info):
    campos, actividades, regimenes, obligaciones, cedula = _campos(info)
    g = lambda *claves: next((campos[k] for k in claves if campos.get(k)), "")  # noqa: E731
    d = {
        "rfc": g("RFC"),
        "curp": g("CURP"),
        "nombres": g("NOMBRE(S)", "NOMBRES"),
        "paterno": g("PRIMERAPELLIDO"),
        "materno": g("SEGUNDOAPELLIDO"),
        "razon_social": g("DENOMINACION/RAZONSOCIAL", "DENOMINACIONORAZONSOCIAL"),
        "regimen_capital": g("REGIMENCAPITAL"),
        "nombre_comercial": g("NOMBRECOMERCIAL"),
        "inicio_operaciones": g("FECHAINICIODEOPERACIONES"),
        "estatus": g("ESTATUSENELPADRON"),
        "ultimo_cambio": g("FECHADEULTIMOCAMBIODEESTADO"),
        "cp": g("CODIGOPOSTAL"),
        "vialidad": g("NOMBREDEVIALIDAD"),
        "num_ext": g("NUMEROEXTERIOR"),
        "colonia": g("NOMBREDELACOLONIA"),
        "municipio": g("NOMBREDELMUNICIPIOODEMARCACIONTERRITORIAL"),
        "entidad": g("NOMBREDELAENTIDADFEDERATIVA"),
        "actividades": actividades, "regimenes": regimenes, "obligaciones": obligaciones,
    }
    d["tipo"] = "moral" if d["razon_social"] else ("fisica" if d["curp"] or d["paterno"] else "")
    d["nombre_completo"] = (d["razon_social"] if d["tipo"] == "moral" else
                            " ".join(x for x in (d["nombres"], d["paterno"], d["materno"]) if x))

    # --- Cédula (recuadro con el 1er QR) -----------------------------------
    lineas = [l.strip() for l in cedula if l.strip()]
    d["cedula_rfc"] = lineas[0] if lineas else ""
    nombre_lineas, idcif = [], ""
    for l in lineas[1:]:
        n = _norm(l)
        if n.startswith("IDCIF"):
            idcif = re.sub(r"\D", "", l)
        elif n.startswith(("REGISTRO FEDERAL", "CONTRIBUYENTES", "NOMBRE, DENOMINACION",
                           "SOCIAL", "VALIDA TU", "FISCAL")):
            continue
        else:
            nombre_lineas.append(l)
    d["cedula_nombre"] = " ".join(nombre_lineas)
    d["idcif"] = idcif
    if not idcif:
        m = re.search(r"idCIF:\s*(\d+)", info["texto"])
        d["idcif"] = m.group(1) if m else ""

    # --- Lugar y fecha de emisión ------------------------------------------
    em = info.get("emision_texto", "")
    if not _fecha_texto(em):
        m = re.search(r"([A-ZÁÉÍÓÚÑ .,]+?\bA\s+\d{1,2}\s+DE\s+[A-Z]+\s+DE\s+\d{4})", _norm(info["texto"]))
        em = m.group(1) if m else em
    d["emision_texto"] = em
    d["fecha_emision"] = _fecha_texto(em)
    d["lugar_emision"] = re.split(r"\s+A\s+\d", _norm(em))[0].strip(" ,") if em else ""

    # --- Cadena original y sello -------------------------------------------
    # La cadena viene partida en renglones. Se pegan SIN espacio (el base64
    # se corta a media palabra) y luego se repone el único espacio que se
    # pierde en el corte: "SITUACIÓN FISCAL".
    texto = info["texto"]
    m = re.search(r"Cadena\s*Original\s*Sello:\s*(.*?)\s*Sello\s*Digital:", texto, re.S)
    cadena = re.sub(r"\s*\n\s*", "", m.group(1)).strip() if m else ""
    d["cadena"] = re.sub(r"SITUACI([OÓ])N\s*FISCAL", r"SITUACI\1N FISCAL", cadena)
    # El sello puede partirse entre dos páginas: se quita el pie
    # "Página 2 de 3" que queda en medio y se toma todo el base64 seguido.
    m = re.search(r"Sello\s*Digital:\s*(.*)", texto, re.S)
    resto = re.sub(r"P[aá]gina\s*\[?\d+\]?\s*de\s*\[?\d+\]?", " ", m.group(1)) if m else ""
    m = re.match(r"[A-Za-z0-9+/=\s]+", resto)
    d["sello"] = re.sub(r"\s+", "", m.group(0)) if m else ""
    return d


# ===========================================================================
#  LOS CANDADOS
# ===========================================================================
def _candados_estructura(info, add):
    """SECCIÓN 1 — El archivo mismo. Detecta que el PDF NO salió tal cual del
    SAT: que se editó, se volvió a guardar, se imprimió a PDF, se armó en
    otro programa o es una imagen (foto, escaneo, generada con IA)."""
    crudo = info["crudo"]
    meta = info["metadatos"]
    chars = info["caracteres"]

    # 1.1 — CAPA DE TEXTO. La CSF del SAT es un PDF con texto seleccionable.
    # Una foto, un escaneo, una captura de pantalla o una imagen generada por
    # IA "pegada" en un PDF no trae texto: no hay forma de verificarla
    # técnicamente y es el formato favorito para falsificar.
    n_chars = len(chars)
    if n_chars < 200:
        add("1.1", "PDF con capa de texto (no foto ni escaneo)", FALLA,
            f"Solo {n_chars} caracteres de texto. Es una imagen (foto, escaneo, captura o "
            "imagen generada) dentro de un PDF. Pide el PDF original descargado del SAT.",
            "Constancias fotografiadas, escaneadas o generadas con IA como imagen.")
    else:
        add("1.1", "PDF con capa de texto (no foto ni escaneo)", OK,
            f"{n_chars:,} caracteres de texto seleccionable.",
            "Constancias fotografiadas, escaneadas o generadas con IA como imagen.")

    # 1.2 — PROGRAMA QUE GENERÓ EL PDF. Cada programa deja su firma en el
    # campo /Producer. El SAT usa Oracle XML Publisher. Abrir la CSF en
    # Acrobat/iLovePDF/Word y guardarla, o "Imprimir a PDF", lo reemplaza.
    productor = meta.get("/Producer", "")
    if productor.startswith(PRODUCTOR_SAT):
        add("1.2", "Generado por el motor del SAT", OK, f"Productor: {productor}.",
            "Constancias editadas y vueltas a guardar en otro programa.")
    else:
        add("1.2", "Generado por el motor del SAT", FALLA,
            f"Productor: «{productor or 'vacío'}». El SAT genera la CSF con {PRODUCTOR_SAT}; "
            "este archivo fue creado o re-guardado con otro programa.",
            "Constancias editadas y vueltas a guardar en otro programa.")

    # 1.3 — METADATOS DE EDICIÓN. La CSF original solo trae /Producer: sin
    # autor, título, creador, fechas ni metadatos XMP. Los editores agregan
    # /Creator, /ModDate, /Author, o un bloque XMP con su historial.
    extras = sorted(k for k in meta if k not in ("/Producer", "/Type"))
    tiene_xmp = b"<x:xmpmeta" in crudo or b"/Metadata" in crudo
    if extras or tiene_xmp:
        add("1.3", "Sin metadatos de edición", FALLA,
            "Trae " + ", ".join([f"{k[1:]}={meta[k][:40]!r}" for k in extras] +
                                (["metadatos XMP"] if tiene_xmp else [])) +
            ". La CSF del SAT no trae estos datos; los agrega el programa que la editó.",
            "Edición con Acrobat, Word, Canva, iLovePDF, navegadores, etc.")
    else:
        add("1.3", "Sin metadatos de edición", OK, "Solo trae el campo Producer, como el original.",
            "Edición con Acrobat, Word, Canva, iLovePDF, navegadores, etc.")

    # 1.4 — UNA SOLA REVISIÓN. Muchos editores no reescriben el PDF: le
    # AGREGAN al final los cambios ("guardado incremental"). El texto viejo
    # sigue adentro y el nuevo se pinta encima. Cada guardado agrega otro
    # "%%EOF" y otro "startxref".
    n_eof = crudo.count(b"%%EOF")
    n_xref = crudo.count(b"startxref")
    if n_eof == 1 and n_xref == 1:
        add("1.4", "Una sola revisión (sin cambios agregados)", OK,
            "Un solo bloque de cierre (%%EOF): el archivo no se modificó después de generarse.",
            "Cambios guardados encima del original (guardado incremental).")
    else:
        add("1.4", "Una sola revisión (sin cambios agregados)", FALLA,
            f"{n_eof} cierres %%EOF y {n_xref} tablas startxref: al archivo se le agregaron "
            "cambios después de generarse.",
            "Cambios guardados encima del original (guardado incremental).")

    # 1.5 — IDENTIFICADOR DEL DOCUMENTO. El PDF trae un /ID de dos partes:
    # la 1a se fija al crear el archivo y la 2a cambia cada vez que se
    # modifica. En la CSF original ambas son idénticas.
    ids = info["ids"]
    if len(ids) == 2 and ids[0] == ids[1]:
        add("1.5", "Identificador del PDF sin modificaciones", OK,
            "Las dos partes del /ID son idénticas (nunca se modificó).",
            "Archivo modificado después de su creación.")
    elif not ids:
        add("1.5", "Identificador del PDF sin modificaciones", FALLA,
            "El PDF no trae /ID. La CSF del SAT siempre lo trae: el archivo fue regenerado.",
            "Archivo regenerado por otro programa.")
    else:
        add("1.5", "Identificador del PDF sin modificaciones", FALLA,
            "Las dos partes del /ID son distintas: el archivo se modificó después de creado.",
            "Archivo modificado después de su creación.")

    # 1.6 — SIN ELEMENTOS AGREGADOS. La CSF solo tiene páginas. Formularios
    # (campos que se rellenan encima), anotaciones (cuadros de texto,
    # sellos, "tachones"), JavaScript o archivos incrustados son añadidos.
    raros = [k for k in info["claves_raiz"] if k not in ("/Type", "/Pages")]
    n_anot = sum(p["anotaciones"] for p in info["paginas"])
    peligrosos = [s for s in (b"/JavaScript", b"/JS", b"/OpenAction", b"/EmbeddedFile",
                              b"/AcroForm", b"/Launch") if s in crudo]
    if raros or n_anot or peligrosos:
        partes = []
        if raros:
            partes.append("catálogo con " + ", ".join(k[1:] for k in raros))
        if n_anot:
            partes.append(f"{n_anot} anotaciones (cuadros de texto/sellos encima)")
        if peligrosos:
            partes.append(", ".join(p.decode()[1:] for p in peligrosos))
        add("1.6", "Sin formularios, anotaciones ni código", FALLA, "; ".join(partes) + ".",
            "Texto sobrepuesto con anotaciones o formularios; PDFs con código.")
    else:
        add("1.6", "Sin formularios, anotaciones ni código", OK,
            "Sin anotaciones, formularios, JavaScript ni archivos incrustados.",
            "Texto sobrepuesto con anotaciones o formularios; PDFs con código.")

    # 1.7 — FUENTES. Para cambiar un dato, el editor necesita una fuente con
    # la que escribir el texto nuevo; casi siempre incrusta una distinta
    # (ArialMT, Calibri, una "Helvetica" incrustada, etc.).
    ajenas = set()
    for p in info["paginas"]:
        for base, incrustada in p["fuentes"]:
            nombre = base.split("+", 1)[-1]
            permitida = nombre in FUENTES_SAT
            if not permitida or (incrustada and nombre != "Noto Sans Medium"):
                ajenas.add(base + (" (incrustada)" if incrustada else ""))
    usadas = {c["fuente"].split("+", 1)[-1] for c in chars}
    ajenas |= {u for u in usadas if u not in FUENTES_SAT}
    if ajenas:
        add("1.7", "Solo fuentes de la plantilla del SAT", FALLA,
            "Fuentes ajenas a la plantilla: " + ", ".join(sorted(ajenas)) +
            ". Señal típica de texto reescrito.",
            "Datos reescritos con un editor de PDF (cambia la fuente).")
    else:
        add("1.7", "Solo fuentes de la plantilla del SAT", OK,
            "Solo " + ", ".join(sorted(usadas)) + ".",
            "Datos reescritos con un editor de PDF (cambia la fuente).")

    # 1.8 — FORMATO INTERNO. El SAT genera PDF 1.4 con UN flujo de contenido
    # por página. Las herramientas que "estampan" texto o imágenes encima
    # agregan un segundo flujo a la página.
    version = crudo[:8].decode("latin-1", "ignore")
    multiflujo = [i + 1 for i, p in enumerate(info["paginas"]) if p["n_contenidos"] != 1]
    formas = [n for n, (sub, *_r) in info["xobjetos"].items() if sub != "/Image"]
    problemas = []
    if version != "%PDF-1.4":
        problemas.append(f"versión {version[1:] or 'desconocida'} (el SAT usa PDF-1.4)")
    if multiflujo:
        problemas.append("páginas con contenido agregado: " + ", ".join(map(str, multiflujo)))
    if formas:
        problemas.append("objetos estampados (Form XObject): " + ", ".join(formas))
    if problemas:
        add("1.8", "Formato interno de la plantilla", FALLA, "; ".join(problemas) + ".",
            "Texto o imágenes estampados encima del original.")
    else:
        add("1.8", "Formato interno de la plantilla", OK,
            "PDF-1.4, un flujo de contenido por página, sin objetos estampados.",
            "Texto o imágenes estampados encima del original.")

    # 1.9 — TEXTO ENCIMADO U OCULTO. La forma más burda de alterar: tapar el
    # dato con un recuadro blanco y escribir otro encima, o escribir texto
    # sobre texto. Se buscan letras que ocupan el mismo lugar que otras, y
    # texto blanco (invisible) que quedó debajo.
    encimados = _caracteres_encimados(chars)
    blancos = [c for c in chars if _es_blanco(c["color"]) and c["texto"].strip()]
    if encimados or blancos:
        detalle = []
        if encimados:
            muestra = ", ".join(f"«{a}» sobre «{b}» (pág. {p + 1})" for p, a, b in encimados[:4])
            detalle.append(f"{len(encimados)} letras encimadas: {muestra}")
        if blancos:
            detalle.append(f"{len(blancos)} letras en color blanco (texto oculto): "
                           f"«{''.join(c['texto'] for c in blancos[:30])}»")
        add("1.9", "Sin texto encimado ni oculto", FALLA, "; ".join(detalle) + ".",
            "Datos tapados con un recuadro y reescritos encima.")
    else:
        add("1.9", "Sin texto encimado ni oculto", OK,
            "Ninguna letra se dibuja encima de otra ni hay texto invisible.",
            "Datos tapados con un recuadro y reescritos encima.")

    # 1.10 — UNIFORMIDAD TIPOGRÁFICA. Aunque el editor use "Helvetica", rara
    # vez atina al tamaño exacto ni a la misma línea base: un "8" cambiado
    # por un "9" queda 0.3 pt más arriba o en tamaño 7.9. Se revisa que
    # cada palabra tenga una sola fuente, un solo tamaño (de los que usa la
    # plantilla) y una línea base recta.
    raras = _palabras_irregulares(chars)
    if raras:
        add("1.10", "Tipografía uniforme en cada palabra", FALLA,
            f"{len(raras)} palabras con tamaño, fuente o alineación irregular: " +
            ", ".join(f"«{w}» (pág. {p + 1}: {m})" for p, w, m in raras[:5]) + ".",
            "Letras o números cambiados uno por uno.")
    else:
        add("1.10", "Tipografía uniforme en cada palabra", OK,
            "Cada palabra con una sola fuente, tamaño de plantilla y línea base recta.",
            "Letras o números cambiados uno por uno.")

    # 1.11 — IMÁGENES. La plantilla trae: encabezado, pie, logos, 2 QR de
    # 150×150 px y 1 código de barras de 35 px de alto. Los QR y el código
    # de barras son imágenes generadas (solo blanco y negro puros, sin
    # compresión JPG). Un QR "pegado" desde una captura o una foto trae grises
    # y artefactos; una imagen de más puede ser un parche que tapa un dato.
    qrs = [n for n, (_s, w, h, _f) in info["xobjetos"].items() if (w, h) == (150, 150)]
    barras = [n for n, (_s, w, h, _f) in info["xobjetos"].items() if h == 35 and w > 100]
    problemas = []
    if len(qrs) != 2:
        problemas.append(f"{len(qrs)} imágenes QR de 150×150 (deben ser 2)")
    if len(barras) != 1:
        problemas.append(f"{len(barras)} códigos de barras (debe ser 1)")
    if len(info["xobjetos"]) > 7:
        problemas.append(f"{len(info['xobjetos'])} imágenes en el archivo (la plantilla usa 7)")
    for im in info["imagenes"]:
        if im["nombre"].split(".")[0].lstrip("/") in {q.lstrip("/") for q in qrs + barras}:
            colores = _colores(im["pil"])
            if colores > 4:
                problemas.append(f"{im['nombre']} tiene {colores} tonos (un código generado tiene 2)")
    for n in qrs + barras:
        if "DCT" in info["xobjetos"][n][3]:
            problemas.append(f"{n} comprimido como JPG (el SAT lo guarda sin pérdida)")
    # Instancias dibujadas: cada QR y el código de barras se pintan UNA vez.
    dibujos = Counter(c["src"] for c in info["colocadas"] if c["src"] in ((150, 150),))
    if dibujos and dibujos[(150, 150)] != 2:
        problemas.append(f"los QR se dibujan {dibujos[(150, 150)]} veces (deben ser 2)")
    problemas = list(dict.fromkeys(problemas))
    if problemas:
        add("1.11", "Imágenes, QR y código de barras de origen", FALLA, "; ".join(problemas) + ".",
            "QR o código de barras sustituidos; parches de imagen sobre datos.")
    else:
        add("1.11", "Imágenes, QR y código de barras de origen", OK,
            "7 imágenes de plantilla; 2 QR y 1 código de barras nítidos (solo blanco y negro).",
            "QR o código de barras sustituidos; parches de imagen sobre datos.")

    # 1.13 — MAQUETACIÓN ORIGINAL. Es el candado contra la edición "fina":
    # la que cambia letras dentro del archivo sin dejar rastro en metadatos,
    # fuentes ni /ID. Oracle acomoda el texto UNA vez, con la longitud del
    # texto original:
    #   (a) La cédula y el "Lugar y Fecha de Emisión" van CENTRADOS. Si
    #       cambian "PEREZ" por "PERES" o "ABRIL" por "OCTUBRE", el renglón
    #       queda más largo o más corto pero su posición de inicio no se
    #       mueve: se descentra (basta 0.15 pt; el original da 0.00).
    #   (b) En las celdas, cada palabra se coloca a exactamente un espacio de
    #       la anterior. Cambiar "JULIO" por "MAYO" deja un hueco irregular.
    # Limitación honesta: un cambio por otra palabra del MISMO ancho exacto
    # (p. ej. un dígito por otro) no mueve nada. Para eso están el QR y el SAT.
    if info.get("maquetacion"):
        m = info["maquetacion"]
        add("1.13", "Maquetación original (centrado y espaciado)", FALLA,
            f"{len(m)} renglón(es) con el acomodo alterado: " +
            "; ".join(f"«{t[:45]}» pág. {p + 1}: {motivo}" for p, t, motivo in m[:4]) +
            ". El texto se cambió después de generarse.",
            "Edición fina de texto dentro del PDF (sin rastro en metadatos ni fuentes).")
    else:
        add("1.13", "Maquetación original (centrado y espaciado)", OK,
            "Textos centrados exactos y espaciado entre palabras idéntico al del motor del SAT.",
            "Edición fina de texto dentro del PDF (sin rastro en metadatos ni fuentes).")

    # 1.12 — PLANTILLA (informativo). El SAT tiene dos diseños vigentes: el
    # anterior (franja gris) y el de 2026 (franja guinda gob.mx, con Noto
    # Sans en el pie). Ambos son válidos.
    nueva = any("Noto Sans" in c["fuente"] for c in chars)
    add("1.12", "Plantilla reconocida", INFO,
        "Diseño gob.mx 2026 (franja guinda)." if nueva else "Diseño anterior (franja gris).", "")


def _es_blanco(color):
    if color is None:
        return False
    try:
        valores = list(color) if isinstance(color, (list, tuple)) else [color]
        if len(valores) == 4:   # CMYK
            return all(v <= 0.02 for v in valores)
        return all(float(v) >= 0.98 for v in valores)
    except Exception:
        return False


def _caracteres_encimados(chars):
    """Pares de letras visibles que ocupan casi el mismo lugar."""
    resultado = []
    cubetas = {}
    for c in chars:
        if not c["texto"].strip():
            continue
        clave = (c["pagina"], int(c["x0"] // 4), int(c["top"] // 4))
        cubetas.setdefault(clave, []).append(c)
    vistos = set()
    for (p, bx, by), _ in list(cubetas.items()):
        cercanos = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cercanos.extend(cubetas.get((p, bx + dx, by + dy), []))
        for i, a in enumerate(cercanos):
            for b in cercanos[i + 1:]:
                if a is b or (id(a), id(b)) in vistos or (id(b), id(a)) in vistos:
                    continue
                vistos.add((id(a), id(b)))
                ancho = min(a["x1"] - a["x0"], b["x1"] - b["x0"])
                alto = min(a["bottom"] - a["top"], b["bottom"] - b["top"])
                if ancho <= 0 or alto <= 0:
                    continue
                cx = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                cy = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
                if cx > 0.6 * ancho and cy > 0.6 * alto:
                    resultado.append((p, a["texto"], b["texto"]))
    return resultado


def _palabras_irregulares(chars):
    """Palabras (letras pegadas en la misma línea) con más de una fuente o
    tamaño, tamaños fuera de plantilla, o letras desalineadas."""
    raras = []
    por_linea = {}
    for c in chars:
        if not c["texto"].strip():
            continue
        por_linea.setdefault((c["pagina"], round(c["bottom"])), []).append(c)
    # Tamaños fuera de plantilla (aunque la palabra sea uniforme).
    fuera = {}
    for c in chars:
        if c["texto"].strip() and not any(abs(c["tam"] - t) < 0.15 for t in TAMANOS_SAT):
            fuera.setdefault(c["pagina"], []).append(c)
    for p, lista in fuera.items():
        raras.append((p, "".join(x["texto"] for x in lista[:20]),
                      "tamaño " + ", ".join(sorted({str(x["tam"]) for x in lista}))))
    for (p, _), lista in por_linea.items():
        lista.sort(key=lambda c: c["x0"])
        palabra = [lista[0]]
        for c in lista[1:] + [None]:
            if c is not None and c["x0"] - palabra[-1]["x1"] < 1.0:
                palabra.append(c)
                continue
            if len(palabra) > 1:
                fuentes = {(x["fuente"].split("+")[-1], x["tam"]) for x in palabra}
                bases = [x["bottom"] for x in palabra]
                texto = "".join(x["texto"] for x in palabra)
                if len(fuentes) > 1 and not _mezcla_legitima(palabra):
                    raras.append((p, texto, "mezcla " + " / ".join(f"{f} {t}" for f, t in sorted(fuentes))))
                elif max(bases) - min(bases) > 0.25:
                    raras.append((p, texto, f"desalineada {max(bases) - min(bases):.2f} pt"))
            palabra = [c] if c is not None else []
    return raras


def _mezcla_legitima(palabra):
    """En la plantilla, la etiqueta en negritas va pegada al valor normal
    ("Código Postal:28800", "Número Interior:38"). Eso NO es alteración:
    el cambio de fuente ocurre justo después de los dos puntos."""
    texto = "".join(x["texto"] for x in palabra)
    if ":" not in texto:
        return False
    corte = texto.index(":") + 1
    antes = {(x["fuente"].split("+")[-1], x["tam"]) for x in palabra[:corte]}
    despues = {(x["fuente"].split("+")[-1], x["tam"]) for x in palabra[corte:]}
    return len(antes) == 1 and len(despues) <= 1


def _colores(pil):
    try:
        colores = pil.convert("L").getcolors(maxcolors=256)
        return len(colores) if colores else 256
    except Exception:
        return 0


def _candados_codigos(info, d, add, analisis, consultar_sat):
    """SECCIÓN 2 — Los QR y el código de barras. Son el candado más fuerte:
    llevan al portal del SAT, que muestra los datos REALES del contribuyente.
    Un falsificador puede cambiar el texto, pero si deja el QR original, el
    QR delata el cambio; y si cambia el QR, tiene que apuntarlo a otro lado."""
    rfc = d["rfc"] or "(sin RFC legible)"
    leidos = []
    for im in info["imagenes"]:
        for fmt, txt in (_leer_codigos(im["pil"]) or []):
            leidos.append({"pagina": im["pagina"], "formato": fmt, "texto": txt, "img": im["nombre"]})
    qr =[x for x in leidos if x["formato"].upper().startswith("QR")]
    # Las imágenes de recursos se repiten en cada página; se deduplica.
    unicos = list(dict.fromkeys(x["texto"] for x in qr))
    barras = list(dict.fromkeys(x["texto"] for x in leidos if "128" in x["formato"]))
    sin_lector = _leer_codigos(_imagen_vacia()) is None

    parsed = [parse_qr_sat(u) for u in unicos]
    qr1 = next((p for p in parsed if p and p["D1"] == D1_QR_CEDULA), None)
    qr2 = next((p for p in parsed if p and p["D1"] == D1_QR_SELLO), None)
    analisis.urls_qr = unicos
    d["qr1"], d["qr2"] = qr1, qr2

    if sin_lector:
        add("2.1", "QR legibles", AVISO,
            "No está instalado el lector de códigos (pip install zxing-cpp). "
            "Escanea los QR con el celular.", "")
        return

    # 2.1 — Los dos QR existen y se pueden leer.
    if len(unicos) == 2 and qr1 and qr2:
        add("2.1", "Dos QR legibles", OK, "Se leyeron el QR de la cédula y el QR del sello.",
            "QR borrados, dañados o sustituidos por imágenes que no son QR.")
    else:
        add("2.1", "Dos QR legibles", FALLA,
            f"Se leyeron {len(unicos)} QR, pero " + (
                "el de la cédula" if not qr1 else "el del sello") +
            " no tiene el formato del validador del SAT (D1=10 cédula, D1=26 sello).",
            "QR borrados, dañados o sustituidos por imágenes que no son QR.")

    # 2.2 — DOMINIO OFICIAL. Ambos QR deben llevar EXACTAMENTE a
    # https://siat.sat.gob.mx/... No basta con "contiene sat": dominios como
    # siat.sat.gob.mx.validar.com o sat-gob-mx.site son páginas clonadas que
    # muestran datos falsos para que la constancia "valide".
    malos = []
    for p in parsed:
        if not p:
            continue
        if p["esquema"] != "https" or p["dominio"] != DOMINIO_QR or p["ruta"] != RUTA_QR:
            pista = next((f" [{q}: cualquiera puede publicar ahí gratis]"
                          for suf, q in HOSTING_GRATUITO.items() if p["dominio"].endswith(suf)), "")
            malos.append(f"{p['esquema']}://{p['dominio']}{p['ruta']}{pista}")
        elif p["extra"]:
            malos.append(f"parámetros extra {p['extra']}")
    if malos:
        add("2.2", "QR apuntan al portal oficial del SAT", FALLA,
            "Dirección no oficial: " + "; ".join(malos) + f". Debe ser https://{DOMINIO_QR}{RUTA_QR}.",
            "QR que llevan a una página clonada del SAT.")
    elif parsed:
        add("2.2", "QR apuntan al portal oficial del SAT", OK,
            f"Ambos llevan a https://{DOMINIO_QR} (validador oficial).",
            "QR que llevan a una página clonada del SAT.")

    # 2.3 — QR 1 (cédula) = idCIF y RFC impresos. El QR de la cédula lleva
    # D3 = idCIF_RFC. Si cambiaron el RFC o el idCIF impresos pero no el QR
    # (o al revés), aquí no cuadra.
    if qr1:
        errores = []
        if qr1["rfc"] != rfc:
            errores.append(f"RFC del QR {qr1['rfc']} ≠ impreso {rfc}")
        if d["idcif"] and qr1["folio"] != d["idcif"]:
            errores.append(f"idCIF del QR {qr1['folio']} ≠ impreso {d['idcif']}")
        if qr1["D2"] != "1":
            errores.append(f"D2={qr1['D2']} (esperado 1)")
        add("2.3", "QR de la cédula = RFC e idCIF impresos", FALLA if errores else OK,
            "; ".join(errores) + "." if errores else
            f"QR: idCIF {qr1['folio']} y RFC {qr1['rfc']}, iguales a los impresos.",
            "Cambio de RFC/idCIF en el texto conservando el QR de otra persona.")

    # 2.4 — QR 2 (sello) = RFC impreso. Corresponde al paso 3 del boletín:
    # el 2do QR y la cadena original deben hablar del mismo RFC.
    if qr2:
        ok = qr2["rfc"] == rfc and qr2["folio"].isdigit() and qr2["D2"] == "1"
        add("2.4", "QR del sello = RFC impreso", OK if ok else FALLA,
            f"QR del sello: folio {qr2['folio']}, RFC {qr2['rfc']}." if ok else
            f"QR del sello trae RFC {qr2['rfc'] or '—'} / folio {qr2['folio'] or '—'}; el impreso es {rfc}.",
            "Constancia armada con el sello de otra persona.")

    # 2.5 — CÓDIGO DE BARRAS. Bajo "Lugar y Fecha de Emisión" va un Code 128
    # con el RFC. Pocos falsificadores lo regeneran.
    if barras:
        ok = barras[0] == rfc
        add("2.5", "Código de barras = RFC", OK if ok else FALLA,
            f"Código de barras: {barras[0]}" + ("." if ok else f" ≠ RFC impreso {rfc}."),
            "Cambio de RFC sin regenerar el código de barras.")
    else:
        add("2.5", "Código de barras = RFC", FALLA,
            "No se pudo leer el código de barras del RFC.",
            "Cambio de RFC sin regenerar el código de barras.")

    # 2.6 — LO QUE SE VE = LO QUE TRAE ADENTRO. Se "imprime" la página como
    # imagen y se escanea, igual que haría un celular. Si alguien pegó un QR
    # encima del original (otra imagen, otra capa), el que se ve no es el
    # incrustado.
    if info.get("render_error"):
        add("2.6", "QR visibles = QR incrustados", INFO,
            "No se pudo renderizar la página para escanearla.", "")
    else:
        vistos = {x["texto"] for x in info["render_codigos"] if x["formato"].upper().startswith("QR")}
        vistos_b = {x["texto"] for x in info["render_codigos"] if "128" in x["formato"]}
        # El código de barras renderizado no siempre se alcanza a leer; solo
        # cuenta si se LEE y dice otra cosa.
        if vistos == set(unicos) and (not vistos_b or not barras or vistos_b == set(barras)):
            add("2.6", "QR visibles = QR incrustados", OK,
                "Al escanear la página se leen exactamente los mismos códigos.",
                "QR falso pegado encima del original.")
        else:
            add("2.6", "QR visibles = QR incrustados", FALLA,
                f"Al escanear la página se ven {len(vistos)} QR distintos a los incrustados.",
                "QR falso pegado encima del original.")

    # 2.7 — CONSULTA EN LÍNEA: el script abre el 1er QR en el SAT y compara
    # CURP, nombre, situación, inicio de operaciones, CP, entidad y régimen.
    # Si el servidor no alcanza al SAT (servidores fuera de México, conexión
    # segura rechazada) queda como INFO con el motivo, y toca hacerlo a mano.
    if consultar_sat and qr1 and not malos:
        add("2.7", "Consulta al portal del SAT", *_consultar_sat(qr1, d))


def _imagen_vacia():
    from PIL import Image
    return Image.new("L", (8, 8), 255)


# Cifrados con los que el servidor del SAT acepta la conexión. Con los que
# trae Python por default (OpenSSL 3) el saludo TLS con siat.sat.gob.mx
# puede fallar y urllib solo dice "URLError". Es la misma lista que usa la
# librería satcfdi (github.com/SAT-CFDI/python-satcfdi) para hablar con el SAT.
# Solo cambia los cifrados: el certificado del SAT SÍ se verifica.
CIFRADOS_SAT = ("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:ECDH+AESGCM:"
                "DH+AESGCM:ECDH+AES:DH+AES:RSA+AESGCM:RSA+AES:!aNULL:!eNULL:!MD5:!DSS:HIGH:!DH")


class _PaginaSAT(HTMLParser):
    """Lee la ficha del validador del SAT: las etiquetas van en
    <span style="font-weight: bold;"> y los valores en
    <td role="gridcell" style="text-align:left;">, en el mismo orden."""

    def __init__(self):
        super().__init__()
        self.etiquetas, self.valores, self._en = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        estilo = (a.get("style") or "").replace(" ", "").lower()
        if tag == "span" and "font-weight:bold" in estilo:
            self._en, self._buf = "etq", []
        elif tag == "td" and a.get("role") == "gridcell" and "text-align:left" in estilo:
            self._en, self._buf = "val", []

    def handle_data(self, data):
        if self._en:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._en == "etq" and tag == "span":
            self.etiquetas.append(re.sub(r"\s+", " ", "".join(self._buf)).strip().rstrip(":"))
            self._en = None
        elif self._en == "val" and tag == "td":
            self.valores.append(re.sub(r"\s+", " ", "".join(self._buf)).strip())
            self._en = None


def leer_pagina_sat(pagina_html):
    """{etiqueta normalizada: [valores]} de la ficha del SAT (puede haber
    varios 'Régimen' y 'Fecha de alta')."""
    p = _PaginaSAT()
    p.feed(pagina_html)
    campos = {}
    for k, v in zip(p.etiquetas, p.valores):
        campos.setdefault(_norm(k), []).append(v)
    return campos


def _descargar_sat(url, timeout=10):
    import ssl
    contexto = ssl.create_default_context()
    try:
        contexto.set_ciphers(CIFRADOS_SAT)
    except ssl.SSLError:
        pass
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "es-MX,es"})
    with urllib.request.urlopen(req, timeout=timeout, context=contexto) as r:
        return r.read(600_000).decode("utf-8", "ignore")


def _motivo(e):
    """El motivo real dentro de un URLError (antes solo se veía 'URLError')."""
    import socket
    import ssl
    razon = getattr(e, "reason", e)
    if isinstance(razon, ssl.SSLCertVerificationError):
        return "el certificado del SAT no se pudo verificar desde este servidor"
    if isinstance(razon, ssl.SSLError):
        return f"falló la conexión segura con el SAT ({getattr(razon, 'reason', None) or razon})"
    if isinstance(razon, (socket.timeout, TimeoutError)) or "timed out" in str(razon):
        return "el SAT no respondió a tiempo (suele bloquear servidores fuera de México)"
    if isinstance(e, urllib.error.HTTPError):
        return f"el SAT respondió con error HTTP {e.code}"
    return f"{type(razon).__name__}: {razon}"


def _consultar_sat(qr1, d):
    """2.7 — Lo que pide el paso 2 del boletín, hecho por el script: abrir
    el 1er QR y comparar la ficha del SAT contra el documento. Si el
    servidor no alcanza al SAT, se dice POR QUÉ y se deja como INFO."""
    try:
        pagina = _descargar_sat(qr1["url"])
    except Exception as e:
        return (INFO, f"No se pudo consultar desde el servidor: {_motivo(e)}. "
                      "Abre el link del QR y compara a mano.", "")

    sat = leer_pagina_sat(html.unescape(pagina))
    if not sat:
        # PASABLE (AVISO): o el idCIF/RFC no existe, o el SAT cambió su página
        # o tuvo una falla. No se puede distinguir desde aquí.
        return (AVISO, "El portal del SAT respondió SIN ficha para el idCIF y RFC de este QR. "
                       "Puede ser que no existan o una falla del SAT: abre el link y revisa.",
                "Constancias inventadas.")
    g = lambda *ks: next((sat[_norm(k)][0] for k in ks if sat.get(_norm(k))), "")  # noqa: E731

    comparaciones = []          # (campo, documento, SAT)
    if d["tipo"] == "fisica":
        comparaciones += [("CURP", d["curp"], g("CURP")),
                          ("Nombre", " ".join(x for x in (d["nombres"], d["paterno"], d["materno"]) if x),
                           " ".join(x for x in (g("Nombre"), g("Apellido Paterno"), g("Apellido Materno")) if x))]
    else:
        comparaciones.append(("Razón social", d["razon_social"],
                              g("Denominación o Razón Social", "Denominación/Razón Social", "Razón Social")))
    comparaciones += [
        ("Situación", d["estatus"], g("Situación del contribuyente", "Situación")),
        ("Inicio de operaciones", _fmt(_fecha_texto(d["inicio_operaciones"])),
         _fmt(_fecha_texto(g("Fecha de Inicio de operaciones", "Fecha inicio de operaciones").replace("-", "/")))),
        ("Código postal", d["cp"], g("CP", "Código Postal")),
        ("Entidad", d["entidad"], g("Entidad Federativa")),
    ]
    regs_sat = {_compacto(r) for r in sat.get(_norm("Régimen"), [])}
    regs_doc = {_compacto(r["regimen"]) for r in d["regimenes"]}
    if regs_sat or regs_doc:
        comparaciones.append(("Régimen", "; ".join(sorted(regs_doc)), "; ".join(sorted(regs_sat))))

    # El SAT muestra los datos de HOY y la constancia los del día en que se
    # emitió. Situación, domicilio y régimen pueden haber cambiado entre una
    # fecha y otra (PASABLE = AVISO). CURP, nombre e inicio de operaciones
    # no cambian: si difieren, el documento se alteró (FALLA).
    mutables = {"Situación", "Código postal", "Entidad", "Régimen"}
    distintos, cambiaron, revisados = [], [], []
    for campo, doc, en_sat in comparaciones:
        if not en_sat or doc in ("", "—"):
            continue            # el SAT no mostró ese campo: no se puede comparar
        revisados.append(campo)
        if _compacto(doc) != _compacto(en_sat):
            texto = (f"{campo}: documento «{doc}» / SAT «{en_sat}»"
                     if campo != "Régimen" else "Régimen distinto al registrado hoy en el SAT")
            (cambiaron if campo in mutables else distintos).append(texto)
    if distintos:
        return (FALLA, "Lo que dice el SAT no coincide con el documento — " +
                "; ".join(distintos + cambiaron) + ".", "Datos cambiados en el texto de la constancia.")
    if cambiaron:
        return (AVISO, "Coinciden " + ", ".join(c for c in revisados if c not in mutables) +
                ", pero hoy el SAT muestra otro dato — " + "; ".join(cambiaron) +
                ". Pudo cambiar después de emitida; pide una CSF reciente.",
                "Datos cambiados en el texto de la constancia.")
    if not revisados:
        return (AVISO, "El SAT respondió, pero no se reconocieron sus campos. Abre el link del QR "
                       "y compara a mano.", "")
    return (OK, "Consultado en el portal del SAT: coinciden " + ", ".join(revisados) + ".",
            "Datos cambiados en el texto de la constancia.")


def _candados_datos(d, add, hoy):
    """SECCIÓN 3 — Coherencia de los datos. Una constancia fabricada (a mano
    o con IA) "se ve" bien, pero sus datos no cumplen las reglas con que el
    SAT y RENAPO los forman. Aquí se cruzan unos contra otros."""
    rfc, curp, tipo = d["rfc"], d["curp"], d["tipo"]

    # 3.1 — RFC: formato y dígito verificador.
    patron = PAT_RFC_MORAL if len(rfc) == 12 else PAT_RFC_FISICA
    if not rfc:
        add("3.1", "RFC válido (formato y dígito verificador)", FALLA,
            "No se encontró el RFC en la tabla de identificación.", "")
    elif not patron.match(rfc):
        add("3.1", "RFC válido (formato y dígito verificador)", FALLA,
            f"{rfc} no tiene formato de RFC.", "RFC inventado o mal capturado.")
    elif rfc.startswith(("XAXX", "XEXX")):
        add("3.1", "RFC válido (formato y dígito verificador)", FALLA,
            f"{rfc} es un RFC genérico, no de un contribuyente.", "RFC genérico.")
    else:
        dv = digito_rfc(rfc)
        add("3.1", "RFC válido (formato y dígito verificador)", OK if dv == rfc[-1] else FALLA,
            f"Dígito verificador {rfc[-1]} correcto." if dv == rfc[-1] else
            f"El último carácter debería ser {dv}, no {rfc[-1]}: el RFC no existe así.",
            "RFC inventado o con un carácter cambiado.")

    # 3.2 — TIPO DE PERSONA. Persona física: RFC de 13 y CURP + apellidos.
    # Persona moral: RFC de 12 y razón social. Mezclarlos es típico de una
    # constancia "armada" con partes de dos documentos.
    esperado = {12: "moral", 13: "fisica"}.get(len(rfc))
    if tipo and esperado and tipo != esperado:
        add("3.2", "Tipo de persona coherente con el RFC", FALLA,
            f"El RFC es de persona {esperado} ({len(rfc)} caracteres) pero el documento trae datos "
            f"de persona {tipo}.", "Constancia armada con partes de dos documentos.")
    else:
        add("3.2", "Tipo de persona coherente con el RFC", OK if tipo else AVISO,
            f"Persona {'moral' if tipo == 'moral' else 'física'} con RFC de {len(rfc)} caracteres."
            if tipo else "No se identificó el tipo de persona.",
            "Constancia armada con partes de dos documentos.")

    # 3.3 — CURP (solo física): formato, dígito verificador y que su fecha y
    # letras sean las del RFC. RFC y CURP se calculan con la misma fecha de
    # nacimiento: si no coinciden, uno de los dos se cambió.
    if tipo == "fisica":
        errores, avisos = [], []
        if not PAT_CURP.match(curp or ""):
            errores.append(f"CURP «{curp or 'vacía'}» sin formato válido")
        else:
            if digito_curp(curp) != curp[-1]:
                errores.append(f"dígito verificador de la CURP debería ser {digito_curp(curp)}")
            if curp[11:13] not in ENTIDADES_CURP:
                errores.append(f"entidad de nacimiento {curp[11:13]} no existe")
            if not _fecha_aammdd(curp[4:10], hoy):
                errores.append("fecha de nacimiento de la CURP inválida")
            # PASABLE: RFC y CURP salen de la misma fecha de nacimiento, pero
            # hay RFC antiguos dados de alta con la fecha mal capturada que el
            # SAT nunca corrigió. Fuerte indicio, no prueba: AVISO.
            if rfc and curp[4:10] != rfc[4:10]:
                avisos.append(f"fecha del RFC ({rfc[4:10]}) ≠ fecha de la CURP ({curp[4:10]}); "
                              "puede ser un error de captura antiguo del SAT, confirma en el QR")
            if rfc and curp[:4] != rfc[:4]:
                avisos.append(f"letras del RFC ({rfc[:4]}) ≠ de la CURP ({curp[:4]})")
        estado = FALLA if errores else (AVISO if avisos else OK)
        add("3.3", "CURP válida y coherente con el RFC", estado,
            "; ".join(errores + avisos) + "." if errores or avisos else
            f"CURP con dígito correcto; misma fecha y letras que el RFC ({rfc[:10]}).",
            "CURP o RFC cambiados; datos de dos personas mezclados.")

    # 3.4 — NOMBRE. (a) El nombre de la cédula (junto al QR) es el mismo que
    # el de la tabla: al editar se suele olvidar uno de los dos. (b) Las
    # letras del RFC salen del nombre: si cambian el nombre, ya no cuadran.
    # (b) tiene excepciones legítimas, por eso solo es AVISO.
    errores, avisos = [], []
    if d["cedula_nombre"] and d["nombre_completo"] and \
            _compacto(d["cedula_nombre"]) != _compacto(d["nombre_completo"]):
        errores.append(f"cédula dice «{d['cedula_nombre']}» y la tabla «{d['nombre_completo']}»")
    if d["cedula_rfc"] and rfc and _compacto(d["cedula_rfc"]) != rfc:
        errores.append(f"RFC de la cédula {d['cedula_rfc']} ≠ tabla {rfc}")
    if tipo == "fisica":
        esperado_l = letras_rfc_fisica(d["paterno"], d["materno"], d["nombres"])
        if esperado_l and rfc and esperado_l != rfc[:4]:
            avisos.append(f"por el nombre, el RFC empezaría con {esperado_l} y empieza con {rfc[:4]}")
    elif tipo == "moral":
        esperado_l = letras_rfc_moral(d["razon_social"])
        if esperado_l and rfc and esperado_l != rfc[:3]:
            avisos.append(f"por la razón social, el RFC empezaría con {esperado_l} y empieza con {rfc[:3]}")
    estado = FALLA if errores else (AVISO if avisos else OK)
    add("3.4", "Nombre consistente (cédula, tabla y RFC)", estado,
        "; ".join(errores + avisos) + (" (puede ser una excepción del SAT; confirma en el QR)."
                                       if avisos and not errores else ".")
        if errores or avisos else "El nombre coincide en cédula y tabla y corresponde a las letras del RFC.",
        "Cambio del nombre del titular.")

    # 3.5 — FECHAS.
    #   FALLA (imposible en una CSF real): inicio de operaciones o último
    #   cambio de estado POSTERIORES a la fecha de emisión.
    #   PASABLE (AVISO): un régimen, actividad u obligación con inicio
    #   posterior a la emisión (un cambio de régimen se presenta antes y
    #   "surte efectos" después, p. ej. el 1 de enero siguiente).
    #   NO SE REVISA: que el último cambio de estado sea anterior al inicio de
    #   operaciones. Es normal: alguien se inscribe al RFC (o lo inscribe un
    #   patrón) años antes de empezar a tener obligaciones; ese "cambio de
    #   estado" es la inscripción. Así viene en CSF auténticas.
    emision = d["fecha_emision"]
    inicio = _fecha_texto(d["inicio_operaciones"])
    cambio = _fecha_texto(d["ultimo_cambio"])
    errores, avisos = [], []
    if not emision:
        errores.append("no se pudo leer la fecha de emisión")
    for etq, f in (("inicio de operaciones", inicio), ("último cambio de estado", cambio)):
        if f and emision and f > emision:
            errores.append(f"{etq} ({_fmt(f)}) posterior a la emisión")
    for grupo, clave in (("regimenes", "regimen"), ("actividades", "actividad"), ("obligaciones", "obligacion")):
        for x in d[grupo]:
            f = _fecha_texto(x.get("inicio", ""))
            if f and emision and f > emision:
                avisos.append(f"{clave} con inicio {_fmt(f)} posterior a la emisión (posible cambio "
                              "programado; confirma en el QR)")
    if tipo == "moral" and rfc and inicio:
        f_rfc = _fecha_aammdd(rfc[3:9], hoy)
        if f_rfc and f_rfc != inicio:
            avisos.append(f"fecha del RFC ({_fmt(f_rfc)}) distinta al inicio de operaciones "
                          f"({_fmt(inicio)}); es posible si inició después de constituirse")
    if tipo == "fisica" and rfc and inicio:
        nacimiento = _fecha_aammdd(rfc[4:10], hoy)
        if nacimiento and (inicio - nacimiento).days < 365 * 15:
            avisos.append(f"inicio de operaciones a los {(inicio - nacimiento).days // 365} años de edad")
    estado = FALLA if errores else (AVISO if avisos else OK)
    add("3.5", "Fechas coherentes entre sí", estado,
        "; ".join(errores + avisos) + "." if errores or avisos else
        f"Inicio {_fmt(inicio)}, último cambio {_fmt(cambio)}, emisión {_fmt(emision)}: en orden.",
        "Fechas alteradas (antigüedad, estatus) o constancia inventada.")

    # 3.6 — ACTIVIDADES. Las actividades VIGENTES (sin fecha fin) suman 100 %.
    # Una IA o una edición manual de la tabla suele romperlo. PASABLE (AVISO):
    # una tabla partida entre páginas o una actividad dada de baja pueden
    # hacer que la lectura no cuadre aunque el documento sea auténtico.
    vigentes = [a for a in d["actividades"] if not str(a.get("fin") or "").strip()]
    if vigentes:
        try:
            suma = sum(float(str(a["porcentaje"]).strip() or 0) for a in vigentes)
        except ValueError:
            suma = -1
        add("3.6", "Porcentajes de actividades suman 100", OK if abs(suma - 100) < 0.01 else AVISO,
            f"Suman {suma:g}% en {len(vigentes)} actividad(es) vigente(s).",
            "Tabla de actividades editada o inventada.")
    else:
        add("3.6", "Porcentajes de actividades suman 100", AVISO,
            "No se encontró la tabla de actividades económicas.", "")

    # 3.7 — RÉGIMEN acorde al tipo de persona. "Sueldos y Salarios" en una
    # persona moral, o "General de Ley Personas Morales" en una física, no
    # existen. Igual con las obligaciones "Personas Morales" en una física.
    regs = [_norm(r["regimen"]) for r in d["regimenes"]]
    obls = [_norm(o["obligacion"]) for o in d["obligaciones"]]
    # FALLA: un RÉGIMEN que no existe para ese tipo de persona.
    # PASABLE (AVISO): una OBLIGACIÓN que menciona al otro tipo (hay
    # obligaciones de retención o informativas cuyo texto nombra a "personas
    # morales" aunque las tenga una física).
    errores, avisos = [], []
    if tipo == "moral":
        errores += [r for r in regs if any(x in r for x in REGIMENES_SOLO_FISICA)]
        avisos += [o for o in obls if "PERSONAS FISICAS" in o]
    elif tipo == "fisica":
        errores += [r for r in regs if any(x in r for x in REGIMENES_SOLO_MORAL)]
        avisos += [o for o in obls if "PERSONAS MORALES" in o]
    persona = "moral" if tipo == "moral" else "física"
    if not regs:
        add("3.7", "Régimen acorde al tipo de persona", AVISO, "No se encontró la tabla de regímenes.", "")
    else:
        add("3.7", "Régimen acorde al tipo de persona", FALLA if errores else (AVISO if avisos else OK),
            (f"Régimen que no existe para persona {persona}: " +
             "; ".join(e.title() for e in errores) + ".") if errores else
            ("Obligación que menciona al otro tipo de persona: " +
             "; ".join(o.title() for o in avisos) + " (puede ser legítima; confirma en el QR).")
            if avisos else "; ".join(r.title() for r in regs) + ".",
            "Régimen cambiado para aparentar otro perfil de ingresos.")

    # 3.8 — DOMICILIO. El código postal tiene 5 dígitos y sus dos primeros
    # corresponden a la entidad (Colima 28xxx, Jalisco 44–49xxx, ...).
    # PASABLE (AVISO): SEPOMEX tiene códigos en zonas limítrofes que no
    # siguen la regla por entidad.
    cp, ent = d["cp"], d["entidad"]
    coincide = cp_coincide_entidad(cp, ent)
    if coincide is None:
        add("3.8", "Código postal corresponde a la entidad", AVISO,
            f"No se pudo validar CP «{cp}» / entidad «{ent}».", "Domicilio cambiado.")
    else:
        add("3.8", "Código postal corresponde a la entidad", OK if coincide else AVISO,
            f"CP {cp} pertenece a {ent.title()}." if coincide else
            f"El CP {cp} no pertenece a {ent.title()}.", "Domicilio cambiado o inventado.")

    # 3.9 — CADENA ORIGINAL (paso 3 del boletín). Formato:
    #   ||AAAA/MM/DD HH:MM:SS|RFC|CONSTANCIA DE SITUACIÓN FISCAL|<certificado>|<cifrado>||
    # La fecha debe ser la de emisión y el RFC el del documento. El último
    # bloque es un cifrado OpenSSL ("Salted__" + sal + 32 bytes): un texto
    # inventado por una persona o una IA no tiene esa estructura binaria.
    cad = d["cadena"]
    m = re.match(r"^\|\|(\d{4})/(\d{2})/(\d{2}) ?(\d{2}):(\d{2}):(\d{2})\|([A-ZÑ&0-9]{12,13})\|"
                 r"CONSTANCIA ?DE ?SITUACI[OÓ]N ?FISCAL\|(\d+)\|([A-Za-z0-9+/=]+)\|\|$", cad)
    errores, avisos = [], []
    if not m:
        errores.append("la cadena original no tiene el formato del SAT" if cad else "no se encontró la cadena original")
    else:
        try:
            f_cad = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            f_cad = None
        if m.group(7) != rfc:
            errores.append(f"RFC de la cadena {m.group(7)} ≠ {rfc}")
        if emision and f_cad != emision:
            errores.append(f"fecha de la cadena {_fmt(f_cad)} ≠ emisión {_fmt(emision)}")
        if m.group(8) != CERTIFICADO_SAT:
            avisos.append(f"certificado {m.group(8)} distinto al habitual ({CERTIFICADO_SAT})")
        try:
            b = base64.b64decode(m.group(9), validate=True)
            if not (b.startswith(b"Salted__") and len(b) >= 32 and (len(b) - 16) % 16 == 0):
                errores.append("el bloque cifrado no tiene la estructura del SAT")
        except Exception:
            errores.append("el bloque cifrado no es base64 válido")
    estado = FALLA if errores else (AVISO if avisos else OK)
    add("3.9", "Cadena original: fecha y RFC (paso 3 del boletín)", estado,
        "; ".join(errores + avisos) + "." if errores or avisos else
        f"Fecha {_fmt(emision)} y RFC {rfc} coinciden; bloque cifrado con estructura válida.",
        "Cadena copiada de otra constancia o inventada.")

    # 3.10 — SELLO DIGITAL. Firma RSA de 1024 bits codificada en base64:
    # exactamente 128 bytes. Un sello inventado o recortado no da 128.
    try:
        n = len(base64.b64decode(d["sello"], validate=True)) if d["sello"] else 0
    except Exception:
        n = -1
    add("3.10", "Sello digital con estructura válida", OK if n == 128 else FALLA,
        "Firma de 128 bytes (RSA-1024), como la del SAT." if n == 128 else
        ("No se encontró el sello digital." if n == 0 else
         f"El sello {'no es base64 válido' if n < 0 else f'mide {n} bytes'} (deben ser 128)."),
        "Sello copiado, recortado o inventado.")

    # 3.11 — LUGAR DE EMISIÓN (informativo). El SAT pone el municipio y
    # estado del domicilio fiscal. Si no coincide, solo es una nota.
    lugar = d["lugar_emision"]
    if lugar and d["municipio"]:
        coincide = _compacto(d["municipio"]) in _compacto(lugar) and \
            (not d["entidad"] or _compacto(entidad_de_texto(d["entidad"]) or d["entidad"]) in _compacto(lugar))
        add("3.11", "Lugar de emisión = domicilio fiscal", INFO,
            f"Emitida en {lugar.title()}; domicilio en {d['municipio'].title()}, {d['entidad'].title()}"
            + ("." if coincide else " (no coinciden; revisa en el QR)."), "")


def _candados_politicas(d, add, hoy):
    """SECCIÓN 4 — Requisitos de la financiera. No indican alteración: una
    CSF vieja es auténtica, pero no sirve para el expediente."""
    emision = d["fecha_emision"]
    # 4.1 — VIGENCIA (paso 1 del boletín): emitida en el último mes.
    if not emision:
        add("4.1", f"Emitida en los últimos {DIAS_VIGENCIA} días", FALLA, "Sin fecha de emisión legible.", "")
    elif emision > hoy:
        add("4.1", f"Emitida en los últimos {DIAS_VIGENCIA} días", FALLA,
            f"Fecha de emisión {_fmt(emision)} en el FUTURO: imposible en una CSF real.",
            "Fecha alterada.")
    else:
        dias = (hoy - emision).days
        add("4.1", f"Emitida en los últimos {DIAS_VIGENCIA} días", OK if dias <= DIAS_VIGENCIA else AVISO,
            f"Emitida el {_fmt(emision)} (hace {dias} días)." +
            ("" if dias <= DIAS_VIGENCIA else " Pide al cliente una constancia reciente."),
            "Constancias viejas que ya no reflejan la situación actual.")

    # 4.2 — ESTATUS EN EL PADRÓN: ACTIVO. Suspendido, cancelado o "no
    # localizado" no es apto para crédito.
    # REACTIVADO = volvió a estar activo después de una suspensión: es apto,
    # pero conviene saber que hubo suspensión.
    est = _norm(d["estatus"])
    if est == "REACTIVADO":
        add("4.2", "Estatus en el padrón: ACTIVO", OK,
            f"Estatus: REACTIVADO (activo de nuevo; estuvo suspendido, último cambio "
            f"{d['ultimo_cambio'] or '—'}).", "Contribuyentes suspendidos o cancelados.")
    else:
        add("4.2", "Estatus en el padrón: ACTIVO", OK if est == "ACTIVO" else FALLA,
            f"Estatus: {d['estatus'] or 'no encontrado'}.", "Contribuyentes suspendidos o cancelados.")


# ===========================================================================
#  ANÁLISIS COMPLETO
# ===========================================================================
EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tif", ".tiff")


def analizar_csf(ruta, hoy=None, consultar_sat=False, nombre=None):
    """Corre todos los candados sobre un archivo. Nunca lanza excepción por
    un PDF raro: cualquier error de lectura se reporta como FALLA."""
    hoy = hoy or _hoy()
    crudo = open(ruta, "rb").read()
    analisis = Analisis(archivo=nombre or os.path.basename(ruta),
                        sha256=hashlib.sha256(crudo).hexdigest(),
                        tipo_archivo="pdf" if crudo[:5] == b"%PDF-" else "imagen")

    def add(clave, titulo, estado, detalle, previene=""):
        analisis.candados.append(Candado(clave, titulo, estado, detalle, previene))

    # Foto o captura: solo se pueden leer los QR (y mandar a validar al SAT).
    if analisis.tipo_archivo == "imagen" or ruta.lower().endswith(EXT_IMAGEN):
        analisis.tipo_archivo = "imagen"
        _analizar_imagen(ruta, analisis, add)
        return analisis

    try:
        info = _extraer_pdf(ruta)
    except Exception as e:
        add("1.1", "PDF legible", FALLA,
            f"El archivo no se pudo leer como PDF ({type(e).__name__}: {e}). Puede estar dañado "
            "o protegido; pide el PDF original del SAT.", "")
        return analisis
    if info.get("cifrado"):
        add("1.0", "PDF sin contraseña ni cifrado", FALLA,
            "El PDF está cifrado. La CSF del SAT nunca lo está.", "Archivos protegidos para evitar revisión.")

    d = _extraer_datos(info)
    analisis.datos = d
    _candados_estructura(info, add)
    _candados_codigos(info, d, add, analisis, consultar_sat)
    _candados_datos(d, add, hoy)
    _candados_politicas(d, add, hoy)
    analisis.candados.sort(key=lambda c: tuple(int(x) for x in c.clave.split(".")))
    return analisis


def _analizar_imagen(ruta, analisis, add):
    from PIL import Image
    try:
        img = Image.open(ruta)
        img.load()
    except Exception as e:
        add("1.1", "Archivo legible", FALLA, f"No se pudo abrir la imagen ({e}).", "")
        return
    add("1.1", "PDF con capa de texto (no foto ni escaneo)", FALLA,
        "Es una imagen (foto/captura/escaneo). Una imagen no se puede validar técnicamente: "
        "puede estar editada o generada con IA. Pide el PDF original descargado del SAT.",
        "Constancias fotografiadas, editadas como imagen o generadas con IA.")
    codigos = _leer_codigos(img) or []
    qrs = [parse_qr_sat(t) for f, t in codigos if f.upper().startswith("QR")]
    analisis.urls_qr = [q["url"] for q in qrs if q]
    if not qrs:
        add("2.1", "QR legibles", AVISO, "No se pudo leer ningún QR en la imagen.", "")
    for i, q in enumerate(q for q in qrs if q):
        ok = q["esquema"] == "https" and q["dominio"] == DOMINIO_QR and q["ruta"] == RUTA_QR
        add(f"2.{i + 2}", f"QR {i + 1} apunta al portal oficial", OK if ok else FALLA,
            f"{q['dominio']}{q['ruta']} · RFC {q['rfc']}" + ("" if ok else " — dirección NO oficial."),
            "QR hacia página clonada del SAT.")


def analizar_lote(rutas, hoy=None, consultar_sat=False, nombres=None):
    """Analiza varios archivos y agrega el candado de lote: dos constancias
    DISTINTAS no pueden compartir sello, cadena ni idCIF. Si comparten, una
    se fabricó a partir de la otra."""
    resultados = [analizar_csf(r, hoy, consultar_sat, (nombres or [None] * len(rutas))[i])
                  for i, r in enumerate(rutas)]
    # 3.12 — CANDADO DE LOTE. El sello, la cadena y el idCIF+folio son
    # irrepetibles. Si dos archivos DIFERENTES (otro contenido) los
    # comparten, uno es copia alterada del otro. El script no puede saber
    # cuál es el bueno: marca a ambos.
    if len(resultados) > 1:
        compartidos = {id(a): {} for a in resultados}
        for clave, etq in (("sello", "sello digital"), ("cadena", "cadena original"), ("idcif", "idCIF")):
            grupos = {}
            for a in resultados:
                v = (a.datos or {}).get(clave)
                if v:
                    grupos.setdefault(v, []).append(a)
            for grupo in grupos.values():
                # El idCIF es del CONTRIBUYENTE: dos constancias del mismo RFC
                # (de meses distintos) lo comparten legítimamente. Solo es
                # clon si aparece con RFC distintos.
                if clave == "idcif" and len({(a.datos or {}).get("rfc") for a in grupo}) < 2:
                    continue
                if len({a.sha256 for a in grupo}) > 1:
                    for a in grupo:
                        for o in grupo:
                            if o.sha256 != a.sha256:
                                compartidos[id(a)].setdefault(o.archivo, []).append(etq)
        for a in resultados:
            if compartidos[id(a)]:
                detalle = "; ".join(f"{', '.join(dict.fromkeys(e))} igual que «{n}»"
                                    for n, e in compartidos[id(a)].items())
                a.candados.append(Candado(
                    "3.12", "Sello, cadena e idCIF irrepetibles en el lote", FALLA,
                    detalle + ". Dos archivos distintos no pueden compartirlos: uno es copia alterada.",
                    "Constancias clonadas a partir de otra."))
                a.candados.sort(key=lambda c: tuple(int(x) for x in c.clave.split(".")))
    return resultados


# ===========================================================================
#  REPORTE PDF
# ===========================================================================
_COLOR_ESTADO = {OK: "#15803D", AVISO: "#B45309", FALLA: "#B91C1C", INFO: "#475569"}
_FONDO_ESTADO = {OK: "#DCFCE7", AVISO: "#FEF3C7", FALLA: "#FEE2E2", INFO: "#E2E8F0"}
_COLOR_VEREDICTO = {"SIN INDICIOS DE ALTERACIÓN": "#15803D", "REVISAR MANUALMENTE": "#B45309",
                    "ALTERADA / NO CONFIABLE": "#B91C1C", "NO VERIFICABLE": "#B91C1C"}
AZUL = "#191970"


def generar_pdf(analisis, ruta_salida, analista="", pdv=""):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    est = getSampleStyleSheet()
    cuerpo = ParagraphStyle("c", parent=est["Normal"], fontName="Helvetica", fontSize=8.5, leading=11)
    chico = ParagraphStyle("ch", parent=cuerpo, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#475569"))
    h2 = ParagraphStyle("h2", parent=cuerpo, fontName="Helvetica-Bold", fontSize=11, leading=14,
                        textColor=colors.HexColor(AZUL), spaceBefore=10, spaceAfter=4,
                        keepWithNext=1)
    esc = lambda t: html.escape(str(t or ""))  # noqa: E731

    d = analisis.datos or {}
    fecha_gen = (_fechas.ahora() if _fechas else datetime.now()).strftime("%d/%m/%Y %H:%M")
    elementos = []

    # --- Veredicto ----------------------------------------------------------
    ver = analisis.veredicto
    col = colors.HexColor(_COLOR_VEREDICTO.get(ver, "#475569"))
    n = analisis.conteo()
    resumen = (f"{n.get(OK, 0)} candados OK · {n.get(AVISO, 0)} avisos · {n.get(FALLA, 0)} fallas")
    if ver in ("ALTERADA / NO CONFIABLE", "NO VERIFICABLE"):
        pol = "No se debe usar para el expediente: solicita la CSF original descargada del SAT"
    elif analisis.cumple_politicas:
        pol = "Cumple políticas (vigencia y estatus)"
    else:
        pol = "NO cumple políticas de la financiera (ver sección 4)"
    caja = Table([[Paragraph(f'<font color="white"><b>{esc(ver)}</b></font>',
                             ParagraphStyle("v", parent=cuerpo, fontSize=16, leading=20, alignment=TA_CENTER))],
                  [Paragraph(f'<font color="white">{esc(resumen)}<br/>{esc(pol)}</font>',
                             ParagraphStyle("v2", parent=cuerpo, alignment=TA_CENTER))]],
                 colWidths=[17.6 * cm])
    caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), col),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    elementos += [caja, Spacer(1, 4)]
    for i, u in enumerate(analisis.urls_qr, 1):
        elementos.append(Paragraph(f'Valida en el SAT · QR {i}: <link href="{esc(u)}" color="#1D4ED8">'
                                   f'{esc(u)}</link>', chico))
    elementos.append(Spacer(1, 6))

    # --- Datos leídos --------------------------------------------------------
    if d:
        filas = [
            ("RFC", d.get("rfc")), ("Nombre / razón social", d.get("nombre_completo")),
            ("Tipo", {"moral": "Persona moral", "fisica": "Persona física"}.get(d.get("tipo"), "—")),
            ("CURP", d.get("curp") or "—"), ("idCIF", d.get("idcif")),
            ("Emisión", d.get("emision_texto")), ("Estatus", d.get("estatus")),
            ("Régimen", "; ".join(r["regimen"] for r in d.get("regimenes", [])) or "—"),
            ("Domicilio", ", ".join(x for x in (d.get("vialidad"), d.get("num_ext"), d.get("colonia"),
                                                f"CP {d.get('cp')}" if d.get("cp") else "",
                                                d.get("municipio"), d.get("entidad")) if x)),
        ]
        t = Table([[Paragraph(f"<b>{esc(a)}</b>", cuerpo), Paragraph(esc(b), cuerpo)] for a, b in filas],
                  colWidths=[4.2 * cm, 13.4 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        elementos += [Paragraph("Datos leídos del documento", h2), t]

    # --- Candados por sección -----------------------------------------------
    for sec, titulo in SECCIONES.items():
        lista = [c for c in analisis.candados if c.seccion == sec]
        if not lista:
            continue
        filas = [[Paragraph("<b>#</b>", chico), Paragraph("<b>Candado</b>", chico),
                  Paragraph("<b>Resultado</b>", chico), Paragraph("<b>Detalle</b>", chico)]]
        estilos = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                   ("VALIGN", (0, 0), (-1, -1), "TOP")]
        for i, c in enumerate(lista, start=1):
            det = esc(c.detalle)
            if c.previene and c.estado in (FALLA, AVISO):
                det += f'<br/><font color="#64748B" size="7">Previene: {esc(c.previene)}</font>'
            filas.append([Paragraph(c.clave, chico), Paragraph(esc(c.titulo), cuerpo),
                          Paragraph(f'<font color="{_COLOR_ESTADO[c.estado]}"><b>{c.estado}</b></font>',
                                    ParagraphStyle("e", parent=cuerpo, alignment=TA_CENTER)),
                          Paragraph(det, cuerpo)])
            estilos.append(("BACKGROUND", (2, i), (2, i), colors.HexColor(_FONDO_ESTADO[c.estado])))
        t = Table(filas, colWidths=[1.0 * cm, 5.0 * cm, 1.8 * cm, 9.8 * cm], repeatRows=1)
        t.setStyle(TableStyle(estilos))
        elementos += [Paragraph(f"{sec}. {titulo}", h2), t]

    # --- Validación manual (boletín) -----------------------------------------
    pasos = [
        "Escanea el <b>1er QR</b> (junto a la cédula) y confirma que el portal del SAT muestre "
        "el mismo nombre, RFC, CURP, situación, régimen con fecha de inicio y domicilio.",
        "Escanea el <b>2do QR</b> (junto al sello) y confirma que la fecha y el RFC coincidan con "
        "la cadena original.",
        "Verifica que el link abra en <b>siat.sat.gob.mx</b> y no en otra dirección.",
        "No solicites usuarios ni contraseñas al cliente; el PDV no debe generar ni editar la constancia.",
    ]
    bloque = [Paragraph("Validación manual obligatoria (boletín BMGFS)", h2)]
    bloque += [Paragraph(f"{i}. {p}", cuerpo) for i, p in enumerate(pasos, 1)]
    for i, u in enumerate(analisis.urls_qr, 1):
        bloque.append(Paragraph(f'QR {i}: <link href="{esc(u)}" color="#1D4ED8">{esc(u)}</link>', chico))
    elementos.append(KeepTogether(bloque))
    elementos += [Spacer(1, 8), Paragraph(
        "Este análisis revisa candados técnicos del archivo; no sustituye la consulta al portal del "
        "SAT. Un resultado sin indicios no garantiza autenticidad si el QR no se valida.", chico),
        Paragraph(f"Huella SHA-256 del archivo revisado: {analisis.sha256}", chico)]

    def pie(canvas, doc):
        canvas.saveState()
        ancho, alto = letter
        canvas.setFillColor(colors.HexColor(AZUL))
        canvas.rect(0, alto - 0.15 * cm, ancho, 0.15 * cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(1.6 * cm, alto - 1.1 * cm, "Validación de Constancia de Situación Fiscal")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(1.6 * cm, alto - 1.5 * cm, f"Archivo: {analisis.archivo[:90]}")
        canvas.drawRightString(ancho - 1.6 * cm, alto - 1.1 * cm, fecha_gen)
        canvas.line(1.6 * cm, 1.3 * cm, ancho - 1.6 * cm, 1.3 * cm)
        izq = " · ".join(x for x in (pdv, f"Validó: {analista}" if analista else "") if x)
        canvas.drawString(1.6 * cm, 0.85 * cm, izq or "Autoexpress Inbursa · MG Financial Services")
        canvas.drawRightString(ancho - 1.6 * cm, 0.85 * cm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(ruta_salida, pagesize=letter, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=2.0 * cm, bottomMargin=1.7 * cm,
                            title=f"Validación CSF {d.get('rfc', '')}", author=analista or "")
    doc.build(elementos, onFirstPage=pie, onLaterPages=pie)
    return ruta_salida


def resumen_texto(analisis):
    """Resumen en texto para la consola / el 'Detalle del proceso' de la app."""
    lineas = [f"{analisis.archivo}: {analisis.veredicto}"
              + ("" if analisis.cumple_politicas else "  ·  NO cumple políticas")]
    for c in analisis.candados:
        if c.estado in (FALLA, AVISO):
            lineas.append(f"   [{c.estado}] {c.clave} {c.titulo}: {c.detalle}")
    return "\n".join(lineas)


# ===========================================================================
#  PUNTO DE ENTRADA (Colab / línea de comandos)
# ===========================================================================
def resumen_dict(analisis, reporte=None, hoy=None):
    """Lo esencial del análisis en datos simples (str/int/list/dict), para
    mostrarlo en la página de la app sin depender de estas clases."""
    hoy = hoy or _hoy()
    d = analisis.datos or {}
    n = analisis.conteo()
    tecnicos = [c for c in analisis.candados if c.seccion < 4]
    emision = d.get("fecha_emision")
    return {
        "archivo": analisis.archivo,
        "reporte": reporte,
        "veredicto": analisis.veredicto,
        "cumple_politicas": analisis.cumple_politicas,
        "total": len(analisis.candados),
        "ok": n.get(OK, 0), "avisos": n.get(AVISO, 0), "fallas": n.get(FALLA, 0),
        "tecnicos_ok": sum(c.estado in (OK, INFO) for c in tecnicos),
        "tecnicos_total": len(tecnicos),
        "datos": {
            "RFC": d.get("rfc") or "—",
            "Nombre / razón social": d.get("nombre_completo") or "—",
            "Tipo": {"moral": "Persona moral", "fisica": "Persona física"}.get(d.get("tipo"), "—"),
            "CURP": d.get("curp") or ("No aplica" if d.get("tipo") == "moral" else "—"),
            "idCIF": d.get("idcif") or "—",
            "Emisión": (f"{_fmt(emision)} · hace {(hoy - emision).days} días" if emision else "—"),
            "Lugar de emisión": (d.get("lugar_emision") or "—").title(),
            "Estatus en el padrón": d.get("estatus") or "—",
            "Inicio de operaciones": d.get("inicio_operaciones") or "—",
            "Régimen": "; ".join(r["regimen"] for r in d.get("regimenes", [])) or "—",
            "Domicilio": ", ".join(x for x in (d.get("vialidad"), d.get("num_ext"), d.get("colonia"),
                                               f"CP {d.get('cp')}" if d.get("cp") else "",
                                               d.get("municipio"), d.get("entidad")) if x) or "—",
        },
        "dias_emision": (hoy - emision).days if emision else None,
        "candados": [{"clave": c.clave, "seccion": c.seccion, "titulo": c.titulo, "estado": c.estado,
                      "detalle": c.detalle, "previene": c.previene} for c in analisis.candados],
        "urls_qr": list(analisis.urls_qr),
        "sha256": analisis.sha256,
    }


def main(rutas=None, carpeta_salida="salida", analista="", pdv="", consultar_sat=True, nombres=None,
         devolver_resumen=False):
    """En Colab, sin argumentos, pide subir los archivos y descarga los PDF.
    Con devolver_resumen=True regresa (rutas_pdf, [resumen_dict, ...]) para la app."""
    en_colab = False
    if rutas is None:
        try:
            from google.colab import files  # type: ignore
            subidos = files.upload()
            rutas = list(subidos.keys())
            en_colab = True
        except ImportError:
            import sys
            rutas = sys.argv[1:]
    os.makedirs(carpeta_salida, exist_ok=True)
    salidas, resumenes = [], []
    for a in analizar_lote(rutas, consultar_sat=consultar_sat, nombres=nombres):
        rfc = (a.datos or {}).get("rfc") or re.sub(r"\W+", "_", os.path.splitext(a.archivo)[0])[:40]
        ruta = os.path.join(carpeta_salida, f"Validacion_CSF_{rfc}.pdf")
        k = 2
        while ruta in salidas:
            ruta = os.path.join(carpeta_salida, f"Validacion_CSF_{rfc}_{k}.pdf")
            k += 1
        generar_pdf(a, ruta, analista=analista, pdv=pdv)
        salidas.append(ruta)
        resumenes.append(resumen_dict(a, reporte=os.path.basename(ruta)))
        print(resumen_texto(a))
        print()
    if en_colab:
        from google.colab import files  # type: ignore
        for s in salidas:
            files.download(s)
    return (salidas, resumenes) if devolver_resumen else salidas


if __name__ == "__main__":
    main()
