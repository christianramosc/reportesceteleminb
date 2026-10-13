# -*- coding: utf-8 -*-
"""Exporta el modelo de datos (modelo_datos.py) a un Excel listo para
Power BI o Power Pivot.

Cada tabla del modelo va en su propia hoja como TABLA DE EXCEL con nombre
(hechos_solicitud, dim_mes...). Power BI las reconoce por ese nombre al
usar "Obtener datos > Excel", así que basta con marcarlas y crear las
relaciones que vienen en la hoja "Relaciones" (o dejar que Power BI las
detecte: las columnas se llaman igual en ambos lados).

Además del modelo, el libro trae:
  - Léeme        qué hay en el archivo, el diagrama y cómo usarlo.
  - Cuadre       conteos por mes con fórmulas vivas sobre las tablas, para
                 comprobar que cuadran con los reportes mensuales.
  - Relaciones   las llaves entre tablas.
  - Diccionario  qué significa cada columna.
  - Medidas DAX  medidas sugeridas para empezar el tablero.
"""

import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

try:
    from . import modelo_datos as md
except ImportError:
    import modelo_datos as md

FUENTE = "Arial"
AZUL = "191970"          # azul Inbursa
GRIS_TEXTO = "4B5563"
GRIS_BORDE = "D9DDE3"

FMT_MONEDA = '"$"#,##0.00'
FMT_PCT = "0.0%"
FMT_PCT_TASA = "0.00%"
FMT_ENTERO = "0"
FMT_FECHA = "dd/mm/yyyy"

COLS_MONEDA = set(md.COLUMNAS_MONEDA.values())
COLS_PCT = {"pct_enganche": FMT_PCT, "tasa_anual": FMT_PCT_TASA}

ORDEN_HOJAS = ["hechos_solicitud", "hechos_estatus_mes", "dim_mes", "dim_vendedor",
               "dim_vehiculo", "dim_estatus", "dim_cliente", "calidad_datos"]

MEDIDAS_DAX = [
    ("Solicitudes", "DISTINCTCOUNT ( hechos_solicitud[folio] )",
     "Solicitudes únicas del periodo (cada folio una vez)."),
    ("Financiadas", "SUM ( hechos_solicitud[financiado] )",
     "Solicitudes cuyo último estatus es FINANCIADO."),
    ("Conversión", "DIVIDE ( [Financiadas], [Solicitudes] )",
     "Financiadas / solicitudes. Formato porcentaje."),
    ("Monto financiado", "CALCULATE ( SUM ( hechos_solicitud[monto_financiar] ), hechos_solicitud[financiado] = 1 )",
     "Monto de las solicitudes financiadas."),
    ("Ticket promedio", "DIVIDE ( [Monto financiado], [Financiadas] )",
     "Monto promedio por crédito financiado."),
    ("% con GAP", "AVERAGE ( hechos_solicitud[tiene_gap] )",
     "Proporción de solicitudes con seguro GAP."),
    ("% con GAP en financiadas", "CALCULATE ( AVERAGE ( hechos_solicitud[tiene_gap] ), hechos_solicitud[financiado] = 1 )",
     "GAP colocado en lo que sí se dispersó."),
    ("Enganche promedio", "AVERAGE ( hechos_solicitud[pct_enganche] )",
     "Porcentaje de enganche promedio."),
    ("Rechazo", "DIVIDE ( SUM ( hechos_solicitud[rechazado] ), [Solicitudes] )",
     "Proporción de solicitudes rechazadas."),
    ("Solicitudes en la foto", "COUNTROWS ( hechos_estatus_mes )",
     "Renglones de la bitácora del mes; cuadra con el reporte mensual. Úsala con dim_mes."),
    ("Financiadas en la foto", "CALCULATE ( COUNTROWS ( hechos_estatus_mes ), hechos_estatus_mes[clave_estatus] = \"FINANCIADO\" )",
     "Financiadas tal como las reporta cada bitácora mensual."),
    ("Financiadas por mes de dispersión",
     "CALCULATE ( [Financiadas], USERELATIONSHIP ( hechos_solicitud[id_mes_ultimo], dim_mes[id_mes] ) )",
     "Usa la relación inactiva: cuenta cada financiada en el mes de su último estatus, no en el de captura."),
]


# =======================================================================
# Diagrama del modelo
# =======================================================================
_CAMPOS_DIAGRAMA = {
    "hechos_solicitud": ["PK folio", "FK id_mes_captura  ·  id_mes_ultimo", "FK id_vendedor",
                         "FK id_vehiculo", "FK estatus_final", "FK id_cliente",
                         "financiado, monto_financiar,", "pct_enganche, plazo, tasa, GAP..."],
    "hechos_estatus_mes": ["PK id_mes + folio  (FK a dim_mes)", "FK clave_estatus", "FK id_vendedor",
                           "FK id_vehiculo", "estatus_anterior, cambio_estatus"],
    "dim_mes": ["PK id_mes", "mes, anio, trimestre"],
    "dim_vendedor": ["PK id_vendedor", "vendedor, es_persona"],
    "dim_vehiculo": ["PK id_vehiculo", "version, linea,", "transmision, hibrido"],
    "dim_estatus": ["PK clave_estatus", "estatus, grupo, color"],
    "dim_cliente": ["PK id_cliente (seudónimo)", "tipo_persona, rango_edad,", "solicitudes"],
}


def dibujar_diagrama(ruta_png):
    """Esquema estrella del modelo como imagen (se inserta en el Léeme)."""
    pos = {  # centro (x, y), ancho, alto
        "hechos_solicitud": (6.0, 4.6, 3.6, 2.5),
        "hechos_estatus_mes": (6.0, 1.3, 3.6, 1.8),
        "dim_cliente": (6.0, 7.55, 3.2, 1.2),
        "dim_mes": (1.7, 6.2, 2.9, 1.0),
        "dim_vendedor": (1.7, 2.6, 2.9, 1.0),
        "dim_estatus": (10.3, 6.2, 2.9, 1.0),
        "dim_vehiculo": (10.3, 2.6, 2.9, 1.2),
    }
    fig, ax = plt.subplots(figsize=(12, 8.6), dpi=110)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8.5)
    ax.axis("off")

    dibujadas = set()
    for tabla, _, destino, _, activa in md.RELACIONES:
        (x1, y1, *_), (x2, y2, *_) = pos[tabla], pos[destino]
        if (tabla, destino) in dibujadas:   # segunda relación entre las mismas tablas
            y1, y2 = y1 - 0.45, y2 - 0.3
        dibujadas.add((tabla, destino))
        ax.plot([x1, x2], [y1, y2], color="#9CA3AF" if activa else "#C9A227",
                lw=1.3, ls="-" if activa else (0, (4, 3)), zorder=1)

    for nombre, (x, y, w, h) in pos.items():
        es_hecho = nombre.startswith("hechos")
        color = "#" + AZUL if es_hecho else "#5B7FD6"
        caja = FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                              fc="white", ec=color, lw=1.6, zorder=2)
        ax.add_patch(caja)
        ax.add_patch(FancyBboxPatch((x - w / 2, y + h / 2 - 0.42), w, 0.42,
                                    boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc=color, ec=color, lw=1.6, zorder=3))
        ax.text(x, y + h / 2 - 0.21, nombre, ha="center", va="center", color="white",
                fontsize=10.5, fontweight="bold", zorder=4)
        campos = _CAMPOS_DIAGRAMA[nombre]
        paso = (h - 0.55) / max(len(campos), 1)
        for i, campo in enumerate(campos):
            ax.text(x - w / 2 + 0.15, y + h / 2 - 0.62 - i * paso, campo, ha="left", va="center",
                    fontsize=8.6, color="#1F2937", zorder=4,
                    fontweight="bold" if campo.startswith("PK") else "normal")

    ax.plot([0.4, 0.9], [0.25, 0.25], color="#9CA3AF", lw=1.3)
    ax.text(1.0, 0.25, "relación activa (muchos a uno)", va="center", fontsize=8.5, color="#4B5563")
    ax.plot([4.0, 4.5], [0.25, 0.25], color="#C9A227", lw=1.3, ls=(0, (4, 3)))
    ax.text(4.6, 0.25, "relación inactiva (USERELATIONSHIP)", va="center", fontsize=8.5, color="#4B5563")
    plt.tight_layout()
    fig.savefig(ruta_png, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta_png


# =======================================================================
# Utilidades de formato
# =======================================================================
def _encabezado(celda):
    celda.font = Font(name=FUENTE, bold=True, color="FFFFFF", size=10)
    celda.fill = PatternFill("solid", fgColor=AZUL)
    celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _formato_columna(nombre):
    if nombre in COLS_MONEDA:
        return FMT_MONEDA
    if nombre in COLS_PCT:
        return COLS_PCT[nombre]
    if nombre == "fecha_inicio":
        return FMT_FECHA
    if nombre.startswith("id_mes") or nombre in ("primer_mes", "ultimo_mes", "anio", "anio_modelo"):
        return FMT_ENTERO
    return None


def _hoja_tabla(wb, nombre, df):
    ws = wb.create_sheet(nombre)
    columnas = list(df.columns)
    for j, col in enumerate(columnas, 1):
        _encabezado(ws.cell(row=1, column=j, value=col))
    for i, fila in enumerate(df.itertuples(index=False), 2):
        for j, valor in enumerate(fila, 1):
            if valor is None or (isinstance(valor, float) and pd.isna(valor)):
                valor = None
            elif isinstance(valor, pd.Timestamp):
                valor = valor.to_pydatetime()
            elif hasattr(valor, "item"):
                valor = valor.item()
            c = ws.cell(row=i, column=j, value=valor)
            c.font = Font(name=FUENTE, size=10)
    for j, col in enumerate(columnas, 1):
        fmt = _formato_columna(col)
        letra = get_column_letter(j)
        if fmt:
            for i in range(2, len(df) + 2):
                ws[f"{letra}{i}"].number_format = fmt
        largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(200).tolist()])
        ws.column_dimensions[letra].width = min(max(10, largo + 2), 48)
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "B2"

    # Tabla de Excel con nombre: es lo que Power BI lista al importar.
    fin = f"{get_column_letter(len(columnas))}{max(len(df) + 1, 2)}"
    tabla = Table(displayName=nombre, ref=f"A1:{fin}")
    tabla.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(tabla)
    return ws


def _rango(ws_nombre, df, columna):
    j = list(df.columns).index(columna) + 1
    letra = get_column_letter(j)
    return f"'{ws_nombre}'!${letra}$2:${letra}${max(len(df) + 1, 2)}"


# =======================================================================
# Hojas de apoyo
# =======================================================================
def _hoja_leeme(wb, modelo, fuentes, ruta_png):
    ws = wb.create_sheet("Léeme", 0)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 95

    meses = modelo["dim_mes"]
    h = modelo["hechos_solicitud"]
    periodo = f"{meses.mes_anio.iloc[0]} a {meses.mes_anio.iloc[-1]}" if len(meses) > 1 else meses.mes_anio.iloc[0]

    ws["B2"] = "Modelo de datos de la bitácora de solicitudes"
    ws["B2"].font = Font(name=FUENTE, size=16, bold=True, color=AZUL)
    ws["B3"] = f"Periodo: {periodo}  ·  Generado el {datetime.now():%d/%m/%Y %H:%M}"
    ws["B3"].font = Font(name=FUENTE, size=10, color=GRIS_TEXTO)
    ws["B4"] = f"Archivos de origen: {', '.join(fuentes)}"
    ws["B4"].font = Font(name=FUENTE, size=9, color=GRIS_TEXTO)

    texto = [
        f"{len(modelo['hechos_estatus_mes'])} renglones en las bitácoras = {len(h)} solicitudes únicas "
        f"({int(h.cruzo_mes.sum())} folios aparecen en más de un mes y aquí cuentan una sola vez).",
        "Sin datos de contacto: el cliente se identifica con una clave seudónima (id_cliente).",
        "Para Power BI: Obtener datos > Excel > marcar las tablas hechos_* y dim_* > crear las "
        "relaciones de la hoja Relaciones > copiar las medidas de la hoja Medidas DAX.",
        "Para actualizar: generar de nuevo con TODOS los meses (las claves se recalculan juntas).",
    ]
    for i, t in enumerate(texto):
        c = ws.cell(row=6 + i, column=2, value="•  " + t)
        c.font = Font(name=FUENTE, size=10)
        ws.merge_cells(start_row=6 + i, start_column=2, end_row=6 + i, end_column=4)

    fila = 11
    for j, enc in enumerate(["Tabla", "Renglones", "Qué contiene"], 2):
        _encabezado(ws.cell(row=fila, column=j, value=enc))
    for nombre in ORDEN_HOJAS:
        fila += 1
        ws.cell(row=fila, column=2, value=nombre).font = Font(name=FUENTE, size=10, bold=True,
                                                              color="0563C1", underline="single")
        ws.cell(row=fila, column=2).hyperlink = f"#'{nombre}'!A1"
        ws.cell(row=fila, column=3, value=len(modelo[nombre])).font = Font(name=FUENTE, size=10)
        c = ws.cell(row=fila, column=4, value=md.DESCRIPCION_TABLAS[nombre])
        c.font = Font(name=FUENTE, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[fila].height = 28

    if ruta_png and os.path.exists(ruta_png):
        img = XLImage(ruta_png)
        escala = 820 / img.width
        img.width, img.height = int(img.width * escala), int(img.height * escala)
        ws.add_image(img, f"B{fila + 2}")


def _hoja_cuadre(wb, modelo):
    """Conteos por mes con fórmulas sobre las hojas del modelo."""
    ws = wb.create_sheet("Cuadre", 1)
    ws.sheet_view.showGridLines = False
    e, h, m = modelo["hechos_estatus_mes"], modelo["hechos_solicitud"], modelo["dim_mes"]

    ws["A1"] = "Cuadre por mes"
    ws["A1"].font = Font(name=FUENTE, size=14, bold=True, color=AZUL)
    ws["A2"] = ("La 'foto' es lo que trae la bitácora de cada mes (cuadra con el Resumen Mensual). "
                "'Capturadas' cuenta cada folio una vez, en su mes de captura, con su último estatus.")
    ws["A2"].font = Font(name=FUENTE, size=9, color=GRIS_TEXTO)

    enc = ["Mes", "id_mes", "Foto: renglones", "Foto: financiadas", "Capturadas (únicas)",
           "Capturadas que ya se financiaron", "Conversión", "Monto financiado"]
    for j, t in enumerate(enc, 1):
        _encabezado(ws.cell(row=4, column=j, value=t))

    r_e_mes = _rango("hechos_estatus_mes", e, "id_mes")
    r_e_est = _rango("hechos_estatus_mes", e, "clave_estatus")
    r_h_mes = _rango("hechos_solicitud", h, "id_mes_captura")
    r_h_fin = _rango("hechos_solicitud", h, "financiado")
    r_h_monto = _rango("hechos_solicitud", h, "monto_financiar")

    fila = 5
    for _, mes in m.iterrows():
        ws.cell(row=fila, column=1, value=mes.mes_anio)
        ws.cell(row=fila, column=2, value=int(mes.id_mes))
        ws.cell(row=fila, column=3, value=f"=COUNTIFS({r_e_mes},B{fila})")
        ws.cell(row=fila, column=4, value=f'=COUNTIFS({r_e_mes},B{fila},{r_e_est},"FINANCIADO")')
        ws.cell(row=fila, column=5, value=f"=COUNTIFS({r_h_mes},B{fila})")
        ws.cell(row=fila, column=6, value=f"=SUMIFS({r_h_fin},{r_h_mes},B{fila})")
        ws.cell(row=fila, column=7, value=f"=IFERROR(F{fila}/E{fila},0)")
        ws.cell(row=fila, column=8, value=f"=SUMIFS({r_h_monto},{r_h_mes},B{fila},{r_h_fin},1)")
        fila += 1
    ws.cell(row=fila, column=1, value="Total")
    for j in (3, 4, 5, 6, 8):
        L = get_column_letter(j)
        ws.cell(row=fila, column=j, value=f"=SUM({L}5:{L}{fila - 1})")
    ws.cell(row=fila, column=7, value=f"=IFERROR(F{fila}/E{fila},0)")

    for i in range(5, fila + 1):
        for j in range(1, 9):
            c = ws.cell(row=i, column=j)
            c.font = Font(name=FUENTE, size=10, bold=(i == fila))
            c.border = Border(bottom=Side(style="thin", color=GRIS_BORDE))
        ws.cell(row=i, column=2).number_format = FMT_ENTERO
        ws.cell(row=i, column=7).number_format = FMT_PCT
        ws.cell(row=i, column=8).number_format = FMT_MONEDA
    ws.cell(row=fila + 2, column=1,
            value=("La foto suma más que las capturadas cuando hay folios que cruzan de mes: "
                   "la diferencia son esos folios contados en cada bitácora donde aparecen.")
            ).font = Font(name=FUENTE, size=9, italic=True, color=GRIS_TEXTO)
    anchos = [18, 10, 15, 16, 18, 22, 12, 18]
    for j, w in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[4].height = 32


def _hoja_simple(wb, titulo, encabezados, filas, anchos):
    ws = wb.create_sheet(titulo)
    for j, t in enumerate(encabezados, 1):
        _encabezado(ws.cell(row=1, column=j, value=t))
    for i, fila in enumerate(filas, 2):
        for j, v in enumerate(fila, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=FUENTE, size=10, bold=(j == 1 and titulo == "Medidas DAX"))
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for j, w in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    return ws


# =======================================================================
# Punto de entrada
# =======================================================================
def exportar_excel(modelo, ruta_xlsx, fuentes=(), carpeta_temporal=None):
    carpeta_temporal = carpeta_temporal or os.path.dirname(os.path.abspath(ruta_xlsx))
    ruta_png = os.path.join(carpeta_temporal, "_diagrama_modelo.png")
    dibujar_diagrama(ruta_png)

    wb = Workbook()
    wb.remove(wb.active)
    for nombre in ORDEN_HOJAS:
        _hoja_tabla(wb, nombre, modelo[nombre])
    _hoja_leeme(wb, modelo, list(fuentes), ruta_png)
    _hoja_cuadre(wb, modelo)

    _hoja_simple(
        wb, "Relaciones",
        ["Tabla (muchos)", "Columna", "Tabla (uno)", "Columna", "Estado"],
        [(a, b, c, d, "Activa" if act else "Inactiva") for a, b, c, d, act in md.RELACIONES],
        [22, 18, 22, 18, 12],
    )
    filas_dic = []
    for nombre in ORDEN_HOJAS:
        for col in modelo[nombre].columns:
            filas_dic.append((nombre, col, md.DICCIONARIO.get(col, "")))
    _hoja_simple(wb, "Diccionario", ["Tabla", "Columna", "Descripción"], filas_dic, [22, 24, 90])
    _hoja_simple(wb, "Medidas DAX", ["Medida", "Fórmula DAX", "Para qué sirve"],
                 [(n, f"{n} = {f}", d) for n, f, d in MEDIDAS_DAX], [28, 80, 60])

    # El Léeme y el Cuadre primero; luego apoyo y al final las tablas.
    orden = ["Léeme", "Cuadre", "Relaciones", "Diccionario", "Medidas DAX"] + ORDEN_HOJAS
    wb._sheets = [wb[n] for n in orden]
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True
    wb.save(ruta_xlsx)
    try:
        os.remove(ruta_png)
    except OSError:
        pass
    return ruta_xlsx
