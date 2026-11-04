"""Datos que aparecen en el encabezado y el pie de los reportes.

Antes cada reporte tenía sus propias constantes de módulo
(SUBTITULO_EMPRESA, NOMBRE_ANALISTA), repetidas en cinco archivos, y cada
adaptador las sobrescribía antes de generar. Como Streamlit atiende a todos
los usuarios en un solo proceso, esas constantes eran compartidas: el PDF de
una persona podía salir con el PDV de otra. Ahora los datos viajan como
parámetro (DatosReporte) y los valores por defecto viven solo aquí.
"""

from dataclasses import dataclass

NOMBRE_EMPRESA = "AUTOEXPRESS INBURSA"
PDV_DEFECTO = "MG Colima PYD"
ANALISTA_DEFECTO = "Christian Ramos"


@dataclass(frozen=True)
class DatosReporte:
    """PDV, implant y empresa de UNA corrida."""

    pdv: str = PDV_DEFECTO
    analista: str = ANALISTA_DEFECTO
    empresa: str = NOMBRE_EMPRESA

    @classmethod
    def desde_opciones(cls, nombre_pdv=None, nombre_analista=None):
        """Lo que escribió el usuario en la app; vacío = valor por defecto."""
        return cls(
            pdv=(nombre_pdv or "").strip() or PDV_DEFECTO,
            analista=(nombre_analista or "").strip() or ANALISTA_DEFECTO,
        )
