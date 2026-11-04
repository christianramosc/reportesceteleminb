"""
Genera la GUÍA DE USO de Relación de clientes (ZIP → Excel): un PDF de dos
páginas (mapa mental + ejemplos) y una imagen de la página 1 que la app
muestra en el desplegable "¿Cómo armo el ZIP?".

La guía se escribe en guias/guia_zip.html. Para cambiar un texto, se edita
ese archivo y se vuelve a correr esto desde la raíz del repo:

    python -m scripts.guia_zip

No es parte de la app (Streamlit Cloud solo sirve los archivos ya
generados, que se suben al repo): se corre a mano cuando cambia la guía.
Necesita Playwright con Chromium, que no está en requirements.txt:

    pip install playwright && playwright install chromium

Si se agrega un estatus al catálogo (herramientas/estatus.py), la prueba
tests/test_guia_zip.py falla hasta que se agregue también a la lista
"Los 14 nombres de carpeta" del HTML: así la guía no se queda atrás.
"""

import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "guias")
HTML = os.path.join(CARPETA, "guia_zip.html")
PDF = os.path.join(CARPETA, "Guia_ZIP_Relacion_de_clientes.pdf")
IMAGEN = os.path.join(CARPETA, "guia_zip_mapa.png")


def generar(html=HTML, pdf=PDF, imagen=IMAGEN):
    """Dibuja el HTML en Chromium: el PDF a tamaño carta horizontal y la
    página 1 como imagen al doble de resolución, para que se lea al
    ampliarla en la app."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1056, "height": 816}, device_scale_factor=2)
        pagina.goto("file://" + os.path.abspath(html))
        pagina.wait_for_timeout(800)          # que carguen las fuentes
        pagina.pdf(path=pdf, width="11in", height="8.5in",
                   print_background=True, prefer_css_page_size=True)
        pagina.locator("section.pagina").first.screenshot(path=imagen)
        navegador.close()
    return pdf, imagen


if __name__ == "__main__":
    for ruta in generar():
        print("✔", os.path.relpath(ruta, RAIZ))
