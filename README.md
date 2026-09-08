# Reportes — Bitácora MG Colima

App de Streamlit que junta, detrás de botones simples de "sube el archivo
y descarga el resultado", los scripts que ya usas en Colab:

| Pestaña | Qué hace | Entrada | Salida |
|---|---|---|---|
| 📁 Relación de Clientes | `bitacora_zip.py` (adaptado de `Relacion_de_clientes_ZIP_DEL_MES`) | 1 ZIP del mes | 1 Excel (bitácora) |
| 📈 Avance Preliminar Mensual | `avance_preliminar_original.py` (sin cambios) | 1 Excel | 1 PDF + 1 Word |
| 📊 Comparativo Mensual | `comparativo_mensual_original.py` (sin cambios) | 2+ Excel | 1 PDF + 1 Word |

Tus compañeros solo necesitan el link de la app — no necesitan Colab, ni
cuenta de Google, ni saber qué es una celda de código.

### Nombre de PDV y analista (por PDV)

Las pestañas de Avance Preliminar y Comparativo Mensual ahora traen dos
campos arriba del uploader: **Nombre del PDV** y **Analista**. Vienen
prellenados con los valores originales del script (`MG Colima PYD` /
`Christian Ramos`), pero cada quien los puede cambiar antes de generar su
reporte — así la misma app le sirve a cualquier PDV, no solo a Colima.
Internamente esto ajusta las constantes `SUBTITULO_EMPRESA` /
`NOMBRE_ANALISTA` de los scripts originales antes de generar, sin tener
que tocar esos archivos.

### Versión Word (editable)

Cada vez que generas el Avance Preliminar o el Comparativo, además del
PDF se genera un `.docx` con el mismo contenido (KPIs, tablas, gráficas
e insights) para que cualquiera lo pueda editar libremente antes de
compartirlo — cambiar texto, quitar una tabla, agregar un comentario,
etc. Lo arma `herramientas/docx_reportes.py`, reutilizando las mismas
tablas/gráficas/insights ya calculados por los scripts originales (no
son datos recalculados aparte). La única sección que no es una copia
literal del PDF es "Conclusiones" del Avance Preliminar: ahí se redactó
de nuevo con el mismo criterio (top vendedor por volumen, por
financiado, por GAP) porque en el script original esas frases están
armadas dentro de la función que arma el PDF, no en una función aparte
reutilizable. El resto si es exactamente el mismo contenido que el PDF.

## Cómo desplegarla (gratis, Streamlit Community Cloud)

1. Crea un repositorio en GitHub y sube TODO el contenido de esta carpeta
   (incluyendo `requirements.txt` y `packages.txt` — son necesarios).
2. Entra a [share.streamlit.io](https://share.streamlit.io), conecta tu
   cuenta de GitHub y elige "New app".
3. Selecciona el repo, la rama, y como "Main file path" pon
   `streamlit_app.py`.
4. Deploy. En 1-2 minutos te da un link tipo
   `https://tu-app.streamlit.app` — ese es el que compartes con tus
   compañeros.

Cada vez que subas cambios al repo de GitHub, la app se actualiza sola.

(Alternativa sin GitHub: Hugging Face Spaces con SDK "Streamlit" — el
mismo `requirements.txt` funciona igual; `packages.txt` ahí se llama
`packages.txt` también.)

## Cómo agregar otro script más adelante

**Sí se puede, y no hay que tocar `streamlit_app.py`.** La app arma una
pestaña automática por cada herramienta registrada en
`herramientas/__init__.py`. Pasos:

1. Asegúrate de que tu script tenga una función `main(...)` como punto de
   entrada (que reciba la ruta del archivo como parámetro, no que la pida
   con `input()` o `files.upload()`) y un guard al final:
   ```python
   if __name__ == "__main__":
       main()
   ```
   Cópialo tal cual a la carpeta `herramientas/` (mismo patrón que
   `avance_preliminar_original.py` y `comparativo_mensual_original.py` —
   a esos dos no les tuvimos que cambiar ni una línea).

2. Crea `herramientas/herramienta_tu_script.py`:
   ```python
   from . import tu_script_original as _tu_script
   from .registro import Herramienta

   def ejecutar(rutas_archivos, carpeta_salida="salida", **opciones):
       _tu_script.main(ruta_local=rutas_archivos[0])
       # ... localizar y mover el archivo generado a carpeta_salida ...
       return [ruta_del_resultado]

   HERRAMIENTA = Herramienta(
       id="tu_script",
       nombre="🆕 Nombre para el botón",
       descripcion="Qué hace, en una o dos líneas.",
       multiple_archivos=False,
       tipos_permitidos=["xlsx"],
       ejecutar=ejecutar,
   )
   ```
   (usa `herramientas/herramienta_avance_preliminar.py` como plantilla —
   es la más simple de las tres)

3. En `herramientas/__init__.py`, impórtalo y agrégalo a la lista
   `REGISTRO`.

Con eso, `streamlit_app.py` ya le arma solo la pestaña, el botón de subir
archivo y el botón de descarga.

## Correrla en tu computadora (para probar antes de desplegar)

```bash
pip install -r requirements.txt
# (opcional) el binario pdftotext acelera la lectura de PDFs; si no lo tienes
# la app usa pdfplumber automáticamente:
#   Windows: https://github.com/oschwartz10612/poppler-windows/releases
#   Mac:     brew install poppler
#   Linux:   sudo apt install poppler-utils
streamlit run streamlit_app.py
```

## Pruebas

Antes de desplegar un cambio, corre las pruebas desde la raíz del proyecto:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

Tardan ~35 segundos y cubren tres frentes:

- **`test_estatus.py`** — el catálogo de estatus: que cada sinónimo caiga en
  su categoría, que "NO FINANCIADOS" nunca se confunda con FINANCIADO, y que
  al agregar un estatus nuevo no repitas un sinónimo o un color de otro.
- **`test_calculos.py`** — que los conteos cuadren con el total y que
  "en trámite" no incluya cierres definitivos.
- **`test_reportes.py`** — genera los tres reportes de verdad y verifica que
  el PDF traiga gráficas. Incluye `test_dos_corridas_seguidas_en_el_mismo_proceso`,
  que ejecuta cada reporte **dos veces seguidas**, como hace Streamlit: es la
  prueba que detecta los errores que solo aparecen a partir de la segunda
  generación y que probar una sola vez deja pasar.

Las pruebas no usan bitácoras reales: arman un Excel sintético con las mismas
columnas, así que se pueden correr en cualquier máquina sin datos de clientes.

## Notas

- Los tres scripts fueron probados de extremo a extremo (Excel/PDF de
  prueba) antes de entregarte este proyecto.
- La herramienta "Relación de Clientes" lee PDFs con `pdftotext` (poppler)
  si el binario está instalado, y si no con `pdfplumber` (Python puro, va en
  requirements.txt). Por eso el proyecto YA NO lleva `packages.txt`: Streamlit
  Community Cloud aborta el despliegue completo cuando intenta correr
  apt-get, porque el repositorio bullseye-security de Debian está vencido.
  No vuelvas a agregar packages.txt salvo que Streamlit actualice su imagen.
- Es una app pensada para uso interno de pocas personas a la vez; si dos
  personas generan un PDF en el mismo minuto exacto podría haber una
  colisión de nombre de archivo. Para el volumen de tu equipo no debería
  ser un problema, pero es bueno saberlo.
- Por el mismo motivo, si dos personas de PDVs distintos generan un
  reporte exactamente al mismo tiempo, el nombre de PDV/analista de una
  podría "ganarle" a la otra por una fracción de segundo (es una variable
  compartida del proceso, no algo aislado por usuario). Para el uso
  típico —una persona generando un reporte a la vez— no pasa nada.
# reportesceteleminb
