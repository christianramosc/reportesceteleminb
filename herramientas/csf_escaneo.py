# -*- coding: utf-8 -*-
"""
VALIDAR CSF — MODO COPIA (escaneo o foto)
=========================================

Una CSF escaneada, fotografiada o "impresa a imagen" ya no es el archivo
del SAT: es una fotografía de lo que alguien imprimió. Por eso NO se le
pueden aplicar los candados del archivo (productor, metadatos, fuentes,
maquetación...): un escaneo puede venir de una constancia alterada ANTES de
imprimirse y no habría forma de notarlo en el archivo.

Lo que SÍ se puede revisar, y es lo que hace este módulo:

  1. Leer los códigos tal como están impresos (2 QR + código de barras) y
     comparar sus cadenas entre sí: los tres deben hablar del mismo RFC y
     llevar al portal oficial del SAT.
  2. Leer el texto impreso con OCR (reconocimiento de texto) y compararlo
     contra los códigos: RFC, idCIF, cadena original (fecha y RFC).
  3. Revisar que los datos leídos sean coherentes: dígito verificador de
     RFC y CURP, RFC ↔ CURP ↔ nombre, fechas, código postal, régimen.

Veredictos de este modo (nunca "sin indicios de alteración"):
  - ALTERADA / NO CONFIABLE : un código no coincide con otro o con el texto,
                              o un QR lleva a una página que no es del SAT.
  - COPIA: DATOS COINCIDEN  : todo lo legible coincide. Aun así la
                              autenticidad NO se puede comprobar: hay que
                              validar el QR en el SAT o pedir el PDF original.
  - COPIA: REVISAR A MANO   : algo no se alcanzó a leer o quedó dudoso.
  - NO VERIFICABLE          : no se pudo leer ningún código.

El OCR (RapidOCR) puede confundir caracteres parecidos (0/O, 1/I, 5/S, 8/B).
Una diferencia que solo se explica por esa confusión se marca como AVISO
("lectura dudosa"), no como FALLA, para no acusar de alterada una copia
legítima por una mancha del escáner.
"""

import re
from datetime import date

try:
    from . import validar_csf as v
except ImportError:  # ejecución suelta (Colab)
    import validar_csf as v

OK, AVISO, FALLA, INFO = v.OK, v.AVISO, v.FALLA, v.INFO

# Resolución de trabajo: ~200 dpi para OCR; los códigos se reintentan más grandes.
ESCALA_OCR = 2.6          # puntos PDF -> píxeles (2.6 × 72 ≈ 190 dpi)
ESCALAS_CODIGOS = (3, 2, 4)
LADO_MAX_FOTO = 2600      # una foto de celular se reduce a esto para el OCR

# Caracteres que el OCR confunde entre sí. Se llevan todos a un mismo
# "representante" para saber si dos lecturas difieren SOLO por eso.
_CONFUSION = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "J": "1",
                            "S": "5", "B": "8", "Z": "2", "G": "6", "T": "7", "A": "4"})

_PAT_RFC = re.compile(r"(?<![A-Z0-9Ñ&])([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})(?![A-Z0-9])")
_PAT_CURP = re.compile(r"(?<![A-Z0-9])([A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d)(?![A-Z0-9])")
_MESES = "ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|SETIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE"


# ===========================================================================
#  ¿Es una copia?
# ===========================================================================
def es_copia_pdf(ruta):
    """(True, motivo) si el PDF es un escaneo o una imagen de la constancia:
    sin texto, o con cada página cubierta por una sola imagen y un productor
    que no es el del SAT (escáneres que agregan texto "buscable")."""
    try:
        import pdfplumber
        import pypdf
        lector = pypdf.PdfReader(ruta, strict=False)
        productor = str((lector.metadata or {}).get("/Producer", "") or "")
        with pdfplumber.open(ruta) as pdf:
            chars = sum(len(p.chars) for p in pdf.pages)
            n = len(pdf.pages)

            def cubiertas(fraccion):
                total = 0
                for p in pdf.pages:
                    area = float(p.width) * float(p.height)
                    total += any(im["width"] * im["height"] >= fraccion * area for im in p.images)
                return total
            casi_todo, todo = cubiertas(0.6), cubiertas(0.85)
    except Exception:
        return False, ""
    # Es copia solo si sus páginas SON imágenes. Un PDF con poco texto y sin
    # imagen de página (p. ej. una constancia fabricada en Word o con IA) se
    # queda en el modo digital, donde fallan sus candados.
    if n and casi_todo == n and chars < 200:
        return True, f"el PDF no tiene texto: cada página es una imagen{_de(productor)}"
    if n and todo == n and not productor.startswith(v.PRODUCTOR_SAT):
        return True, f"cada página es una imagen completa con texto agregado por OCR{_de(productor)}"
    return False, ""


def _de(productor):
    return f" (generado por «{productor}»)" if productor else ""


# ===========================================================================
#  Páginas como imagen
# ===========================================================================
def _paginas_pdf(ruta, escala):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(ruta)
    try:
        return [doc[i].render(scale=escala).to_pil().convert("RGB") for i in range(len(doc))]
    finally:
        doc.close()


def _foto(ruta):
    from PIL import Image, ImageOps
    img = Image.open(ruta)
    img = ImageOps.exif_transpose(img)        # fotos de celular giradas
    return img.convert("RGB")


def _reducir(img, lado=LADO_MAX_FOTO):
    from PIL import Image
    if max(img.size) <= lado:
        return img
    f = lado / max(img.size)
    return img.resize((int(img.width * f), int(img.height * f)), Image.LANCZOS)


# ===========================================================================
#  Códigos (QR y código de barras)
# ===========================================================================
def _variantes(img):
    """La imagen tal cual y versiones que ayudan con escaneos pálidos o fotos."""
    from PIL import ImageOps
    gris = ImageOps.autocontrast(img.convert("L"), cutoff=2)
    yield img
    yield gris
    yield gris.point(lambda p: 255 if p > 150 else 0)


def leer_codigos(ruta, es_pdf):
    """[{pagina, formato, texto}] sin repetir. Para PDF se renderiza a varias
    resoluciones hasta encontrar los QR y el código de barras."""
    encontrados = {}

    def anotar(pagina, img):
        for fmt, txt in (v._leer_codigos(img) or []):
            fmt = "QR" if fmt.upper().startswith("QR") else ("CODE128" if "128" in fmt else fmt)
            encontrados.setdefault((fmt, txt), pagina)

    def completo():
        qrs = {t for (f, t) in encontrados if f == "QR"}
        return len(qrs) >= 2 and any(f == "CODE128" for (f, _) in encontrados)

    if es_pdf:
        for escala in ESCALAS_CODIGOS:
            for i, img in enumerate(_paginas_pdf(ruta, escala)):
                anotar(i, img)
            if completo():
                break
        if not completo():
            for i, img in enumerate(_paginas_pdf(ruta, 3)):
                for var in list(_variantes(img))[1:]:
                    anotar(i, var)
    else:
        img = _foto(ruta)
        for var in _variantes(img):
            anotar(0, var)
            if completo():
                break
        if not completo():
            from PIL import Image
            # Foto chica: el código de barras mide pocos píxeles de alto; se amplía.
            if max(img.size) < 3000:
                anotar(0, img.resize((img.width * 2, img.height * 2), Image.LANCZOS))
            anotar(0, _reducir(img, 1800))
    return [{"pagina": p, "formato": f, "texto": t} for (f, t), p in encontrados.items()]


# ===========================================================================
#  Texto (OCR)
# ===========================================================================
_MOTOR = None


def _motor_ocr():
    """RapidOCR (pip, sin programas del sistema: funciona en Streamlit Cloud).
    Se carga una sola vez por proceso. None si no está instalado."""
    global _MOTOR
    if _MOTOR is None:
        try:
            from rapidocr import RapidOCR
            _MOTOR = RapidOCR(params={"Global.log_level": "error"})
        except Exception:
            _MOTOR = False
    return _MOTOR or None


def leer_texto(ruta, es_pdf):
    """Renglones de texto de todas las páginas, en orden de lectura.
    None si no hay motor de OCR."""
    motor = _motor_ocr()
    if motor is None:
        return None
    imagenes = _paginas_pdf(ruta, ESCALA_OCR) if es_pdf else [_reducir(_foto(ruta))]
    renglones = []
    for img in imagenes:
        try:
            import numpy as np
            r = motor(np.asarray(img))
            renglones.extend(t.strip() for t in (r.txts or ()) if t and t.strip())
        except Exception:
            continue
    return renglones


# ===========================================================================
#  Datos desde el texto leído
# ===========================================================================
def _c(texto):
    return v._compacto(texto)


def _valor(renglones, *etiquetas):
    """Valor de un campo "Etiqueta: valor". El valor puede venir en el mismo
    renglón o, como en las tablas de la CSF, en el renglón siguiente."""
    objetivos = [_c(e) for e in etiquetas]
    for i, r in enumerate(renglones):
        cr = _c(r)
        for obj in objetivos:
            if not cr.startswith(obj):
                continue
            if ":" in r:
                valor = r.split(":", 1)[1].strip()
                if valor:
                    return valor
            elif cr != obj:
                # "Código Postal 28550" (sin dos puntos): se quita la etiqueta.
                palabras, acumulado = r.split(), ""
                while palabras and obj.startswith(acumulado + _c(palabras[0])):
                    acumulado += _c(palabras.pop(0))
                return " ".join(palabras).strip()
            siguiente = renglones[i + 1].strip() if i + 1 < len(renglones) else ""
            return "" if (":" in siguiente or not siguiente) else siguiente
    return ""


def datos_de_texto(renglones):
    """Mismo diccionario que validar_csf._extraer_datos, hasta donde el OCR
    alcanza a leer."""
    t = "\n".join(renglones)
    n = v._norm(t)
    g = lambda *e: _valor(renglones, *e)  # noqa: E731
    d = {
        "rfc": "", "curp": "", "nombres": g("Nombre (s)", "Nombres"),
        "paterno": g("Primer Apellido"), "materno": g("Segundo Apellido"),
        "razon_social": g("Denominación/Razón Social", "Denominación o Razón Social"),
        "regimen_capital": g("Régimen Capital"), "nombre_comercial": g("Nombre Comercial"),
        "inicio_operaciones": g("Fecha inicio de operaciones"),
        "estatus": v._norm(g("Estatus en el padrón")).split(" ")[0] if g("Estatus en el padrón") else "",
        "ultimo_cambio": g("Fecha de último cambio de estado"),
        "cp": re.sub(r"\D", "", g("Código Postal"))[:5],
        "vialidad": g("Nombre de Vialidad"), "num_ext": g("Número Exterior"),
        "colonia": g("Nombre de la Colonia"),
        "municipio": g("Nombre del Municipio o Demarcación Territorial"),
        "entidad": g("Nombre de la Entidad Federativa"),
        "actividades": [], "obligaciones": [], "sello": "", "cadena": "",
    }
    # RFC de la tabla y todos los "con forma de RFC" que aparezcan (cédula,
    # tabla, leyenda del código de barras, cadena original).
    d["rfc"] = re.sub(r"[^A-Z0-9Ñ&]", "", v._norm(g("RFC")))[:13]
    d["rfcs_leidos"] = _PAT_RFC.findall(n)
    curp = re.sub(r"[^A-Z0-9]", "", v._norm(g("CURP")))
    if len(curp) != 18:
        m = _PAT_CURP.search(n)
        curp = m.group(1) if m else curp
    d["curp"] = curp
    m = re.search(r"CIF\s*[:.;]?\s*(\d[\d ]{8,13}\d)", n)
    d["idcif"] = re.sub(r"\D", "", m.group(1)) if m else ""

    # Lugar y fecha de emisión: "COLIMA , COLIMA A 30 DE OCTUBRE DE 2026".
    # Se busca renglón por renglón (el texto completo junta la cédula con el
    # recuadro de emisión); la fecha puede partirse en el renglón siguiente.
    d["emision_texto"], d["fecha_emision"], d["lugar_emision"] = "", None, ""
    patron = re.compile(rf"^(.*?)\bA\s+(\d{{1,2}})\s+DE\s+({_MESES})\s+DE\s+(\d{{4}})")
    for i, r in enumerate(renglones):
        nr = v._norm(r)
        if not re.search(r"\bA\s+\d{1,2}\b", nr):
            continue
        siguiente = v._norm(renglones[i + 1]) if i + 1 < len(renglones) else ""
        m = patron.search(nr) or patron.search(f"{nr} {siguiente}")
        if m:
            lugar = m.group(1).strip(" ,")
            d["lugar_emision"] = lugar
            d["emision_texto"] = f"{lugar} A {m.group(2)} DE {m.group(3)} DE {m.group(4)}".strip()
            d["fecha_emision"] = v._fecha_texto(d["emision_texto"])
            break

    # Cadena original: fecha-hora, RFC, certificado y el bloque cifrado.
    i = n.find("CADENA ORIGINAL")
    tramo = re.sub(r"\s+", " ", n[i:i + 700]) if i >= 0 else ""
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})\s*(\d{2}):(\d{2}):(\d{2})", tramo)
    d["cadena_fecha"] = None
    d["cadena_rfc"] = d["cadena_cert"] = ""
    d["cadena_cifrado"] = False
    if m:
        try:
            d["cadena_fecha"] = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
        resto = tramo[m.end():]
        r = _PAT_RFC.search(resto)
        d["cadena_rfc"] = r.group(1) if r else ""
        cert = re.search(r"(\d{18,22})", resto)
        d["cadena_cert"] = cert.group(1) if cert else ""
        # El cifrado del SAT siempre empieza con "U2FsdGVkX1" ("Salted__" en base64).
        d["cadena_cifrado"] = "U2FSDGVKX1" in re.sub(r"[^A-Z0-9]", "", resto)
        d["cadena"] = tramo[:250]
    d["sello_presente"] = bool(re.search(r"SELLO\s*DIGITAL\s*:?\s*[A-Z0-9+/=]{60,}", re.sub(r"\s*\n\s*", "", n)))

    # Régimen(es): renglones que empiezan con "RÉGIMEN DE/DEL ..." (no el encabezado).
    regimenes = []
    for r in renglones:
        nr = v._norm(r)
        if re.match(r"^REGIMEN (DE|DEL|SIMPLIFICADO|GENERAL)\b", nr) and len(nr) > 20:
            regimenes.append({"regimen": re.sub(r"\s*\d{2}/\d{2}/\d{4}.*$", "", r).strip().rstrip("."),
                              "inicio": "", "fin": ""})
    d["regimenes"] = regimenes

    largo = len(d["rfc"]) or len(max(d["rfcs_leidos"], key=len, default=""))
    d["tipo"] = "moral" if (d["razon_social"] or largo == 12) else ("fisica" if (d["curp"] or d["paterno"]) else "")
    d["nombre_completo"] = (d["razon_social"] if d["tipo"] == "moral" else
                            " ".join(x for x in (d["nombres"], d["paterno"], d["materno"]) if x))
    return d


# ===========================================================================
#  Comparación tolerante a errores de OCR
# ===========================================================================
def comparar(leido, exacto):
    """'igual', 'dudoso' (difiere solo en caracteres que el OCR confunde),
    'distinto' o None (no se leyó)."""
    leido = re.sub(r"\s+", "", str(leido or "")).upper()
    exacto = re.sub(r"\s+", "", str(exacto or "")).upper()
    if not leido or not exacto:
        return None
    if leido == exacto:
        return "igual"
    if len(leido) == len(exacto) and leido.translate(_CONFUSION) == exacto.translate(_CONFUSION):
        return "dudoso"
    return "distinto"


# ===========================================================================
#  ANÁLISIS
# ===========================================================================
def analizar(ruta, analisis, add, hoy, consultar_sat, es_pdf, motivo=""):
    analisis.modo = "copia"
    try:
        codigos = leer_codigos(ruta, es_pdf)
        renglones = leer_texto(ruta, es_pdf)
    except Exception as e:
        add("1.1", "Archivo legible", FALLA, f"No se pudo abrir el archivo ({type(e).__name__}: {e}).", "")
        analisis.verificable = False
        return
    d = datos_de_texto(renglones or [])
    analisis.datos = d

    # ---------------------------------------------------------------- 1. Archivo
    # 1.1 — POR QUÉ ESTE MODO. Se dice claramente qué NO se puede saber.
    que = "una foto o imagen" if not es_pdf else "un escaneo (o una imagen puesta en un PDF)"
    add("1.1", "Documento digital original del SAT", AVISO,
        f"Es {que}" + (f": {motivo}" if motivo else "") + ". Con una copia NO se puede comprobar "
        "que la constancia no se alteró antes de imprimirse o fotografiarse, ni aplicar los candados "
        "del archivo (programa que lo generó, edición, fuentes, maquetación). Solo se compararon los "
        "códigos y los datos visibles. Para certeza, valida el QR en el SAT o pide el PDF original.",
        "Constancias alteradas y luego impresas, escaneadas o fotografiadas.")

    # 1.2 — CALIDAD DE LECTURA (OCR).
    if renglones is None:
        add("1.2", "Lectura del texto (OCR)", AVISO,
            "No está disponible el lector de texto (pip install rapidocr onnxruntime): solo se "
            "compararon los códigos entre sí.", "")
    elif len(renglones) < 25:
        add("1.2", "Lectura del texto (OCR)", AVISO,
            f"Solo se leyeron {len(renglones)} renglones: la imagen está borrosa, chica o con reflejos. "
            "Escanea a 300 dpi o toma la foto de frente, con buena luz.", "")
    else:
        add("1.2", "Lectura del texto (OCR)", INFO,
            f"Se leyeron {len(renglones)} renglones. El OCR puede confundir caracteres parecidos "
            "(0/O, 1/I, 5/S): esas diferencias se marcan como lectura dudosa, no como alteración.", "")

    # -------------------------------------------------------------- 2. Códigos
    qrs = [c for c in codigos if c["formato"] == "QR"]
    barras = [c["texto"] for c in codigos if c["formato"] == "CODE128"]
    parsed = [p for p in (v.parse_qr_sat(c["texto"]) for c in qrs) if p]
    qr1 = next((p for p in parsed if p["D1"] == v.D1_QR_CEDULA), None)
    qr2 = next((p for p in parsed if p["D1"] == v.D1_QR_SELLO), None)
    analisis.urls_qr = [c["texto"] for c in qrs]
    d["qr1"], d["qr2"] = qr1, qr2
    analisis.verificable = bool(qrs or barras)

    calidad = ("Toma la foto de frente, con buena luz y sin reflejos." if not es_pdf
               else "Vuelve a escanear a 300 dpi, sin arrugas ni sombras sobre el código.")
    # 2.1 y 2.2 — QR legibles.
    add("2.1", "QR de la cédula legible", OK if qr1 else AVISO,
        f"idCIF {qr1['folio']} · RFC {qr1['rfc']}." if qr1 else f"No se pudo leer (página 1, junto a la cédula). {calidad}",
        "QR borrados o sustituidos.")
    add("2.2", "QR del sello legible", OK if qr2 else AVISO,
        f"Folio {qr2['folio']} · RFC {qr2['rfc']}." if qr2 else
        "No se pudo leer. Está en la página 2, junto al sello: " +
        ("si es foto, sube también una de la página 2 o junta ambas en un PDF." if not es_pdf else calidad),
        "QR borrados o sustituidos.")

    # 2.3 — DOMINIO OFICIAL: aquí no hay duda de lectura, la dirección se lee exacta.
    malos = []
    for p in parsed:
        if p["esquema"] != "https" or p["dominio"] != v.DOMINIO_QR or p["ruta"] != v.RUTA_QR or p["extra"]:
            pista = next((f" [{q}: cualquiera puede publicar ahí gratis]"
                          for suf, q in v.HOSTING_GRATUITO.items() if p["dominio"].endswith(suf)), "")
            malos.append(f"{p['esquema']}://{p['dominio']}{p['ruta']}{pista}")
    otros = [c["texto"] for c in qrs if not v.parse_qr_sat(c["texto"]) or
             v.parse_qr_sat(c["texto"])["D1"] not in (v.D1_QR_CEDULA, v.D1_QR_SELLO)]
    if malos or otros:
        add("2.3", "QR apuntan al portal oficial del SAT", FALLA,
            "Dirección no oficial: " + "; ".join(malos + [o[:80] for o in otros if o not in malos]) +
            f". Debe ser https://{v.DOMINIO_QR}{v.RUTA_QR}.", "QR que llevan a una página clonada del SAT.")
    elif parsed:
        add("2.3", "QR apuntan al portal oficial del SAT", OK,
            f"Llevan a https://{v.DOMINIO_QR} (validador oficial).", "QR que llevan a una página clonada del SAT.")

    # 2.4 — Código de barras legible.
    add("2.4", "Código de barras legible", OK if barras else AVISO,
        f"Dice {barras[0]}." if barras else
        f"No se pudo leer (página 1, bajo «Lugar y Fecha de Emisión»). {calidad}",
        "Cambio de RFC sin regenerar el código de barras.")

    # 2.5 — LOS CÓDIGOS ENTRE SÍ. Son lecturas EXACTAS (sin OCR): si no dicen
    # el mismo RFC, la constancia se armó con piezas de dos documentos.
    rfcs_codigos = {}
    if qr1:
        rfcs_codigos["QR de la cédula"] = qr1["rfc"]
    if qr2:
        rfcs_codigos["QR del sello"] = qr2["rfc"]
    if barras:
        rfcs_codigos["código de barras"] = barras[0]
    # Si no coinciden, el de referencia es el que repite la mayoría.
    from collections import Counter
    rfc_codigos = Counter(rfcs_codigos.values()).most_common(1)[0][0] if rfcs_codigos else ""
    if len(rfcs_codigos) >= 2:
        iguales = len(set(rfcs_codigos.values())) == 1
        add("2.5", "Los códigos coinciden entre sí", OK if iguales else FALLA,
            f"Los {len(rfcs_codigos)} códigos dicen {rfc_codigos}." if iguales else
            "No dicen el mismo RFC: " + "; ".join(f"{k}: {x}" for k, x in rfcs_codigos.items()) + ".",
            "Constancia armada con códigos de otra persona.")
    else:
        add("2.5", "Los códigos coinciden entre sí", AVISO,
            "Se leyó un solo código: no hay contra qué compararlo.", "")
    d["rfc_codigos"] = rfc_codigos

    # 2.6 — QR DE LA CÉDULA = LO IMPRESO (idCIF y RFC junto al QR).
    if qr1:
        cmp_cif = comparar(d["idcif"], qr1["folio"])
        if cmp_cif is None:
            add("2.6", "QR de la cédula = idCIF impreso", AVISO,
                f"No se alcanzó a leer el idCIF impreso. El QR dice {qr1['folio']}: compáralo a simple vista.", "")
        else:
            estado = {"igual": OK, "dudoso": AVISO, "distinto": FALLA}[cmp_cif]
            add("2.6", "QR de la cédula = idCIF impreso", estado,
                f"Impreso {d['idcif']} = QR {qr1['folio']}." if cmp_cif == "igual" else
                f"Impreso {d['idcif']} / QR {qr1['folio']}" +
                (": parece error de lectura, compáralo a simple vista." if cmp_cif == "dudoso"
                 else ": el idCIF impreso no es el del QR."),
                "Cambio de idCIF en el texto conservando el QR de otra persona.")

    # 2.7 — Consulta al portal del SAT (mismo candado que el modo digital).
    if consultar_sat and qr1 and not malos:
        if not d["rfc"]:
            d["rfc"] = rfc_codigos
        add("2.7", "Consulta al portal del SAT", *v._consultar_sat(qr1, d))

    # ----------------------------------------------------------------- 3. Datos
    rfc = rfc_codigos or d["rfc"]
    d["rfc"] = rfc
    origen_rfc = "de los códigos" if rfc_codigos else "leído con OCR"

    # 3.1 — Dígito verificador. Con el RFC de los códigos es exacto (FALLA);
    # si solo hay el del OCR, una mala lectura podría causarlo (AVISO).
    if rfc:
        patron = v.PAT_RFC_MORAL if len(rfc) == 12 else v.PAT_RFC_FISICA
        ok = bool(patron.match(rfc)) and v.digito_rfc(rfc) == rfc[-1]
        add("3.1", "RFC válido (dígito verificador)", OK if ok else (FALLA if rfc_codigos else AVISO),
            f"RFC {rfc} ({origen_rfc}): dígito verificador correcto." if ok else
            f"RFC {rfc} ({origen_rfc}): el último carácter debería ser {v.digito_rfc(rfc)}.",
            "RFC inventado o con un carácter cambiado.")
    else:
        add("3.1", "RFC válido (dígito verificador)", AVISO, "No se pudo leer el RFC.", "")

    # 3.2 — EL RFC IMPRESO (cédula, tabla, leyenda del código, cadena) = CÓDIGOS.
    if rfc_codigos and d["rfcs_leidos"]:
        res = {x: comparar(x, rfc_codigos) for x in dict.fromkeys(d["rfcs_leidos"])}
        distintos = [x for x, r in res.items() if r == "distinto"]
        dudosos = [x for x, r in res.items() if r == "dudoso"]
        veces = len(d["rfcs_leidos"])
        if distintos:
            add("3.2", "RFC impreso = RFC de los códigos", FALLA,
                f"El texto dice {', '.join(distintos)} y los códigos {rfc_codigos}.",
                "Cambio de RFC en el texto conservando los códigos de otra persona.")
        else:
            add("3.2", "RFC impreso = RFC de los códigos", AVISO if dudosos else OK,
                f"Lectura dudosa: {', '.join(dudosos)} vs {rfc_codigos} (compáralo a simple vista)."
                if dudosos else f"Las {veces} veces que aparece impreso dice {rfc_codigos}.",
                "Cambio de RFC en el texto conservando los códigos de otra persona.")
    elif rfc_codigos:
        add("3.2", "RFC impreso = RFC de los códigos", AVISO,
            "No se alcanzó a leer el RFC impreso: compáralo a simple vista.", "")

    # 3.3 / 3.4 — CURP y nombre contra el RFC. Vienen del OCR: AVISO si no cuadra.
    if d["tipo"] == "fisica" and rfc:
        curp = d["curp"]
        if not curp:
            add("3.3", "CURP válida y coherente con el RFC", AVISO, "No se alcanzó a leer la CURP.", "")
        else:
            problemas = []
            if not v.PAT_CURP.match(curp):
                problemas.append(f"«{curp}» no tiene formato de CURP")
            elif v.digito_curp(curp) != curp[-1]:
                problemas.append(f"el dígito verificador debería ser {v.digito_curp(curp)}")
            if comparar(curp[4:10], rfc[4:10]) == "distinto":
                problemas.append(f"fecha de la CURP ({curp[4:10]}) ≠ fecha del RFC ({rfc[4:10]})")
            if comparar(curp[:4], rfc[:4]) == "distinto":
                problemas.append(f"letras de la CURP ({curp[:4]}) ≠ del RFC ({rfc[:4]})")
            add("3.3", "CURP válida y coherente con el RFC", AVISO if problemas else OK,
                ("; ".join(problemas) + " (puede ser error de lectura; compáralo a simple vista).")
                if problemas else f"CURP {curp}: dígito correcto; misma fecha y letras que el RFC.",
                "CURP o RFC cambiados.")
        esperado = v.letras_rfc_fisica(d["paterno"], d["materno"], d["nombres"])
    elif d["tipo"] == "moral":
        esperado = v.letras_rfc_moral(d["razon_social"])
    else:
        esperado = None
    if esperado and rfc:
        ok = comparar(esperado, rfc[:len(esperado)]) in ("igual", "dudoso")
        add("3.4", "Nombre corresponde al RFC", OK if ok else AVISO,
            f"«{d['nombre_completo']}» corresponde a las letras {rfc[:len(esperado)]}." if ok else
            f"Por el nombre leído («{d['nombre_completo']}») el RFC empezaría con {esperado} y empieza "
            f"con {rfc[:len(esperado)]} (puede ser excepción del SAT o error de lectura).",
            "Cambio del nombre del titular.")
    elif rfc:
        add("3.4", "Nombre corresponde al RFC", AVISO, "No se alcanzó a leer el nombre.", "")

    # 3.5 — Fechas: ninguna posterior a la emisión.
    emision = d["fecha_emision"] or d["cadena_fecha"]
    if not d["fecha_emision"] and d["cadena_fecha"]:
        d["fecha_emision"] = d["cadena_fecha"]
        d["emision_texto"] = d["emision_texto"] or f"(de la cadena original) {v._fmt(d['cadena_fecha'])}"
    inicio, cambio = v._fecha_texto(d["inicio_operaciones"]), v._fecha_texto(d["ultimo_cambio"])
    raras = [f"{etq} {v._fmt(f)}" for etq, f in (("inicio de operaciones", inicio), ("último cambio", cambio))
             if f and emision and f > emision]
    if emision and emision > hoy:
        raras.append(f"emisión {v._fmt(emision)} en el futuro")
    if emision:
        add("3.5", "Fechas coherentes", AVISO if raras else OK,
            ("Posterior a la emisión: " + "; ".join(raras) + " (o error de lectura).") if raras else
            f"Inicio {v._fmt(inicio)}, último cambio {v._fmt(cambio)}, emisión {v._fmt(emision)}: en orden.",
            "Fechas alteradas.")

    # 3.7 — Régimen acorde al tipo de persona.
    regs = [v._norm(r["regimen"]) for r in d["regimenes"]]
    if regs and d["tipo"]:
        imposibles = v.REGIMENES_SOLO_FISICA if d["tipo"] == "moral" else v.REGIMENES_SOLO_MORAL
        malos_reg = [r for r in regs if any(x in r for x in imposibles)]
        add("3.7", "Régimen acorde al tipo de persona", AVISO if malos_reg else OK,
            ("No corresponde: " + "; ".join(r.title() for r in malos_reg) + ".") if malos_reg else
            "; ".join(r.title() for r in regs) + ".", "Régimen cambiado.")

    # 3.8 — Código postal de la entidad.
    coincide = v.cp_coincide_entidad(d["cp"], d["entidad"])
    if coincide is not None:
        add("3.8", "Código postal corresponde a la entidad", OK if coincide else AVISO,
            f"CP {d['cp']} pertenece a {d['entidad'].title()}." if coincide else
            f"El CP {d['cp']} no corresponde a {d['entidad'].title()} (o error de lectura).", "Domicilio cambiado.")

    # 3.9 — CADENA ORIGINAL (paso 3 del boletín): su fecha es la de emisión y
    # su RFC es el de los códigos. Los dígitos se leen bien con OCR, así que
    # una diferencia real (no explicable por confusión de caracteres) es FALLA.
    if d["cadena_fecha"] or d["cadena_rfc"]:
        fallas, avisos, bien = [], [], []
        if d["cadena_fecha"] and d["fecha_emision"] and d["fecha_emision"] != d["cadena_fecha"]:
            r = comparar(d["cadena_fecha"].strftime("%Y%m%d"), d["fecha_emision"].strftime("%Y%m%d"))
            (avisos if r == "dudoso" else fallas).append(
                f"fecha de la cadena {v._fmt(d['cadena_fecha'])} ≠ emisión {v._fmt(d['fecha_emision'])}")
        elif d["cadena_fecha"]:
            bien.append(f"fecha {v._fmt(d['cadena_fecha'])}")
        if d["cadena_rfc"] and rfc:
            r = comparar(d["cadena_rfc"], rfc)
            if r == "distinto":
                fallas.append(f"RFC de la cadena {d['cadena_rfc']} ≠ {rfc}")
            elif r == "dudoso":
                avisos.append(f"RFC de la cadena {d['cadena_rfc']} (lectura dudosa)")
            else:
                bien.append(f"RFC {rfc}")
        elif not d["cadena_rfc"]:
            avisos.append("no se leyó el RFC de la cadena")
        if d["cadena_cert"] and comparar(d["cadena_cert"], v.CERTIFICADO_SAT) == "distinto":
            avisos.append(f"certificado {d['cadena_cert']} distinto al habitual")
        if not d["cadena_cifrado"]:
            avisos.append("no se reconoce el inicio del bloque cifrado (U2FsdGVkX1)")
        estado = FALLA if fallas else (AVISO if avisos else OK)
        add("3.9", "Cadena original: fecha y RFC (paso 3 del boletín)", estado,
            "; ".join(fallas + avisos) + "." if fallas or avisos else
            "Coinciden " + " y ".join(bien) + "; certificado y bloque cifrado con la forma del SAT.",
            "Cadena copiada de otra constancia.")
    elif renglones:
        add("3.9", "Cadena original: fecha y RFC (paso 3 del boletín)", AVISO,
            "No se alcanzó a leer la cadena original (2.ª página).", "")

    # 3.10 — El sello no se puede validar desde una imagen (el OCR confunde l/I
    # en base64): solo se informa si está.
    if renglones:
        add("3.10", "Sello digital", INFO,
            "Presente. En una copia no se puede comprobar su estructura (el OCR confunde l, I y 1)."
            if d["sello_presente"] else "No se alcanzó a leer.", "")

    # ------------------------------------------------------------ 4. Políticas
    if d["fecha_emision"] or d["estatus"]:
        v._candados_politicas(d, add, hoy)
