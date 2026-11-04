"""Estilos visuales de la app.

Está aparte de streamlit_app.py a propósito: el CSS es largo y no tiene
nada que ver con la lógica de generar reportes. Si mañana cambia el look,
se toca este archivo (y .streamlit/config.toml) y nada más.

Dirección de diseño
-------------------
Tema oscuro con tres colores:

- Midnight Black (#02070A): el fondo de todo; tarjetas un tono más claro
  (#07131B) con borde fino.
- Electric Blue (#0297DE): lo activo y lo que guía: la herramienta elegida
  en el menú, el número de cada paso, el borde de la zona para soltar el
  archivo y un brillo tenue arriba a la derecha.
- Cantaloupe Orange (#FC734D): solo la acción principal, "Generar reporte",
  con texto negro (contraste 7:1), y la tarjeta de descargas.
- Tipografía: Instrument Serif para el título de cada herramienta (la
  última palabra en cursiva), Inter para el texto y JetBrains Mono para
  etiquetas, nombres de archivo y el detalle del proceso.
- Navegación en barra lateral y cada herramienta en tarjetas numeradas:
  archivo -> datos -> descargas.
"""

import html
import re

import streamlit as st

# --- Tokens ---------------------------------------------------------------
NEGRO        = "#02070A"   # Midnight Black: fondo
AZUL         = "#0297DE"   # Electric Blue
NARANJA      = "#FC734D"   # Cantaloupe Orange
FONDO        = NEGRO
LATERAL      = "#050E14"   # barra lateral
TARJETA      = "#07131B"   # card
MUTED        = "#0D1D28"   # botones secundarios, campos
BORDE        = "#1C2A33"
BORDE_FUERTE = "#2D3E49"
TEXTO        = "#F2F5F7"
TEXTO_SUAVE  = "#A9B4BC"   # 8.6:1 sobre el fondo
TEXTO_TENUE  = "#7D8A93"   # 5.6:1 sobre el fondo
AZUL_TEXTO   = "#6CC6F2"   # azul para texto pequeño (8.9:1)
ACENTO       = NARANJA     # primary
ACENTO_HOVER = "#FD8B6B"
ANILLO       = AZUL        # ring

# Color e etiqueta por tipo de archivo en la lista de descargas.
TIPOS_ARCHIVO = {
    "pdf":  ("PDF",    NARANJA,   ":material/picture_as_pdf:"),
    "docx": ("Word",   AZUL,      ":material/description:"),
    "xlsx": ("Excel",  "#34C38F", ":material/table_chart:"),
    "png":  ("Imagen", "#A9B4BC", ":material/image:"),
    "zip":  ("ZIP",    "#F5B54A", ":material/folder_zip:"),
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
  --fondo: {FONDO};
  --lateral: {LATERAL};
  --tarjeta: {TARJETA};
  --muted: {MUTED};
  --borde: {BORDE};
  --borde-fuerte: {BORDE_FUERTE};
  --texto: {TEXTO};
  --texto-suave: {TEXTO_SUAVE};
  --texto-tenue: {TEXTO_TENUE};
  --azul: {AZUL};
  --azul-texto: {AZUL_TEXTO};
  --naranja: {NARANJA};
  --acento: {ACENTO};
  --acento-hover: {ACENTO_HOVER};
  --anillo: {ANILLO};
  --radio: 0.75rem;
  --serif: 'Instrument Serif', Georgia, serif;
  --mono: 'JetBrains Mono', ui-monospace, monospace;
}}

/* ---------- Base ---------- */
.stApp {{
  background:
    radial-gradient(ellipse 55% 34% at 92% 0%, rgba(2, 151, 222, 0.20) 0%, rgba(2, 151, 222, 0) 70%),
    radial-gradient(ellipse 40% 26% at 70% 100%, rgba(252, 115, 77, 0.07) 0%, rgba(252, 115, 77, 0) 70%),
    var(--fondo);
  background-attachment: fixed;
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.75rem; padding-bottom: 4rem; max-width: 52rem; }}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"] {{ background: var(--lateral); border-right: 1px solid var(--borde); }}
[data-testid="stSidebarContent"] {{ padding-top: 0.25rem; }}
[data-testid="stSidebarHeader"] {{ height: 1.25rem; min-height: 0; padding: 0; }}

.gr-marca {{ display: flex; align-items: center; gap: 0.7rem; padding: 0.25rem 0.25rem 1.2rem; }}
.gr-marca-logo {{ flex: none; display: grid; place-items: center; width: 2.1rem; height: 2.1rem; }}
.gr-marca-titulo {{ font-weight: 600; font-size: 0.92rem; color: var(--texto); line-height: 1.25; }}
.gr-marca-sub {{ font-size: 0.74rem; color: var(--texto-suave); line-height: 1.3; }}

.gr-grupo {{
  font-family: var(--mono); font-size: 0.66rem; font-weight: 500; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--texto-tenue);
  padding: 1rem 0.65rem 0.45rem; border-top: 1px solid var(--borde);
}}

/* Menú de herramientas: el radio se dibuja como lista de navegación.
   Estructura de Streamlit 1.63: label[data-testid=stRadioOption] >
   div > div > [div del círculo] + [stMarkdownContainer]. */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
[data-testid="stSidebar"] [data-testid="stRadio"],
[data-testid="stSidebar"] [data-testid="stRadio"] > div,
[data-testid="stSidebar"] [data-testid="stRadioGroup"] {{ gap: 3px; width: 100%; max-width: none; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"] {{
  width: 100%; box-sizing: border-box; margin: 0; min-height: 2.75rem;
  padding: 0.55rem 0.75rem; border-radius: 0.65rem;
  display: flex; align-items: center;
  cursor: pointer; transition: background 120ms ease;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div > div:not([data-testid="stMarkdownContainer"]) {{
  display: none;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p {{
  font-size: 0.875rem; font-weight: 500; color: #C7D1D8;
  display: flex; align-items: center; gap: 0.7rem; margin: 0;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p [role="img"] {{ font-size: 1.15rem; color: var(--texto-suave); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {{ background: rgba(242, 245, 247, 0.05); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover p {{ color: var(--texto); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {{
  background: rgba(2, 151, 222, 0.18);
  box-shadow: inset 0 0 0 1px rgba(2, 151, 222, 0.5);
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {{ color: #FFFFFF; font-weight: 600; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p [role="img"] {{ color: var(--azul-texto); }}

.gr-nota-lateral {{
  display: flex; gap: 0.6rem; align-items: flex-start;
  margin-top: 1.75rem; padding: 0.85rem; border-radius: var(--radio);
  border: 1px solid var(--borde); background: rgba(242, 245, 247, 0.03);
  font-size: 0.75rem; line-height: 1.5; color: var(--texto-suave);
}}
.gr-nota-lateral svg {{ flex: none; margin-top: 2px; color: var(--azul-texto); }}

/* ---------- Encabezado de la herramienta ---------- */
.gr-migas {{ font-family: var(--mono); font-size: 0.72rem; color: var(--texto-tenue); margin-bottom: 0.75rem; }}
.gr-migas b {{ color: var(--texto-suave); font-weight: 500; }}
.gr-titulo {{
  font-family: var(--serif); font-weight: 400;
  font-size: 3.4rem; letter-spacing: -0.01em; line-height: 1;
  color: var(--texto); margin: 0 0 0.8rem;
}}
.gr-titulo em {{ font-style: italic; }}
[data-testid="stMarkdownContainer"] p.gr-bajada {{ font-size: 0.95rem; line-height: 1.6; color: var(--texto-suave); margin: 0 0 1rem; max-width: 42rem; }}
.gr-badges {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.8rem; }}
.gr-badge {{
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.22rem 0.6rem; border-radius: 0.4rem;
  border: 1px solid var(--borde-fuerte); background: transparent;
  font-family: var(--mono); font-size: 0.68rem; font-weight: 500;
  color: #C7D1D8; white-space: nowrap;
}}
.gr-badge-solido {{ background: var(--muted); color: var(--texto); }}
.gr-punto {{ width: 0.5rem; height: 0.5rem; border-radius: 999px; display: inline-block;
  box-shadow: 0 0 0 1px rgba(242, 245, 247, 0.2); }}

/* ---------- Tarjetas (st.container(border=True)) ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] .gr-paso),
div[class*="st-key-tarjeta_"] {{
  background: var(--tarjeta);
  border-color: var(--borde) !important;
  border-radius: 1.1rem !important;
  box-shadow: none;
}}
div[class*="st-key-tarjeta_"] {{ padding: 1.4rem 1.5rem 1.5rem !important; }}
div.st-key-tarjeta_descargas {{
  background: linear-gradient(135deg, rgba(2, 151, 222, 0.13) 0%, rgba(252, 115, 77, 0.11) 100%), var(--tarjeta);
  border-color: rgba(252, 115, 77, 0.35) !important;
}}

.gr-paso {{ display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.45rem; }}
.gr-paso-num {{
  font-family: var(--mono); font-size: 0.7rem; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--azul-texto);
}}
div.st-key-tarjeta_descargas .gr-paso-num {{ color: #FDA58C; }}
[data-testid="stMarkdownContainer"] p.gr-paso-titulo {{ font-size: 1.05rem; font-weight: 600; color: var(--texto); line-height: 1.4; margin: 0; }}
[data-testid="stMarkdownContainer"] p.gr-paso-ayuda {{ font-size: 0.82rem; color: var(--texto-suave); margin: 0.1rem 0 0; line-height: 1.5; }}

/* ---------- Carga de archivos ---------- */
[data-testid="stFileUploaderDropzone"] {{
  background: rgba(2, 151, 222, 0.06);
  border: 1.5px dashed rgba(2, 151, 222, 0.6);
  border-radius: var(--radio);
  padding: 1.35rem 1.35rem;
  transition: border-color 140ms ease, background 140ms ease;
}}
[data-testid="stFileUploaderDropzone"]:hover {{ border-color: var(--azul); background: rgba(2, 151, 222, 0.11); }}
[data-testid="stFileUploaderDropzone"] svg {{ color: var(--azul-texto); }}
[data-testid="stFileUploaderDropzone"] button {{
  background: var(--muted); border: 1px solid var(--borde-fuerte); color: var(--texto);
  font-weight: 500;
}}
[data-testid="stFileUploaderFile"] {{ font-family: var(--mono); }}

/* ---------- Resumen de lo leído ---------- */
.gr-lectura {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.9rem;
  margin-top: 0.9rem; padding: 0.8rem 0.95rem;
  border: 1px solid var(--borde); border-radius: var(--radio); background: rgba(2, 7, 10, 0.55);
}}
.gr-lectura-cifra {{ font-size: 0.85rem; color: var(--texto-suave); }}
.gr-lectura-cifra b {{ font-family: var(--serif); font-size: 1.6rem; font-weight: 400; color: var(--texto); margin-right: 0.2rem; }}
.gr-lectura .gr-badges {{ margin: 0; }}

/* ---------- Campos ---------- */
.stTextInput input, .stTextArea textarea, .stDateInput input {{ font-size: 0.9rem; }}
[data-testid="stTextInputRootElement"], [data-testid="stTextArea"] textarea, [data-testid="stDateInputField"] {{
  background: var(--fondo);
}}
[data-testid="stWidgetLabel"] p {{ font-size: 0.82rem; font-weight: 500; color: #C7D1D8; }}

/* ---------- Botón principal ---------- */
.stButton > button[kind="primary"] {{
  background: var(--acento); border: 1px solid var(--acento); color: {NEGRO};
  font-weight: 600; font-size: 0.95rem; height: 3.1rem;
  transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
}}
.stButton > button[kind="primary"] p {{ font-weight: 600; }}
.stButton > button[kind="primary"]:hover:not(:disabled) {{
  background: var(--acento-hover); border-color: var(--acento-hover); color: {NEGRO};
  box-shadow: 0 10px 30px rgba(252, 115, 77, 0.28);
}}
.stButton > button[kind="primary"]:disabled {{
  background: var(--muted); border-color: var(--borde); color: var(--texto-tenue); opacity: 1;
}}

/* ---------- Lista de descargas ---------- */
div[class*="st-key-archivo_"] {{
  border: 1px solid var(--borde); border-radius: var(--radio);
  background: rgba(2, 7, 10, 0.72); padding: 0.6rem 0.65rem 0.6rem 0.75rem;
  transition: border-color 120ms ease;
}}
div[class*="st-key-archivo_"]:hover {{ border-color: var(--borde-fuerte); }}
.gr-archivo {{ display: flex; align-items: center; gap: 0.85rem; min-width: 0; }}
.gr-archivo-icono {{
  flex: none; width: 2.5rem; height: 2.5rem; border-radius: 0.55rem;
  display: grid; place-items: center;
  font-family: var(--mono); font-size: 0.6rem; font-weight: 500; letter-spacing: 0.04em;
}}
.gr-archivo-texto {{ min-width: 0; }}
.gr-archivo-nombre {{
  font-family: var(--mono); font-size: 0.8rem; color: var(--texto);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.gr-archivo-meta {{ font-size: 0.74rem; color: var(--texto-suave); margin-top: 0.15rem; }}
.stDownloadButton > button {{
  background: var(--texto); border: 1px solid var(--texto); color: {NEGRO};
  font-weight: 600; font-size: 0.84rem; height: 2.5rem;
}}
.stDownloadButton > button:hover {{ background: #FFFFFF; border-color: #FFFFFF; color: {NEGRO}; }}

/* ---------- Avisos, expanders y código ---------- */
[data-testid="stAlert"] {{ border-radius: var(--radio); font-size: 0.86rem; }}
[data-testid="stExpander"] details {{ border-color: var(--borde); border-radius: var(--radio); background: transparent; }}
[data-testid="stExpander"] summary p {{ font-size: 0.85rem; font-weight: 500; color: var(--texto-suave); }}
[data-testid="stExpander"] summary:hover p {{ color: var(--texto); }}
[data-testid="stCode"] pre, .stCode pre {{ font-size: 0.75rem !important; }}

/* Accesibilidad */
*:focus-visible {{ outline: 2px solid var(--anillo); outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; animation: none !important; }}
}}
@media (max-width: 640px) {{
  .gr-titulo {{ font-size: 2.5rem; }}
  .block-container {{ padding-top: 1.5rem; }}
  div[class*="st-key-tarjeta_"] {{ padding: 1.1rem !important; }}
}}
</style>
"""

_CANDADO = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
)


def _html(contenido: str):
    st.markdown(contenido, unsafe_allow_html=True)


def aplicar_estilos():
    """Inyecta el CSS. Se llama una sola vez, justo después de
    st.set_page_config()."""
    _html(_CSS)


# --- Barra lateral --------------------------------------------------------
# Barras en los tres colores: la "señal" de la marca.
_LOGO = (
    '<svg width="26" height="20" viewBox="0 0 26 20" aria-hidden="true">'
    f'<rect x="0" y="7" width="3" height="6" rx="1.5" fill="{AZUL}"/>'
    f'<rect x="5" y="3" width="3" height="14" rx="1.5" fill="{AZUL}"/>'
    f'<rect x="10" y="0" width="3" height="20" rx="1.5" fill="{TEXTO}"/>'
    f'<rect x="15" y="4" width="3" height="12" rx="1.5" fill="{NARANJA}"/>'
    f'<rect x="20" y="8" width="3" height="4" rx="1.5" fill="{NARANJA}"/></svg>'
)


def marca(titulo: str, subtitulo: str, logo: str = ""):
    """Logo, nombre de la app y subtítulo. `logo` queda por compatibilidad:
    el logo ahora es el dibujo de barras."""
    _html(
        f'<div class="gr-marca"><div class="gr-marca-logo">{_LOGO}</div>'
        f'<div><div class="gr-marca-titulo">{titulo}</div>'
        f'<div class="gr-marca-sub">{subtitulo}</div></div></div>'
    )


def grupo(texto: str):
    _html(f'<div class="gr-grupo">{texto}</div>')


def nota_lateral(texto: str):
    _html(f'<div class="gr-nota-lateral">{_CANDADO}<span>{texto}</span></div>')


# --- Contenido principal --------------------------------------------------
def badges(textos, solido=False):
    clase = "gr-badge gr-badge-solido" if solido else "gr-badge"
    return "".join(f'<span class="{clase}">{html.escape(t)}</span>' for t in textos)


def _titulo_con_cursiva(nombre: str) -> str:
    """"Resumen Mensual" -> "Resumen <em>Mensual</em>": la última palabra va
    en cursiva, como en el diseño. Lo que va entre paréntesis ("(ZIP →
    Excel)") se queda fuera del título: ya lo dicen las etiquetas."""
    nombre = re.sub(r"\s*\(.*\)\s*$", "", nombre).strip()
    partes = nombre.rsplit(" ", 1)
    if len(partes) == 1:
        return f"<em>{html.escape(nombre)}</em>"
    return f"{html.escape(partes[0])} <em>{html.escape(partes[1])}</em>"


def encabezado(nombre: str, descripcion: str, etiquetas=()):
    """Migas, título, descripción y badges de la herramienta elegida."""
    _html(
        f'<div class="gr-migas">Herramientas &nbsp;/&nbsp; <b>{html.escape(nombre)}</b></div>'
        f'<div class="gr-titulo" role="heading" aria-level="1">{_titulo_con_cursiva(nombre)}</div>'
        f'<p class="gr-bajada">{html.escape(descripcion)}</p>'
        f'<div class="gr-badges">{badges(etiquetas)}</div>'
    )


def paso(numero: int, titulo: str, ayuda: str = ""):
    """Título numerado al inicio de cada tarjeta."""
    texto_ayuda = f'<p class="gr-paso-ayuda">{html.escape(ayuda)}</p>' if ayuda else ""
    _html(
        f'<div class="gr-paso"><div class="gr-paso-num">Paso {numero}</div>'
        f'<div><p class="gr-paso-titulo">{html.escape(titulo)}</p>{texto_ayuda}</div></div>'
    )


def resumen_lectura(filas: int, estatus):
    """Cifra de solicitudes leídas + un badge por estatus con su color.

    estatus: lista de (etiqueta, cantidad, color_hex)."""
    chips = "".join(
        f'<span class="gr-badge"><span class="gr-punto" style="background:{color}"></span>'
        f'{html.escape(str(etiqueta))} · {n}</span>'
        for etiqueta, n, color in estatus
    )
    _html(
        f'<div class="gr-lectura"><span class="gr-lectura-cifra"><b>{filas:,}</b> solicitudes</span>'
        f'<div class="gr-badges">{chips}</div></div>'
    )


def _tamano(n_bytes: int) -> str:
    for unidad in ("B", "KB", "MB"):
        if n_bytes < 1024 or unidad == "MB":
            return f"{n_bytes:.0f} {unidad}" if unidad == "B" else f"{n_bytes:.1f} {unidad}"
        n_bytes /= 1024


def fila_archivo(nombre: str, contenido: bytes):
    """Icono de tipo + nombre + tipo/tamaño (la parte izquierda de la fila)."""
    extension = nombre.rsplit(".", 1)[-1].lower()
    etiqueta, color, _ = TIPOS_ARCHIVO.get(extension, (extension.upper(), TEXTO_SUAVE, ""))
    _html(
        f'<div class="gr-archivo">'
        f'<div class="gr-archivo-icono" style="color:{NEGRO};background:{color}">'
        f'{html.escape(extension.upper())}</div>'
        f'<div class="gr-archivo-texto"><div class="gr-archivo-nombre" title="{html.escape(nombre)}">'
        f'{html.escape(nombre)}</div>'
        f'<div class="gr-archivo-meta">{etiqueta} · {_tamano(len(contenido))}</div></div></div>'
    )


# Los nombres de las herramientas traen un emoji al inicio ("📁 Relación de
# Clientes"). En el menú se usa un icono propio, así que el emoji se quita
# solo para mostrar; el registro no se toca.
_EMOJI_INICIAL = re.compile(r"^[^\w(]+", flags=re.UNICODE)


def nombre_limpio(nombre: str) -> str:
    return _EMOJI_INICIAL.sub("", nombre).strip()
