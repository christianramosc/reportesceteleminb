# -*- coding: utf-8 -*-
"""Construcción de los libros de Excel que acompañan a cada reporte.

Idea de fondo
-------------
El PDF muestra conclusiones; este libro muestra de dónde salieron. Por eso
las tablas NO llevan los números calculados en Python: llevan fórmulas vivas
(COUNTIFS, SUMIFS, AVERAGEIFS) que apuntan a la hoja "Datos".

La consecuencia práctica es la que pediste: quien reciba el archivo puede
filtrar la hoja Datos, cambiar un estatus o agregar filas, y todas las
tablas se recalculan solas. Si los números vinieran pegados como texto, el
archivo sería una foto y habría que volver a correr el reporte para
cualquier pregunta nueva.

Notas técnicas
--------------
- Se usan funciones anteriores a Excel 2007 a propósito (COUNTIFS, SUMIFS,
  IFERROR, INDEX). Las modernas tipo XLOOKUP o FILTER no sobreviven a todos
  los lectores y quedarían como #NAME?.
- Las fórmulas se escriben sin valor en caché, así que el libro se marca con
  fullCalcOnLoad para que Excel las calcule al abrirlo.
- Los rangos se construyen acotados al número real de filas y no con
  columnas enteras: COUNTIFS sobre "A:A" en un libro con varias hojas es
  notablemente más lento al recalcular.
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FUENTE = "Arial"

AZUL_ENCABEZADO = "1F3864"
GRIS_BANDA = "F2F4F7"
GRIS_BORDE = "D9DDE3"
AZUL_TEXTO = "1F3864"

FMT_MONEDA = '"$"#,##0;("$"#,##0);-'
FMT_PORCENTAJE = '0.0%'
FMT_ENTERO = '#,##0;-#,##0;-'

_BORDE = Border(
    bottom=Side(style="thin", color=GRIS_BORDE),
    top=Side(style="thin", color=GRIS_BORDE),
    left=Side(style="thin", color=GRIS_BORDE),
    right=Side(style="thin", color=GRIS_BORDE),
)


class LibroAnalisis:
    """Acumula hojas y las escribe como un .xlsx."""

    def __init__(self, titulo, fuente_datos, notas=None):
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        self.titulo = titulo
        self.fuente_datos = fuente_datos
        self.notas = list(notas or [])
        self._indice = []          # (hoja, descripción) para la portada
        self.hoja_datos = None     # nombre de la hoja de datos
        self.columnas = {}         # nombre de columna -> letra
        self.filas_datos = 0

    # ---------------------------------------------------------------- datos
    def agregar_datos(self, df, nombre="Datos",
                      descripcion="Filas tal como las leyó el reporte"):
        """Escribe la hoja base a la que apuntan todas las fórmulas."""
        ws = self.wb.create_sheet(nombre)
        columnas = list(df.columns)

        for j, col in enumerate(columnas, start=1):
            celda = ws.cell(row=1, column=j, value=str(col))
            celda.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor=AZUL_ENCABEZADO)
            celda.alignment = Alignment(horizontal="center", vertical="center",
                                        wrap_text=True)

        for i, (_, fila) in enumerate(df.iterrows(), start=2):
            for j, col in enumerate(columnas, start=1):
                valor = fila[col]
                # NaN se escribe como celda vacía: un "nan" de texto rompería
                # cualquier SUMIFS que pase por esa columna.
                if valor != valor:
                    valor = None
                elif hasattr(valor, "item"):
                    valor = valor.item()
                celda = ws.cell(row=i, column=j, value=valor)
                celda.font = Font(name=FUENTE, size=10)

        self.hoja_datos = nombre
        self.filas_datos = len(df)
        self.columnas = {str(c): get_column_letter(j)
                         for j, c in enumerate(columnas, start=1)}

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = (f"A1:{get_column_letter(len(columnas))}"
                              f"{max(2, len(df) + 1)}")
        self._ajustar_anchos(ws, df)
        self._indice.append((nombre, descripcion))
        return ws

    def rango(self, columna):
        """Rango absoluto de una columna de Datos, acotado a las filas reales.

        Devuelve "" si la columna no existe en este archivo: los reportes
        aceptan bitácoras con columnas distintas y una fórmula que apunte a
        una columna inexistente quedaría como #REF!.
        """
        letra = self.columnas.get(columna)
        if not letra:
            return ""
        return (f"'{self.hoja_datos}'!${letra}$2:"
                f"${letra}${self.filas_datos + 1}")

    def tiene(self, *columnas):
        return all(c in self.columnas for c in columnas)

    # --------------------------------------------------------------- tablas
    def agregar_tabla(self, nombre, encabezados, filas, descripcion="",
                      formatos=None, nota=None, fila_total=None):
        """Escribe una hoja de tabla.

        `filas` son listas; un elemento que empieza con "=" se escribe como
        fórmula. `formatos` mapea índice de columna (base 0) a formato.
        """
        ws = self.wb.create_sheet(nombre)
        formatos = formatos or {}

        ws.cell(row=1, column=1, value=descripcion or nombre).font = Font(
            name=FUENTE, size=11, bold=True, color=AZUL_TEXTO)
        fila_actual = 3

        for j, texto in enumerate(encabezados, start=1):
            celda = ws.cell(row=fila_actual, column=j, value=texto)
            celda.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor=AZUL_ENCABEZADO)
            celda.alignment = Alignment(horizontal="center", vertical="center",
                                        wrap_text=True)
            celda.border = _BORDE

        for i, datos in enumerate(filas):
            fila_actual += 1
            for j, valor in enumerate(datos, start=1):
                celda = ws.cell(row=fila_actual, column=j, value=valor)
                celda.font = Font(name=FUENTE, size=10)
                celda.border = _BORDE
                if i % 2 == 1:
                    celda.fill = PatternFill("solid", fgColor=GRIS_BANDA)
                if (j - 1) in formatos:
                    celda.number_format = formatos[j - 1]

        if fila_total:
            fila_actual += 1
            for j, valor in enumerate(fila_total, start=1):
                celda = ws.cell(row=fila_actual, column=j, value=valor)
                celda.font = Font(name=FUENTE, size=10, bold=True)
                celda.border = _BORDE
                celda.fill = PatternFill("solid", fgColor="E7ECF3")
                if (j - 1) in formatos:
                    celda.number_format = formatos[j - 1]

        if nota:
            ws.cell(row=fila_actual + 2, column=1, value=nota).font = Font(
                name=FUENTE, size=9, italic=True, color="5D6E85")

        ws.freeze_panes = f"A{4}"
        for j, texto in enumerate(encabezados, start=1):
            largo = max([len(str(texto))] +
                        [len(str(f[j - 1])) for f in filas
                         if len(f) >= j and not str(f[j - 1]).startswith("=")]
                        or [10])
            ws.column_dimensions[get_column_letter(j)].width = min(38, max(12, largo + 3))

        self._indice.append((nombre, descripcion))
        return ws

    # -------------------------------------------------------------- portada
    def _escribir_portada(self):
        ws = self.wb.create_sheet("Léeme", 0)
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 86

        ws["A1"] = self.titulo
        ws["A1"].font = Font(name=FUENTE, size=14, bold=True, color=AZUL_TEXTO)

        lineas = [
            ("Archivo de origen", self.fuente_datos),
            ("Cómo leerlo",
             "La hoja Datos es la fuente; las demás hojas la consultan con "
             "fórmulas vivas (COUNTIFS, SUMIFS, AVERAGEIFS)."),
            ("Se puede editar",
             "Si cambias un estatus, un monto o agregas filas en Datos, las "
             "tablas se recalculan solas. No hay números pegados a mano."),
            ("Si una celda sale en blanco",
             "Abre el archivo con Excel o LibreOffice: las fórmulas se "
             "calculan al abrir. Un visor rápido puede mostrarlas vacías."),
            ("Ojo con los filtros",
             "Filtrar la hoja Datos oculta filas pero NO cambia los totales: "
             "COUNTIFS y SUMIFS cuentan también lo oculto."),
        ]
        for nota in self.notas:
            lineas.append(("Nota", nota))

        fila = 3
        for etiqueta, texto in lineas:
            ws.cell(row=fila, column=1, value=etiqueta).font = Font(
                name=FUENTE, size=10, bold=True)
            celda = ws.cell(row=fila, column=2, value=texto)
            celda.font = Font(name=FUENTE, size=10)
            celda.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[fila].height = 30
            fila += 1

        fila += 1
        ws.cell(row=fila, column=1, value="Contenido").font = Font(
            name=FUENTE, size=11, bold=True, color=AZUL_TEXTO)
        fila += 1
        for hoja, descripcion in self._indice:
            ws.cell(row=fila, column=1, value=hoja).font = Font(
                name=FUENTE, size=10, bold=True)
            ws.cell(row=fila, column=2, value=descripcion).font = Font(
                name=FUENTE, size=10)
            fila += 1

    @staticmethod
    def _ajustar_anchos(ws, df):
        for j, col in enumerate(df.columns, start=1):
            # str(v) y no .astype(str): en una columna que quedó toda vacía
            # (existe en un mes del comparativo y no en otro), astype(str)
            # deja los NaN como float y el len() truena.
            muestra = df[col].head(60).tolist()
            largo = max([len(str(col))] + [len(str(v)) for v in muestra] or [10])
            ws.column_dimensions[get_column_letter(j)].width = min(34, max(11, largo + 2))

    def guardar(self, ruta):
        self._escribir_portada()
        # openpyxl no guarda valores en caché para las fórmulas: sin esto,
        # Excel abriría el libro con las celdas calculadas en blanco.
        self.wb.calculation.fullCalcOnLoad = True
        self.wb.save(ruta)
        return ruta
