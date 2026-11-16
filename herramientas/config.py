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
    # Lo que los datos no traen: el contexto que solo conoce quien hace el
    # reporte ("septiembre tuvo la feria", "falta la bitácora de la semana 4").
    # Se imprime en la portada, antes de las acciones. Vacío = no se imprime.
    mensaje: str = ""
    # Meta de conversión (% de solicitudes financiadas). None = sin meta.
    meta_conversion: float | None = None

    @classmethod
    def desde_opciones(cls, nombre_pdv=None, nombre_analista=None,
                       mensaje_principal=None, meta_conversion=None, **_otras):
        """Lo que escribió el usuario en la app; vacío = valor por defecto."""
        try:
            meta = float(meta_conversion) if meta_conversion not in (None, "", 0) else None
        except (TypeError, ValueError):
            meta = None
        return cls(
            pdv=(nombre_pdv or "").strip() or PDV_DEFECTO,
            analista=(nombre_analista or "").strip() or ANALISTA_DEFECTO,
            mensaje=(mensaje_principal or "").strip(),
            meta_conversion=meta if meta and meta > 0 else None,
        )
