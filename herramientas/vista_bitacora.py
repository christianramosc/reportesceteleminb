"""Qué trae la bitácora, antes de generar el reporte.

La app lo usa en la vista previa (al subir el Excel): cuántas filas hay, qué
estatus se detectaron, qué columnas faltan —y qué parte del reporte se pierde
por cada una— y qué vendedores aparecen. No depende de Streamlit, así que se
puede probar sola.
"""

from . import estatus as _est
from .conclusiones import SIN_VENDEDOR
from .reporte_base import COLUMNAS_ESPERADAS, limpiar_texto

# Qué deja de salir en los reportes cuando falta cada columna. Las columnas
# esperadas que no están aquí (teléfono, correo, marca...) no cambian
# ninguna cifra: se listan aparte, sin alarmar.
CONSECUENCIA = {
    "Nombre del Vendedor": "no habrá análisis por vendedor (el Resumen por "
                           "Vendedor no se puede generar)",
    "Monto Total a Financiar": "no habrá montos financiados ni ticket promedio",
    "¿Tiene GAP?": "no habrá sección de seguro GAP",
    "Monto GAP": "no se reportará el monto colocado en GAP",
    "Vehículo": "no habrá modelos más solicitados",
    "Folio CCK": "no se podrán detectar folios repetidos entre meses",
    "Precio Venta (c/IVA)": "no se calculará el % de enganche",
    "Enganche": "no se calculará el % de enganche",
    "Plazo (meses)": "no saldrá el plazo promedio",
    "Tasa Interés Anual": "no saldrá la tasa promedio",
    "Fecha de Nacimiento": "no saldrá la edad promedio de los clientes",
}

_COLUMNAS_ESTATUS = ("STATUS", "ESTATUS")


def revisar(df):
    """Resumen de una bitácora recién leída (sin limpiar).

    Devuelve un dict:
      filas        número de renglones
      conteo       {categoría: cuántas} o {} si no hay columna de estatus
      faltantes    [(columna, consecuencia)] de las que SÍ cambian el reporte
      otras        [columna] que faltan pero no cambian ninguna cifra
      vendedores   nombres, escritos igual que en los reportes
    """
    columnas = {str(c).strip(): c for c in df.columns}

    conteo = {}
    col_estatus = next((original for limpio, original in columnas.items()
                        if limpio.upper() in _COLUMNAS_ESTATUS), None)
    if col_estatus is not None:
        for valor in df[col_estatus]:
            clave = _est.clasificar_status(valor)
            conteo[clave] = conteo.get(clave, 0) + 1

    ausentes = [c for c in COLUMNAS_ESPERADAS
                if c not in columnas and c.upper() not in _COLUMNAS_ESTATUS]
    faltantes = [(c, CONSECUENCIA[c]) for c in ausentes if c in CONSECUENCIA]
    otras = [c for c in ausentes if c not in CONSECUENCIA]

    vendedores = []
    if "Nombre del Vendedor" in columnas:
        nombres = limpiar_texto(df[columnas["Nombre del Vendedor"]], modo="titulo").dropna()
        vendedores = sorted(v for v in nombres.unique() if v != SIN_VENDEDOR)

    return {"filas": len(df), "conteo": conteo, "faltantes": faltantes,
            "otras": otras, "vendedores": vendedores}
