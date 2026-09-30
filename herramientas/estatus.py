# -*- coding: utf-8 -*-
"""
CATÁLOGO CENTRAL DE ESTATUS  —  fuente única de verdad para los 3 reportes.

===========================================================================
 ¿QUÉ RESUELVE ESTE ARCHIVO?
===========================================================================
Antes, cada reporte (avance preliminar, comparativo mensual y resumen
mensual) traía su propia copia de esta lógica:

    STATUS_APROBADO   = ["APROBADO"]
    STATUS_FINANCIADO = ["FINANCIADOS", "FINANCIADO"]
    STATUS_RECHAZADOS = ["RECHAZADO", ...]

    def clasificar_status(status):
        ...
        return "CONTRAPROPUESTA"     # <-- TODO lo demás caía aquí

Eso tenía dos problemas:

  1. Un estatus nuevo (PENDIENTE, EN PROCESO, EN REVISIÓN...) NO se perdía,
     pero se le pegaba la etiqueta "CONTRAPROPUESTA" aunque no lo fuera:
     inflaba esa categoría y escondía qué era cada cosa.
  2. Para agregar un estatus había que editar 3 archivos y acordarse de
     tocar además ORDEN_CATEGORIAS y COLOR_CATEGORIA en cada uno.

Ahora cada estatus es su propia categoría, con su propio color y su lugar
fijo en el orden de tablas y gráficas, y todo se define UNA sola vez aquí.

===========================================================================
 CÓMO AGREGAR UN ESTATUS NUEVO (lo único que vas a tener que hacer)
===========================================================================
Agrega un bloque a la lista CATALOGO de abajo, en la posición del orden que
quieras que ocupe (el orden de la lista = el orden en tablas y gráficas):

    Categoria(
        clave="EN VALIDACION",              # nombre interno, SIN acentos
        etiqueta="En validación",           # como se ve en tablas/gráficas
        etiqueta_corta="En<br/>validación", # encabezado angosto del PDF
        descripcion="EN VALIDACIÓN (documentos en revisión)",
        sinonimos=["EN VALIDACION", "VALIDACION", "EN VALIDACIÓN"],
        color="#9E001F",   # solo referencia: el color real lo asigna
        grupo=ABIERTA,     # asignar_colores() según el grupo (ver abajo)
    )

Y ya: los 3 reportes lo toman automáticamente.

COLORES: el campo `color` del catálogo ya no decide el color de la gráfica.
Solo FINANCIADO y APROBADO tienen color fijo (COLORES_FIJOS). Los demás
reciben el siguiente color libre de la paleta de su grupo, y únicamente si
aparecen en la bitácora. Para cambiar tonos, edita PALETA_ABIERTAS o
PALETA_CERRADAS_NEG.

NOTA IMPORTANTE: no es obligatorio registrarlo. Si en la bitácora aparece
un estatus que no está en este catálogo, el sistema ya NO lo mete a la
fuerza en "CONTRAPROPUESTA": lo trata como categoría propia, le asigna un
color automático y lo coloca al final del orden. Registrarlo aquí solo
sirve para fijarle color, etiqueta bonita y posición.

===========================================================================
 GRUPOS (para qué sirven)
===========================================================================
Los reportes usan el grupo para redactar los textos automáticos, no para
graficar. Definen si una solicitud ya cerró o todavía se puede mover:

  CERRADA_POSITIVA -> negocio cerrado y cobrado (FINANCIADO)
  ABIERTA          -> todavía puede convertirse en financiado antes del
                      cierre de mes (APROBADO, CONTRAPROPUESTA, PENDIENTE...)
  CERRADA_NEGATIVA -> se cayó (RECHAZADO, CANCELADO)
"""

# ---------------------------------------------------------------------------
# PALETA DE CATEGORÍAS
#
# Criterio: cada categoría se distingue por TONO, no por intensidad. La
# versión anterior era casi toda de rojos (vino, rojo, rojo claro, rosa,
# gris) y en las gráficas —sobre todo en la dona y en las barras apiladas—
# las rebanadas se confundían entre sí. Ahora el rojo MG y el vino quedan
# reservados para el cierre del negocio (APROBADO y FINANCIADO), y el resto
# de los estatus usa tonos claramente separados entre ellos.
# ---------------------------------------------------------------------------
MG_VINO          = "#7A0019"   # FINANCIADO — el cierre más fuerte
MG_ROJO          = "#E4002B"   # APROBADO — rojo de marca
AMBAR            = "#F2A104"   # negociación en curso
INBURSA_AZUL     = "#191970"   # trámite operativo
AZUL_CLARO       = "#4C9BE8"   # análisis de crédito
TEAL             = "#12897F"   # esperando algo del cliente
PURPURA          = "#6A2C91"   # descartado por análisis (no financiable)
ROSA             = "#FF8FA3"   # rechazado
GRIS_MEDIO       = "#9CA3AF"   # cancelado / desistido
CAFE             = "#8B5E3C"   # primer contacto (sondeo)
CIAN_OSCURO      = "#0E7490"   # en fila del analista
OLIVO            = "#4D7C0F"   # validación interna
MAGENTA          = "#C2185B"   # excepciones (punto de decisión)
MOSTAZA          = "#A16207"   # esperando documentos del cliente

# Compatibilidad con nombres previos usados en otros módulos
MG_ROJO_OSCURO   = MG_VINO
MG_ROJO_MEDIO    = "#B3001B"
MG_ROJO_CLARO    = "#FF6B6B"
MG_ROJO_PASTEL   = ROSA
MG_GRIS_OSCURO   = "#2B2B2B"
MG_GRIS_MEDIO    = GRIS_MEDIO
MG_GRIS_CLARO    = "#EAEAEA"
AZUL_MEDIO       = AZUL_CLARO

# Colores de respaldo para estatus que aparezcan en la bitácora y NO estén
# en el catálogo. Antes eran todos rojos, así que un estatus nuevo salía
# casi idéntico a FINANCIADO. Ahora son tonos que no chocan con ninguno de
# los de arriba.
_PALETA_AUTOMATICA = ["#57534E",   # gris cálido
                      "#166534",   # verde bosque
                      "#5B21B6",   # violeta
                      "#B45309",   # naranja quemado
                      "#1E40AF",   # azul rey
                      "#831843",   # vino frambuesa
                      "#065F46",   # verde profundo
                      "#7C2D12"]   # terracota

CERRADA_POSITIVA = "cerrada_positiva"
ABIERTA          = "abierta"
CERRADA_NEGATIVA = "cerrada_negativa"


# ---------------------------------------------------------------------------
# ASIGNACIÓN DE COLORES POR PRESENCIA
#
# Antes cada estatus tenía su color propio de por vida (14 tonos: ámbar,
# olivo, magenta, café...). Aunque en la bitácora solo vinieran 4 estatus,
# las gráficas mostraban colores sueltos, fuera de la paleta de marca.
#
# Ahora solo FINANCIADO y APROBADO tienen color fijo (vino y rojo MG: son
# el cierre del negocio y deben verse igual en todos los reportes). El resto
# NO tiene color hasta que aparece en los datos: asignar_colores() recorre
# los estatus presentes en el orden del catálogo y les va entregando el
# siguiente color de la paleta de su grupo:
#
#   ABIERTA          -> azules Inbursa (y dorado de acento si hay muchos)
#   CERRADA_NEGATIVA -> grises (se cayó: neutro, sin competir con el rojo)
#
# Así, un mes con Financiado, Aprobado, Contrapropuesta y Rechazado sale
# en vino, rojo, azul Inbursa y gris: cuatro colores de marca.
# ---------------------------------------------------------------------------
COLORES_FIJOS = {
    "FINANCIADO": MG_VINO,
    "APROBADO": MG_ROJO,
    "SIN ESTATUS": "#D9DCE1",
}

# El orden importa: alterna oscuro / medio / claro para que dos estatus
# vecinos (en la dona o en las barras apiladas) nunca queden del mismo tono.
PALETA_ABIERTAS = [
    "#191970",   # azul Inbursa
    "#5B7FD6",   # azul medio
    "#B8C7EE",   # azul claro
    "#C9A227",   # dorado (acento)
    "#2F6F8F",   # azul petróleo
    "#E6CF8A",   # dorado claro
    "#6B6FA8",   # lavanda grisáceo
    "#8FB3C9",   # azul acero
]
PALETA_CERRADAS_NEG = [
    "#9CA3AF",   # gris medio
    "#4B5563",   # gris oscuro
    "#D1D5DB",   # gris claro
    "#6B7280",   # gris pizarra
]
_PALETA_POR_GRUPO = {ABIERTA: PALETA_ABIERTAS, CERRADA_NEGATIVA: PALETA_CERRADAS_NEG}


class Categoria:
    """Un estatus de la bitácora con todo lo que los reportes necesitan saber de él."""

    def __init__(self, clave, etiqueta, etiqueta_corta, descripcion,
                 sinonimos, color, grupo):
        self.clave = clave
        self.etiqueta = etiqueta
        self.etiqueta_corta = etiqueta_corta
        self.descripcion = descripcion
        self.sinonimos = [s.strip().upper() for s in sinonimos]
        self.color = color
        self.grupo = grupo


# ===========================================================================
#  EL CATÁLOGO — el orden de esta lista manda en tablas y gráficas
#  (del cierre más fuerte al más débil)
# ===========================================================================
CATALOGO = [
    Categoria(
        clave="FINANCIADO",
        etiqueta="Financiado",
        etiqueta_corta="Financiado",
        descripcion="quedaron <b>FINANCIADAS</b> (crédito ya dispersado)",
        sinonimos=["FINANCIADO", "FINANCIADOS", "FINANCIADA", "FINANCIADAS",
                   "DISPERSADO", "DISPERSADOS"],
        color=MG_VINO,
        grupo=CERRADA_POSITIVA,
    ),
    Categoria(
        clave="APROBADO",
        etiqueta="Aprobado",
        etiqueta_corta="Aprobado",
        descripcion="están <b>APROBADAS</b>, pendientes de dispersar",
        sinonimos=["APROBADO", "APROBADOS", "APROBADA", "APROBADAS",
                   "AUTORIZADO", "AUTORIZADOS"],
        color=MG_ROJO,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="CONTRAPROPUESTA",
        etiqueta="Contrapropuesta",
        etiqueta_corta="Contra-<br/>propuesta",
        descripcion="siguen en <b>CONTRAPROPUESTA</b>",
        sinonimos=["CONTRAPROPUESTA", "CONTRAPROPUESTAS", "CONTRA PROPUESTA",
                   "CONTRA-PROPUESTA"],
        color=AMBAR,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="EXCEPCIONES",
        etiqueta="Excepciones",
        etiqueta_corta="Excep-<br/>ciones",
        descripcion="están en <b>EXCEPCIONES</b> (definiendo si son candidatas al crédito)",
        sinonimos=["EXCEPCIONES", "EXCEPCION", "EXCEPCIÓN", "EN EXCEPCIONES",
                   "EN EXCEPCION", "EN EXCEPCIÓN"],
        color=MAGENTA,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="VALIDACION INTERNA",
        etiqueta="Validación interna",
        etiqueta_corta="Validación<br/>interna",
        descripcion="están en <b>VALIDACIÓN INTERNA</b>",
        sinonimos=["VALIDACION INTERNA", "VALIDACIÓN INTERNA",
                   "EN VALIDACION INTERNA", "EN VALIDACIÓN INTERNA",
                   "VALIDACION", "VALIDACIÓN", "EN VALIDACION", "EN VALIDACIÓN"],
        color=OLIVO,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="EN PROCESO",
        etiqueta="En proceso",
        etiqueta_corta="En<br/>proceso",
        descripcion="están <b>EN PROCESO</b> (expediente en trámite)",
        sinonimos=["EN PROCESO", "PROCESO", "EN TRAMITE", "EN TRÁMITE",
                   "TRAMITE", "TRÁMITE", "EN CURSO"],
        color=INBURSA_AZUL,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="EN REVISION",
        etiqueta="En revisión",
        etiqueta_corta="En<br/>revisión",
        descripcion="están <b>EN REVISIÓN</b> (análisis de crédito)",
        # OJO: "ANALISIS" y "EN ANALISIS" YA NO son sinónimos de este estatus.
        # ANÁLISIS pasó a ser su propia categoría (fila de trabajo del
        # analista), que es una etapa anterior a la revisión de crédito.
        sinonimos=["EN REVISION", "EN REVISIÓN", "REVISION", "REVISIÓN"],
        color=AZUL_CLARO,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="ANALISIS",
        etiqueta="Análisis",
        etiqueta_corta="Análisis",
        descripcion="están en <b>ANÁLISIS</b> (en fila de trabajo del analista)",
        sinonimos=["ANALISIS", "ANÁLISIS", "EN ANALISIS", "EN ANÁLISIS",
                   "EN FILA", "FILA DE ANALISIS"],
        color=CIAN_OSCURO,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="DOCUMENTACION ADICIONAL",
        etiqueta="Documentación adicional",
        etiqueta_corta="Docum.<br/>adicional",
        descripcion="requieren <b>DOCUMENTACIÓN ADICIONAL</b> del cliente",
        sinonimos=["DOCUMENTACION ADICIONAL", "DOCUMENTACIÓN ADICIONAL",
                   "DOC ADICIONAL", "DOCS ADICIONALES", "DOCUMENTOS ADICIONALES",
                   "DOCUMENTACION", "DOCUMENTACIÓN"],
        color=MOSTAZA,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="PENDIENTE",
        etiqueta="Pendiente",
        etiqueta_corta="Pendiente",
        descripcion="están <b>PENDIENTES</b> de información o documentos",
        sinonimos=["PENDIENTE", "PENDIENTES", "EN ESPERA", "ESPERA"],
        color=TEAL,
        grupo=ABIERTA,
    ),
    Categoria(
        clave="SONDEO",
        etiqueta="Sondeo",
        etiqueta_corta="Sondeo",
        descripcion="están en <b>SONDEO</b> (validando y confirmando datos con el cliente)",
        sinonimos=["SONDEO", "SONDEOS", "EN SONDEO", "SONDEO INICIAL"],
        color=CAFE,
        grupo=ABIERTA,
    ),
    # ─────────────────────────────────────────────────────────────────────
    # NO FINANCIABLE es lo contrario de FINANCIADO: la solicitud SÍ pasó la
    # aprobación, pero tras el análisis y estudio del expediente se resolvió
    # no financiarla. Es un cierre definitivo, no un trámite en curso: por
    # eso va en CERRADA_NEGATIVA y NO aparece en la frase "todavía pueden
    # convertirse en FINANCIADAS antes del cierre".
    # ─────────────────────────────────────────────────────────────────────
    Categoria(
        clave="NO FINANCIABLE",
        etiqueta="No financiable",
        etiqueta_corta="No<br/>financiable",
        descripcion="resultaron <b>NO FINANCIABLES</b> tras el análisis",
        sinonimos=["NO FINANCIABLE", "NO FINANCIABLES",
                   "NO FINANCIADO", "NO FINANCIADOS",
                   "NO FINANCIADA", "NO FINANCIADAS",
                   "NO FINANCIAMIENTO"],
        color=PURPURA,
        grupo=CERRADA_NEGATIVA,
    ),
    Categoria(
        clave="RECHAZADO",
        etiqueta="Rechazado",
        etiqueta_corta="Rechazado",
        descripcion="fueron <b>RECHAZADAS</b>",
        sinonimos=["RECHAZADO", "RECHAZADOS", "RECHAZADA", "RECHAZADAS",
                   "DECLINADO", "DECLINADOS", "NEGADO", "NEGADOS"],
        color=ROSA,
        grupo=CERRADA_NEGATIVA,
    ),
    # ─────────────────────────────────────────────────────────────────────
    # OJO — CAMBIO DE CRITERIO RESPECTO A LOS REPORTES ANTERIORES:
    # antes CANCELADO se contaba DENTRO de RECHAZADO. Ahora es su propia
    # categoría, así que los números de "Rechazadas" pueden verse más bajos
    # que en reportes de meses pasados.
    #
    # Si prefieres el comportamiento anterior (cancelado = rechazado):
    #   1. borra este bloque completo, y
    #   2. agrega "CANCELADO", "CANCELADOS" a los sinónimos de RECHAZADO.
    # ─────────────────────────────────────────────────────────────────────
    Categoria(
        clave="CANCELADO",
        etiqueta="Cancelado",
        etiqueta_corta="Cancelado",
        descripcion="se <b>CANCELARON</b> por desistimiento del cliente",
        sinonimos=["CANCELADO", "CANCELADOS", "CANCELADA", "CANCELADAS",
                   "DESISTIDO", "DESISTIMIENTO"],
        color=GRIS_MEDIO,
        grupo=CERRADA_NEGATIVA,
    ),
]

# Etiqueta que se usa cuando la celda de STATUS viene vacía en el Excel.
CLAVE_SIN_ESTATUS = "SIN ESTATUS"

_VACIOS = {"", "NAN", "NONE", "NAT", "-", "--", "N/A", "NA", "SIN STATUS",
           "SIN ESTATUS"}


# ===========================================================================
#  ESTRUCTURAS QUE CONSUMEN LOS REPORTES
#  Son objetos MUTABLES compartidos: los 3 reportes importan estos mismos
#  objetos, así que cuando registrar_categorias() descubre un estatus nuevo
#  en la bitácora, aparece en los tres sin tener que pasarlo por parámetro.
# ===========================================================================
ORDEN_CATEGORIAS = [c.clave for c in CATALOGO]
COLOR_CATEGORIA  = {}   # se llena con asignar_colores() (más abajo)
ETIQUETA_CATEGORIA = {c.clave: c.etiqueta for c in CATALOGO}
ETIQUETA_CORTA_CATEGORIA = {c.clave: c.etiqueta_corta for c in CATALOGO}
DESCRIPCION_CATEGORIA = {c.clave: c.descripcion for c in CATALOGO}
GRUPO_CATEGORIA = {c.clave: c.grupo for c in CATALOGO}

# índice sinónimo -> clave, armado una sola vez
_INDICE_SINONIMOS = {}
for _c in CATALOGO:
    for _s in _c.sinonimos:
        _INDICE_SINONIMOS[_s] = _c.clave

def clasificar_status(status):
    """
    Convierte el STATUS crudo del Excel en la clave de categoría.

    A diferencia de la versión anterior, un estatus desconocido YA NO se
    manda a "CONTRAPROPUESTA": se devuelve tal cual (en mayúsculas) para
    que se cuente y se grafique como categoría propia.
    """
    s = str(status).strip().upper()
    if s in _VACIOS:
        return CLAVE_SIN_ESTATUS
    return _INDICE_SINONIMOS.get(s, s)


def registrar_categorias(categorias):
    """
    Da de alta las categorías que aparecieron en la bitácora y que no están
    en el catálogo, para que tengan color y lugar en el orden de graficado.

    Se llama desde limpiar_datos() de cada reporte. Es idempotente: llamarla
    varias veces (o en varias corridas de la app de Streamlit) no duplica.
    """
    nuevas = []
    for clave in categorias:
        if clave is None:
            continue
        clave = str(clave).strip().upper()
        if not clave or clave in ORDEN_CATEGORIAS:
            continue
        ORDEN_CATEGORIAS.append(clave)
        nuevas.append(clave)

    for clave in nuevas:
        bonita = clave.capitalize()
        ETIQUETA_CATEGORIA.setdefault(clave, bonita)
        ETIQUETA_CORTA_CATEGORIA.setdefault(clave, bonita)
        DESCRIPCION_CATEGORIA.setdefault(clave, clave)
        # Sin información para clasificarla, se asume que sigue viva
        GRUPO_CATEGORIA.setdefault(clave, ABIERTA)
        # Color provisional: el definitivo lo da asignar_colores() al graficar.
        COLOR_CATEGORIA.setdefault(clave, PALETA_ABIERTAS[-1])
        print(f"  ℹ Estatus no catalogado detectado: '{clave}'. Se grafica como "
              f"categoría propia. Para fijarle color y etiqueta, agrégalo al "
              f"CATALOGO en herramientas/estatus.py")

    return nuevas


def asignar_colores(presentes=None):
    """Reparte los colores entre los estatus que REALMENTE vienen en los datos.

    presentes: claves de categoría (o una Serie de pandas, p. ej.
        df["Categoria"]). Si es None, se toman todas las conocidas.

    Reescribe COLOR_CATEGORIA en su lugar (mismo objeto) para que todas las
    gráficas lo vean sin pasarlo por parámetro. Se llama al inicio de cada
    tanda de gráficas; como empieza desde cero, lo que se cargó en una corrida
    anterior de Streamlit no se arrastra a la siguiente.

    Los estatus ausentes quedan SIN color: no consumen lugar en la paleta.
    """
    if presentes is None:
        conjunto = set(ORDEN_CATEGORIAS)
    else:
        valores = presentes.dropna().unique() if hasattr(presentes, "dropna") else presentes
        conjunto = {str(v).strip().upper() for v in valores if v is not None}
    # Orden del catálogo (y al final los no catalogados, en el orden visto)
    orden = [c for c in ORDEN_CATEGORIAS if c in conjunto]
    orden += sorted(c for c in conjunto if c not in orden)

    COLOR_CATEGORIA.clear()
    usados = {grupo: 0 for grupo in _PALETA_POR_GRUPO}
    for clave in orden:
        if clave in COLORES_FIJOS:
            COLOR_CATEGORIA[clave] = COLORES_FIJOS[clave]
            continue
        grupo = GRUPO_CATEGORIA.get(clave, ABIERTA)
        if grupo not in _PALETA_POR_GRUPO:   # CERRADA_POSITIVA no catalogada
            grupo = ABIERTA
        paleta = _PALETA_POR_GRUPO[grupo]
        COLOR_CATEGORIA[clave] = paleta[usados[grupo] % len(paleta)]
        usados[grupo] += 1
    return dict(COLOR_CATEGORIA)


# Estado inicial (por si alguna gráfica se dibuja sin llamar antes a
# asignar_colores): todos los estatus del catálogo, con la misma regla.
asignar_colores()


_CLAVES_CATALOGADAS = frozenset(c.clave for c in CATALOGO)


def esta_catalogado(clave):
    """¿Esta categoría está definida en el CATALOGO, o se detectó sola?

    Las detectadas se grafican igual, pero con color automático y sin
    etiqueta propia, así que conviene poder avisarlo en la interfaz.
    """
    return str(clave).strip().upper() in _CLAVES_CATALOGADAS


def categorias_presentes(df, columna="Categoria"):
    """
    Categorías que REALMENTE aparecen en este DataFrame, en el orden del
    catálogo. Se usa en vez de ORDEN_CATEGORIAS completo para no llenar las
    tablas de columnas en cero.
    """
    if columna not in df.columns:
        return []
    valores = set(df[columna].dropna().unique())
    return [c for c in ORDEN_CATEGORIAS if c in valores]


def color(clave):
    return COLOR_CATEGORIA.get(clave, MG_GRIS_CLARO)


def etiqueta(clave):
    return ETIQUETA_CATEGORIA.get(clave, str(clave).capitalize())


def etiqueta_corta(clave):
    return ETIQUETA_CORTA_CATEGORIA.get(clave, str(clave).capitalize())


def descripcion(clave):
    return DESCRIPCION_CATEGORIA.get(clave, str(clave))


def claves_por_grupo(*grupos):
    """Claves del catálogo (más las detectadas) que pertenecen a esos grupos."""
    return [c for c in ORDEN_CATEGORIAS if GRUPO_CATEGORIA.get(c, ABIERTA) in grupos]


def lista_etiquetas(claves, separador=" / "):
    """'Financiado / Aprobado / En proceso' — para títulos de gráficas."""
    return separador.join(etiqueta(c) for c in claves)


def frase_enumerada(claves, y="y", mayusculas=False):
    """'Financiado, Aprobado y En proceso' — para textos narrativos.

    mayusculas=True pone en versalitas SOLO las etiquetas, nunca la
    conjunción. Antes el código hacía frase_enumerada(...).upper() sobre
    toda la frase y salía "EN REVISIÓN Y PENDIENTE y algunas RECHAZADAS":
    dos conjunciones seguidas, una gritando y otra no.
    """
    etiquetas = [etiqueta(c) for c in claves]
    if mayusculas:
        etiquetas = [e.upper() for e in etiquetas]
    if not etiquetas:
        return ""
    if len(etiquetas) == 1:
        return etiquetas[0]
    return ", ".join(etiquetas[:-1]) + f" {y} " + etiquetas[-1]


def frase_desglose(conteo, total):
    """
    Arma la frase del panorama general enumerando TODAS las categorías
    presentes, en vez de las 4 que estaban escritas a mano en el PDF.

    conteo: dict {clave: n}
    Devuelve, por ejemplo:
      "18 (45.0%) llegaron a FINANCIADAS (crédito ya dispersado), 9 (22.5%)
       están APROBADAS (aprobadas, aún sin dispersar) y 3 (7.5%) están
       EN PROCESO (expediente en trámite)"
    """
    if not total:
        return ""
    # Cada categoría lleva su propio verbo. Sin él, la enumeración quedaba
    # como una lista de sintagmas sin oración: "13 (19.7%) FINANCIADAS,
    # 5 (7.6%) APROBADAS, 8 (12.1%) en CONTRAPROPUESTA..." — agramatical.
    partes = []
    for clave in ORDEN_CATEGORIAS:
        n = int(conteo.get(clave, 0))
        if n:
            partes.append(f"{n} ({n / total * 100:.1f}%) {descripcion(clave)}")
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


# ---------------------------------------------------------------------------
# Compatibilidad hacia atrás: los reportes viejos importaban estas listas.
# Se derivan del catálogo para que nadie tenga que mantenerlas a mano.
# ---------------------------------------------------------------------------
STATUS_FINANCIADO = list(_INDICE_SINONIMOS.keys() and
                         [s for s, c in _INDICE_SINONIMOS.items() if c == "FINANCIADO"])
STATUS_APROBADO   = [s for s, c in _INDICE_SINONIMOS.items() if c == "APROBADO"]
STATUS_RECHAZADOS = [s for s, c in _INDICE_SINONIMOS.items() if c == "RECHAZADO"]
