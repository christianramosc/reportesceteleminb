"""Definición del objeto Herramienta que usa el registro central (__init__.py).

Todo lo que la app necesita saber de una herramienta (icono, qué campos
pedir, si muestra vista previa) se declara aquí. Antes streamlit_app.py
decidía eso con listas de ids escritas a mano ("si es avance_preliminar o
comparativo_mensual, pide PDV..."), así que agregar una herramienta
obligaba a tocar la app en varios lugares.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class Herramienta:
    id: str                      # identificador único, usado como key de Streamlit
    nombre: str                  # título de la página
    descripcion: str             # texto explicativo para el usuario final
    multiple_archivos: bool      # True si acepta varios archivos a la vez
    tipos_permitidos: List[str]  # extensiones que acepta el file_uploader, ej. ["xlsx"]
    # ejecutar(rutas_archivos, carpeta_salida="salida", **opciones) -> lista de rutas de salida
    ejecutar: Callable[..., List[str]]
    ayuda_archivo: Optional[str] = None  # texto de ayuda bajo el uploader (opcional)
    # Opcional: si ejecutar() regresa {"archivos": [...], "resumen": obj},
    # la app guarda obj y llama mostrar_resumen(obj) para dibujar el
    # resultado EN LA PÁGINA, antes de las descargas (ej. Validar CSF).
    mostrar_resumen: Optional[Callable[..., None]] = None

    # --- Menú lateral ---------------------------------------------------
    icono: str = ":material/description:"   # Material Symbols de Streamlit
    nombre_corto: Optional[str] = None      # en el menú; por defecto, el nombre sin emoji

    # --- Qué muestra y qué pide la página ---------------------------------
    # Vista previa de la bitácora (filas y estatus) al subir el Excel.
    vista_previa_bitacora: bool = False
    # Aviso si se suben menos archivos de los necesarios (el comparativo, 2).
    minimo_archivos: int = 1
    # Campos del paso "Datos del reporte". Cada uno llega a ejecutar() como
    # opción con el mismo nombre que usa hoy la herramienta:
    pide_pdv_e_implant: bool = False   # nombre_pdv, nombre_analista
    pide_fecha_corte: bool = False     # fecha_corte ("DD/MM/AAAA")
    pide_vendedores: bool = False      # vendedores_incluir (lista)
    pide_etiquetas_mes: bool = False   # nombres_meses (lista)

    # --- Segundo campo de archivos (opcional) -----------------------------
    # Bitácoras de meses ANTERIORES, para comparar contra ellas:
    #   None     -> la herramienta no las pide
    #   "uno"    -> un solo archivo (el mes anterior)
    #   "varios" -> varios meses
    # Llegan a ejecutar() como rutas_anteriores (lista de rutas). Siempre
    # son opcionales: sin ellas el reporte sale igual que antes.
    meses_anteriores: Optional[str] = None
    ayuda_meses_anteriores: str = ""

    # --- Guía de uso (opcional) -------------------------------------------
    # Rutas desde la raíz del repo. Si hay guía, la página muestra un
    # desplegable con la imagen (guia_vista) y el botón para bajar el PDF.
    guia: Optional[str] = None          # PDF, ej. "guias/Guia_ZIP_Relacion_de_clientes.pdf"
    guia_vista: Optional[str] = None    # imagen de la primera página
    guia_titulo: str = "¿Cómo se usa?"

    @property
    def tiene_opciones(self):
        return (self.pide_pdv_e_implant or self.pide_fecha_corte
                or self.pide_vendedores or self.pide_etiquetas_mes)
