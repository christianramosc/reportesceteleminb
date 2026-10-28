# -*- coding: utf-8 -*-
"""Estilos visuales de la app.

Está aparte de streamlit_app.py a propósito: el CSS es largo y no tiene
nada que ver con la lógica de generar reportes. Si mañana cambia el look,
se toca este archivo (y .streamlit/config.toml) y nada más.

Dirección de diseño
-------------------
Tema claro con el sistema de diseño de shadcn/ui, adaptado a Streamlit
(shadcn es una librería de React; aquí se replican sus tokens y patrones
sobre los componentes nativos, que siguen funcionando igual):

- Paleta "zinc" clara: página gris muy tenue, tarjetas blancas con borde
  fino de 1px y sombra mínima, texto casi negro y secundario gris.
- Un solo acento rojo (#DC2626, la variante "red" de shadcn y cercano al
  rojo de MG), reservado para la acción principal: "Generar reporte".
- Tipografía Geist (la de shadcn/Vercel) y Geist Mono para nombres de
  archivo y el detalle del proceso.
- Navegación en barra lateral, como el "sidebar" de shadcn, y cada
  herramienta ordenada en tarjetas numeradas: archivo -> datos -> descargas.
"""

import html
import re

import streamlit as st

# --- Tokens (shadcn/ui, tema zinc claro) ---------------------------------
FONDO        = "#FAFAFA"   # background de la página
TARJETA      = "#FFFFFF"   # card
MUTED        = "#F4F4F5"   # muted / secondary
BORDE        = "#E4E4E7"   # border / input
BORDE_FUERTE = "#D4D4D8"   # borde al pasar el mouse
TEXTO        = "#09090B"   # foreground
TEXTO_SUAVE  = "#52525B"   # texto secundario
TEXTO_TENUE  = "#71717A"   # muted-foreground
ACENTO       = "#DC2626"   # primary (red)
ACENTO_HOVER = "#B91C1C"
ANILLO       = "#A1A1AA"   # ring

# Color e etiqueta por tipo de archivo en la lista de descargas.
TIPOS_ARCHIVO = {
    "pdf":  ("PDF",    "#DC2626", ":material/picture_as_pdf:"),
    "docx": ("Word",   "#2563EB", ":material/description:"),
    "xlsx": ("Excel",  "#16A34A", ":material/table_chart:"),
    "png":  ("Imagen", "#9333EA", ":material/image:"),
    "zip":  ("ZIP",    "#D97706", ":material/folder_zip:"),
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');

:root {{
  --fondo: {FONDO};
  --tarjeta: {TARJETA};
  --muted: {MUTED};
  --borde: {BORDE};
  --borde-fuerte: {BORDE_FUERTE};
  --texto: {TEXTO};
  --texto-suave: {TEXTO_SUAVE};
  --texto-tenue: {TEXTO_TENUE};
  --acento: {ACENTO};
  --acento-hover: {ACENTO_HOVER};
  --anillo: {ANILLO};
  --radio: 0.625rem;
}}

/* ---------- Base ---------- */
.stApp {{ background: var(--fondo); }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.75rem; padding-bottom: 4rem; max-width: 50rem; }}
h1, h2, h3, h4 {{ letter-spacing: -0.025em; }}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"] {{ border-right: 1px solid var(--borde); }}
[data-testid="stSidebarContent"] {{ padding-top: 0.25rem; }}
[data-testid="stSidebarHeader"] {{ height: 1.25rem; min-height: 0; padding: 0; }}

.gr-marca {{ display: flex; align-items: center; gap: 0.7rem; padding: 0.25rem 0.25rem 1.1rem; }}
.gr-marca-logo {{
  width: 2.1rem; height: 2.1rem; border-radius: 0.5rem; flex: none;
  background: var(--acento); color: #fff;
  display: grid; place-items: center;
  font-weight: 700; font-size: 0.8rem; letter-spacing: 0.02em;
}}
.gr-marca-titulo {{ font-weight: 600; font-size: 0.92rem; color: var(--texto); line-height: 1.2; }}
.gr-marca-sub {{ font-size: 0.75rem; color: var(--texto-suave); line-height: 1.3; }}

.gr-grupo {{
  font-size: 0.72rem; font-weight: 500; color: var(--texto-tenue);
  padding: 0.9rem 0.5rem 0.35rem; border-top: 1px solid var(--borde);
}}

/* Menú de herramientas: el radio se dibuja como lista de navegación.
   Estructura de Streamlit 1.63: label[data-testid=stRadioOption] >
   div > div > [div del círculo] + [stMarkdownContainer]. */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
[data-testid="stSidebar"] [data-testid="stRadio"],
[data-testid="stSidebar"] [data-testid="stRadio"] > div,
[data-testid="stSidebar"] [data-testid="stRadioGroup"] {{ gap: 2px; width: 100%; max-width: none; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"] {{
  width: 100%; box-sizing: border-box; margin: 0; padding: 0.5rem 0.65rem; border-radius: 0.45rem;
  cursor: pointer; transition: background 120ms ease;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div > div:not([data-testid="stMarkdownContainer"]) {{
  display: none;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p {{
  font-size: 0.875rem; font-weight: 500; color: var(--texto-suave);
  display: flex; align-items: center; gap: 0.6rem; margin: 0;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p [role="img"] {{ font-size: 1.1rem; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {{ background: #EBEBED; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover p {{ color: var(--texto); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {{
  background: var(--tarjeta);
  box-shadow: inset 2px 0 0 var(--acento), 0 1px 2px rgba(9, 9, 11, 0.06);
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {{ color: var(--texto); }}

.gr-nota-lateral {{
  display: flex; gap: 0.55rem; align-items: flex-start;
  margin-top: 1.5rem; padding: 0.75rem; border-radius: var(--radio);
  border: 1px solid var(--borde); background: var(--tarjeta);
  font-size: 0.75rem; line-height: 1.45; color: var(--texto-suave);
}}
.gr-nota-lateral svg {{ flex: none; margin-top: 1px; }}

/* ---------- Encabezado de la herramienta ---------- */
.gr-migas {{ font-size: 0.8rem; color: var(--texto-tenue); margin-bottom: 0.6rem; }}
.gr-migas b {{ color: var(--texto-suave); font-weight: 500; }}
.gr-titulo {{
  font-size: 1.9rem; font-weight: 700; letter-spacing: -0.035em;
  line-height: 1.15; color: var(--texto); margin: 0 0 0.55rem;
}}
[data-testid="stMarkdownContainer"] p.gr-bajada {{ font-size: 0.93rem; line-height: 1.6; color: var(--texto-suave); margin: 0 0 0.9rem; max-width: 42rem; }}
.gr-badges {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.6rem; }}
.gr-badge {{
  display: inline-flex; align-items: center; gap: 0.35rem;
  padding: 0.15rem 0.55rem; border-radius: 999px;
  border: 1px solid var(--borde); background: transparent;
  font-size: 0.72rem; font-weight: 500; color: var(--texto-suave); white-space: nowrap;
}}
.gr-badge-solido {{ background: var(--muted); color: var(--texto); }}
.gr-punto {{ width: 0.5rem; height: 0.5rem; border-radius: 999px; display: inline-block;
  box-shadow: 0 0 0 1px rgba(9, 9, 11, 0.12); }}

/* ---------- Tarjetas (st.container(border=True)) ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] .gr-paso),
div[class*="st-key-tarjeta_"] {{
  background: var(--tarjeta);
  border-color: var(--borde) !important;
  border-radius: 0.75rem !important;
  box-shadow: 0 1px 2px rgba(9, 9, 11, 0.05);
}}
div[class*="st-key-tarjeta_"] {{ padding: 1.25rem 1.35rem 1.35rem !important; }}

.gr-paso {{ display: flex; gap: 0.75rem; align-items: flex-start; margin-bottom: 0.35rem; }}
.gr-paso-num {{
  flex: none; width: 1.6rem; height: 1.6rem; border-radius: 999px;
  border: 1px solid var(--borde); background: var(--muted);
  display: grid; place-items: center;
  font-size: 0.75rem; font-weight: 600; color: var(--texto);
}}
[data-testid="stMarkdownContainer"] p.gr-paso-titulo {{ font-size: 0.98rem; font-weight: 600; color: var(--texto); line-height: 1.6rem; margin: 0; }}
[data-testid="stMarkdownContainer"] p.gr-paso-ayuda {{ font-size: 0.8rem; color: var(--texto-suave); margin: 0.1rem 0 0; line-height: 1.45; }}

/* ---------- Carga de archivos ---------- */
[data-testid="stFileUploaderDropzone"] {{
  background: var(--fondo);
  border: 1px dashed var(--borde-fuerte);
  border-radius: var(--radio);
  padding: 1.15rem 1.25rem;
  transition: border-color 140ms ease, background 140ms ease;
}}
[data-testid="stFileUploaderDropzone"]:hover {{ border-color: var(--anillo); background: var(--muted); }}
[data-testid="stFileUploaderDropzone"] button {{
  background: var(--muted); border: 1px solid var(--borde); color: var(--texto);
  border-radius: 0.45rem; font-weight: 500;
}}

/* ---------- Resumen de lo leído ---------- */
.gr-lectura {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.45rem 0.9rem;
  margin-top: 0.85rem; padding: 0.75rem 0.9rem;
  border: 1px solid var(--borde); border-radius: var(--radio); background: var(--fondo);
}}
.gr-lectura-cifra {{ font-size: 0.85rem; color: var(--texto-suave); }}
.gr-lectura-cifra b {{ font-size: 1.05rem; color: var(--texto); font-weight: 600; margin-right: 0.15rem; }}
.gr-lectura .gr-badges {{ margin: 0; }}

/* ---------- Campos ---------- */
.stTextInput input, .stTextArea textarea, .stDateInput input {{ font-size: 0.9rem; }}
[data-testid="stWidgetLabel"] p {{ font-size: 0.82rem; font-weight: 500; color: var(--texto-suave); }}

/* ---------- Botón principal ---------- */
.stButton > button[kind="primary"] {{
  background: var(--acento); border: 1px solid var(--acento); color: #fff;
  font-weight: 600; font-size: 0.9rem; height: 2.65rem;
  transition: background 120ms ease, border-color 120ms ease;
}}
.stButton > button[kind="primary"]:hover:not(:disabled) {{
  background: var(--acento-hover); border-color: var(--acento-hover); color: #fff;
}}
.stButton > button[kind="primary"]:disabled {{
  background: var(--muted); border-color: var(--borde); color: var(--texto-tenue); opacity: 1;
}}

/* ---------- Lista de descargas ---------- */
div[class*="st-key-archivo_"] {{
  border: 1px solid var(--borde); border-radius: var(--radio);
  background: var(--fondo); padding: 0.6rem 0.65rem 0.6rem 0.75rem;
  transition: border-color 120ms ease;
}}
div[class*="st-key-archivo_"]:hover {{ border-color: var(--borde-fuerte); }}
.gr-archivo {{ display: flex; align-items: center; gap: 0.8rem; min-width: 0; }}
.gr-archivo-icono {{
  flex: none; width: 2.35rem; height: 2.35rem; border-radius: 0.5rem;
  display: grid; place-items: center;
  font-size: 0.64rem; font-weight: 700; letter-spacing: 0.04em;
}}
.gr-archivo-texto {{ min-width: 0; }}
.gr-archivo-nombre {{
  font-family: 'Geist Mono', ui-monospace, monospace; font-size: 0.82rem; color: var(--texto);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.gr-archivo-meta {{ font-size: 0.74rem; color: var(--texto-tenue); margin-top: 0.1rem; }}
.stDownloadButton > button {{
  background: var(--muted); border: 1px solid var(--borde); color: var(--texto);
  font-weight: 500; font-size: 0.84rem; height: 2.3rem;
}}
.stDownloadButton > button:hover {{ background: var(--borde); border-color: var(--borde-fuerte); color: var(--texto); }}

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
  .gr-titulo {{ font-size: 1.55rem; }}
  .block-container {{ padding-top: 1.5rem; }}
  div[class*="st-key-tarjeta_"] {{ padding: 1rem !important; }}
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
def marca(titulo: str, subtitulo: str, logo: str = "RH"):
    _html(
        f'<div class="gr-marca"><div class="gr-marca-logo">{logo}</div>'
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


def encabezado(nombre: str, descripcion: str, etiquetas=()):
    """Migas, título, descripción y badges de la herramienta elegida."""
    _html(
        f'<div class="gr-migas">Herramientas &nbsp;/&nbsp; <b>{html.escape(nombre)}</b></div>'
        f'<div class="gr-titulo" role="heading" aria-level="1">{html.escape(nombre)}</div>'
        f'<p class="gr-bajada">{html.escape(descripcion)}</p>'
        f'<div class="gr-badges">{badges(etiquetas)}</div>'
    )


def paso(numero: int, titulo: str, ayuda: str = ""):
    """Título numerado al inicio de cada tarjeta."""
    texto_ayuda = f'<p class="gr-paso-ayuda">{html.escape(ayuda)}</p>' if ayuda else ""
    _html(
        f'<div class="gr-paso"><div class="gr-paso-num">{numero}</div>'
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
        f'<div class="gr-archivo-icono" style="color:{color};background:{color}1F;'
        f'border:1px solid {color}40">{html.escape(extension.upper())}</div>'
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
