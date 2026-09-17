# -*- coding: utf-8 -*-
"""Estilos visuales de la app.

Está aparte de streamlit_app.py a propósito: el CSS es largo y no tiene
nada que ver con la lógica de generar reportes. Si mañana cambia el look,
se toca este archivo y nada más.

Dirección de diseño
-------------------
La app es una herramienta de trabajo que alguien abre unos minutos al mes
para convertir un montón de PDFs en un Excel. Lo que tiene que comunicar
es precisión y estado: qué subí, qué está pasando, dónde quedó mi archivo.
De ahí las decisiones:

- Paleta de tinta sobre papel frío (no crema): el fondo es un gris azulado
  muy claro y el texto un azul de tinta profundo. Lee como documento
  financiero bien impreso, que es literalmente el material de origen.
- Un solo acento rojo (#C8102E, el rojo de MG) y reservado para UNA cosa:
  el botón que genera. Todo lo demás se mantiene callado para que la
  acción principal sea obvia sin tener que buscarla.
- Tipografía Archivo para títulos (grotesca de rasgos rectos, con aire de
  señalética automotriz) e Inter para el cuerpo.
- Pestañas como control segmentado en vez de subrayado: se ven como un
  selector de modo, que es lo que realmente son.
"""

import re

import streamlit as st

# --- Tokens --------------------------------------------------------------
PAPEL       = "#F4F6F9"   # fondo de la página
SUPERFICIE  = "#FFFFFF"   # tarjetas y campos
TINTA       = "#132038"   # texto principal
TINTA_SUAVE = "#5D6E85"   # texto secundario
BORDE       = "#DDE3EC"
ACENTO      = "#C8102E"   # rojo MG — solo para la acción principal
ACENTO_OSC  = "#A00D25"
EXITO       = "#0F7A55"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=Inter:wght@400;500;600&display=swap');

:root {{
  --papel: {PAPEL};
  --superficie: {SUPERFICIE};
  --tinta: {TINTA};
  --tinta-suave: {TINTA_SUAVE};
  --borde: {BORDE};
  --acento: {ACENTO};
  --acento-osc: {ACENTO_OSC};
  --exito: {EXITO};
}}

/* ---------- Base ---------- */
.stApp {{
  background: var(--papel);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: var(--tinta);
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.6rem; max-width: 52rem; }}

h1, h2, h3, h4 {{
  font-family: 'Archivo', 'Inter', sans-serif;
  color: var(--tinta);
  letter-spacing: -0.02em;
}}

/* ---------- Encabezado ---------- */
.gr-encabezado {{ margin-bottom: 2rem; }}
.gr-titulo {{
  font-family: 'Archivo', sans-serif;
  font-weight: 700;
  font-size: 2.5rem;
  line-height: 1.1;
  letter-spacing: -0.035em;
  color: var(--tinta);
  margin: 0;
}}
.gr-regla {{
  width: 3.25rem;
  height: 4px;
  background: var(--acento);
  border-radius: 2px;
  margin: 0.9rem 0 0.85rem;
}}
.gr-bajada {{
  font-size: 0.95rem;
  color: var(--tinta-suave);
  margin: 0;
  max-width: 34rem;
  line-height: 1.55;
}}

/* ---------- Pestañas como control segmentado ----------
   Streamlit 1.63 renderiza las pestañas con react-aria
   ([data-testid="stTab"], [role="tablist"]). Se dejan también los
   selectores viejos de baseweb por si la app corre en una versión
   anterior: los que no existen simplemente no aplican. */
[data-testid="stTabs"] [role="tablist"],
.stTabs [data-baseweb="tab-list"] {{
  gap: 4px;
  background: #E7ECF3;
  padding: 4px;
  border-radius: 12px;
  border: none;
  display: flex;
  flex-wrap: wrap;
}}
[data-testid="stTab"],
.stTabs [data-baseweb="tab-list"] button {{
  background: transparent;
  border: none;
  border-radius: 9px;
  padding: 0.5rem 0.95rem;
  color: var(--tinta-suave);
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease;
}}
[data-testid="stTab"] p {{
  font-family: 'Inter', sans-serif;
  font-size: 0.86rem;
  font-weight: 500;
  margin: 0;
  color: inherit;
}}
[data-testid="stTab"]:hover {{ color: var(--tinta); }}
[data-testid="stTab"][aria-selected="true"],
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
  background: var(--superficie);
  color: var(--tinta);
  box-shadow: 0 1px 2px rgba(19, 32, 56, 0.10);
}}
[data-testid="stTab"][aria-selected="true"] p {{ font-weight: 600; }}

/* El subrayado animado sobra en un control segmentado */
.react-aria-SelectionIndicator,
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

[role="tabpanel"],
.stTabs [data-baseweb="tab-panel"] {{ padding-top: 1.6rem; }}

/* ---------- Zona de carga ---------- */
[data-testid="stFileUploaderDropzone"] {{
  background: var(--superficie);
  border: 1.5px dashed var(--borde);
  border-radius: 12px;
  padding: 1.4rem;
  transition: border-color 140ms ease, background 140ms ease;
}}
[data-testid="stFileUploaderDropzone"]:hover {{
  border-color: #B9C4D4;
  background: #FCFDFE;
}}
[data-testid="stFileUploaderDropzone"] button {{
  background: var(--superficie);
  color: var(--tinta);
  border: 1px solid var(--borde);
  border-radius: 8px;
  font-weight: 500;
}}

/* ---------- Campos ---------- */
.stTextInput input, .stTextArea textarea, .stDateInput input {{
  background: var(--superficie);
  border: 1px solid var(--borde);
  border-radius: 9px;
  color: var(--tinta);
  font-family: 'Inter', sans-serif;
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
  border-color: var(--tinta-suave);
  box-shadow: none;
}}
label, .stCheckbox label p {{
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  color: var(--tinta-suave) !important;
}}

/* ---------- Botón principal: el único elemento rojo ---------- */
.stButton > button[kind="primary"] {{
  background: var(--acento);
  border: none;
  border-radius: 9px;
  color: #fff;
  font-family: 'Inter', sans-serif;
  font-weight: 600;
  font-size: 0.92rem;
  padding: 0.6rem 1.8rem;
  box-shadow: 0 1px 2px rgba(200, 16, 46, 0.25);
  transition: background 120ms ease;
}}
.stButton > button[kind="primary"]:hover:not(:disabled) {{
  background: var(--acento-osc);
  color: #fff;
}}
.stButton > button[kind="primary"]:disabled {{
  background: #C9D2DE;
  color: #8A98AB;
  box-shadow: none;
}}

/* ---------- Botones de descarga ---------- */
.stDownloadButton > button {{
  background: var(--superficie);
  border: 1px solid var(--borde);
  border-radius: 10px;
  color: var(--tinta);
  font-family: 'Inter', sans-serif;
  font-weight: 500;
  font-size: 0.88rem;
  padding: 0.7rem 1rem;
  transition: border-color 120ms ease, box-shadow 120ms ease;
}}
.stDownloadButton > button:hover {{
  border-color: var(--tinta-suave);
  color: var(--tinta);
  box-shadow: 0 2px 6px rgba(19, 32, 56, 0.08);
}}

/* ---------- Avisos ---------- */
[data-testid="stAlert"] {{
  border-radius: 10px;
  border: 1px solid var(--borde);
  font-size: 0.89rem;
}}

/* ---------- Expander ---------- */
[data-testid="stExpander"] details {{
  background: var(--superficie);
  border: 1px solid var(--borde);
  border-radius: 10px;
}}
[data-testid="stExpander"] summary {{
  font-size: 0.86rem;
  font-weight: 500;
  color: var(--tinta-suave);
}}

/* ---------- Bloque de resultado ---------- */
.gr-resultado {{
  background: var(--superficie);
  border: 1px solid var(--borde);
  border-left: 3px solid var(--exito);
  border-radius: 10px;
  padding: 0.85rem 1.1rem;
  margin-bottom: 0.9rem;
}}
.gr-resultado-titulo {{
  font-family: 'Archivo', sans-serif;
  font-weight: 600;
  font-size: 0.97rem;
  color: var(--tinta);
  margin: 0 0 0.15rem;
}}
.gr-resultado-nota {{
  font-size: 0.83rem;
  color: var(--tinta-suave);
  margin: 0;
}}

/* ---------- Pie ---------- */
.gr-pie {{
  margin-top: 3rem;
  padding-top: 1.1rem;
  border-top: 1px solid var(--borde);
  font-size: 0.78rem;
  color: #8A98AB;
}}

/* Accesibilidad */
*:focus-visible {{ outline: 2px solid var(--tinta); outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; animation: none !important; }}
}}
@media (max-width: 640px) {{
  .gr-titulo {{ font-size: 2rem; }}
  .block-container {{ padding-top: 1.6rem; }}
}}
</style>
"""


def aplicar_estilos():
    """Inyecta el CSS. Se llama una sola vez, justo después de
    st.set_page_config()."""
    st.markdown(_CSS, unsafe_allow_html=True)


def encabezado(titulo: str, bajada: str):
    """Dibuja el encabezado de la app."""
    st.markdown(
        f'<div class="gr-encabezado">'
        f'<h1 class="gr-titulo">{titulo}</h1>'
        f'<div class="gr-regla"></div>'
        f'<p class="gr-bajada">{bajada}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def bloque_resultado(titulo: str, nota: str):
    """Panel de confirmación arriba de los botones de descarga."""
    st.markdown(
        f'<div class="gr-resultado">'
        f'<p class="gr-resultado-titulo">{titulo}</p>'
        f'<p class="gr-resultado-nota">{nota}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def pie(texto: str):
    st.markdown(f'<div class="gr-pie">{texto}</div>', unsafe_allow_html=True)


# Los nombres de las herramientas traen un emoji al inicio ("📁 Relación de
# Clientes"). En un control segmentado se ven ruidosos y desalinean las
# pestañas, así que se quitan solo para mostrar; el registro no se toca.
_EMOJI_INICIAL = re.compile(r"^[^\w(]+", flags=re.UNICODE)


def nombre_limpio(nombre: str) -> str:
    return _EMOJI_INICIAL.sub("", nombre).strip()
