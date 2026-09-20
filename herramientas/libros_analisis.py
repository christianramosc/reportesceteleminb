# -*- coding: utf-8 -*-
"""Libros de Excel con las tablas de cada reporte, en fórmulas vivas.

Hay dos constructores porque hay dos formas de reporte:

- libro_mensual(): un solo mes. Lo usan Avance Preliminar, Resumen Mensual
  y Resumen por Vendedor, que leen un único Excel de bitácora.
- libro_comparativo(): varios meses. Las tablas llevan una columna por mes
  y las fórmulas filtran además por la columna Mes de la hoja Datos.

Las dos producen tablas equivalentes a las del PDF; la diferencia es que
aquí cada número es una fórmula que se puede abrir y auditar.
"""

from openpyxl.utils import get_column_letter

from .exportador_excel import (FMT_ENTERO, FMT_MONEDA, FMT_PORCENTAJE,
                               LibroAnalisis)

COL_VENDEDOR = "Nombre del Vendedor"
COL_CATEGORIA = "Categoria"
COL_MONTO = "Monto Total a Financiar"
COL_PRECIO = "Precio Venta (c/IVA)"
COL_VEHICULO = "Vehículo"
COL_MES = "Mes"
COL_GAP = "¿Tiene GAP?"
COL_MONTO_GAP = "Monto GAP"


def _valores(df, columna):
    if columna not in df.columns:
        return []
    return sorted(df[columna].dropna().astype(str).unique().tolist())


def _hoja_vendedores(libro, df, categorias):
    """Una fila por vendedor; cada celda es un COUNTIFS o un SUMIFS.

    Las letras de columna se calculan con get_column_letter y no sumando al
    código de "C": con las columnas de GAP la tabla pasa de la Z y esa
    aritmética produciría referencias inválidas.
    """
    if not libro.tiene(COL_VENDEDOR, COL_CATEGORIA):
        return

    r_vend = libro.rango(COL_VENDEDOR)
    r_cat = libro.rango(COL_CATEGORIA)
    r_monto = libro.rango(COL_MONTO)
    r_gap = libro.rango(COL_GAP)
    r_monto_gap = libro.rango(COL_MONTO_GAP)
    hay_monto = bool(r_monto)
    hay_gap = bool(r_gap)

    # Se arma primero el orden de columnas y luego las fórmulas lo consultan
    # por nombre, para no tener que recontar posiciones al agregar una.
    cols = ["Vendedor", "Solicitudes"] + [c.title() for c in categorias] + \
           ["% Conversión a financiado"]
    if hay_monto:
        cols += ["Monto financiado", "Ticket promedio"]
    if hay_gap:
        cols += ["Con GAP", "% GAP", "GAP en financiados",
                 "% GAP dentro de financiados"]
        if r_monto_gap:
            cols.append("Monto GAP")

    L = {nombre: get_column_letter(i + 1) for i, nombre in enumerate(cols)}
    c_total = L["Solicitudes"]
    c_fin = L[ "Financiado".title() ] if "FINANCIADO" in categorias else None

    vendedores = _valores(df, COL_VENDEDOR)
    filas = []
    for i, vendedor in enumerate(vendedores):
        f = 4 + i
        fila = [vendedor, f'=COUNTIFS({r_vend},$A{f})']
        for cat in categorias:
            fila.append(f'=COUNTIFS({r_vend},$A{f},{r_cat},"{cat}")')
        # Denominador protegido: un vendedor puede quedar sin solicitudes.
        fila.append(f'=IF({c_total}{f}=0,"",{c_fin}{f}/{c_total}{f})'
                    if c_fin else "")
        if hay_monto:
            fila.append(f'=SUMIFS({r_monto},{r_vend},$A{f},{r_cat},"FINANCIADO")')
            # Sin créditos financiados el ticket queda en blanco, no en cero:
            # un $0 se lee como "vendió barato" cuando no vendió.
            fila.append(f'=IF({c_fin}{f}=0,"",{L["Monto financiado"]}{f}/{c_fin}{f})'
                        if c_fin else "")
        if hay_gap:
            fila.append(f'=COUNTIFS({r_vend},$A{f},{r_gap},"SI")')
            fila.append(f'=IF({c_total}{f}=0,"",{L["Con GAP"]}{f}/{c_total}{f})')
            fila.append(
                f'=COUNTIFS({r_vend},$A{f},{r_gap},"SI",{r_cat},"FINANCIADO")'
                if c_fin else "")
            # El GAP dentro de FINANCIADOS es el que ya está efectivamente
            # vendido; el % general incluye solicitudes que aún pueden caerse.
            fila.append(
                f'=IF({c_fin}{f}=0,"",{L["GAP en financiados"]}{f}/{c_fin}{f})'
                if c_fin else "")
            if r_monto_gap:
                fila.append(f'=SUMIFS({r_monto_gap},{r_vend},$A{f},{r_gap},"SI")')
        filas.append(fila)

    ultima = 3 + len(vendedores)
    ft = ultima + 1                      # fila de totales

    def suma(nombre):
        letra = L[nombre]
        return f"=SUM({letra}4:{letra}{ultima})"

    total = ["TOTAL EQUIPO", suma("Solicitudes")]
    for cat in categorias:
        total.append(suma(cat.title()))
    total.append(f'=IF({c_total}{ft}=0,"",{c_fin}{ft}/{c_total}{ft})' if c_fin else "")
    if hay_monto:
        total.append(suma("Monto financiado"))
        total.append(f'=IF({c_fin}{ft}=0,"",{L["Monto financiado"]}{ft}/{c_fin}{ft})'
                     if c_fin else "")
    if hay_gap:
        total.append(suma("Con GAP"))
        total.append(f'=IF({c_total}{ft}=0,"",{L["Con GAP"]}{ft}/{c_total}{ft})')
        total.append(suma("GAP en financiados") if c_fin else "")
        total.append(f'=IF({c_fin}{ft}=0,"",{L["GAP en financiados"]}{ft}/{c_fin}{ft})'
                     if c_fin else "")
        if r_monto_gap:
            total.append(suma("Monto GAP"))

    formatos = {}
    for nombre in cols:
        idx = cols.index(nombre)
        if nombre.startswith("%"):
            formatos[idx] = FMT_PORCENTAJE
        elif nombre.startswith("Monto") or nombre.startswith("Ticket"):
            formatos[idx] = FMT_MONEDA
        elif nombre != "Vendedor":
            formatos[idx] = FMT_ENTERO

    libro.agregar_tabla(
        "Por vendedor", cols, filas,
        descripcion="Desempeño por vendedor, incluida la colocación de GAP",
        formatos=formatos, fila_total=total,
        nota=("El ticket promedio divide entre los créditos FINANCIADOS, no "
              "entre las solicitudes; con pocos créditos una sola operación "
              "mueve el promedio. El % de GAP dentro de financiados es el "
              "indicador que cuenta: ese GAP ya está vendido, mientras que "
              "el % general incluye solicitudes que todavía pueden caerse."),
    )


def _hoja_estatus(libro, df, categorias):
    """Conteo, participación y monto por categoría de estatus."""
    if not libro.tiene(COL_CATEGORIA):
        return
    r_cat = libro.rango(COL_CATEGORIA)
    r_monto = libro.rango(COL_MONTO)
    total_filas = libro.filas_datos

    encabezados = ["Estatus", "Solicitudes", "% del total"]
    if r_monto:
        encabezados += ["Monto total", "Monto promedio"]

    filas = []
    for i, cat in enumerate(categorias):
        f = 4 + i
        fila = [cat.title(), f'=COUNTIFS({r_cat},"{cat}")',
                f'=IFERROR(B{f}/{total_filas},0)']
        if r_monto:
            fila.append(f'=SUMIFS({r_monto},{r_cat},"{cat}")')
            fila.append(f'=IF(B{f}=0,"",D{f}/B{f})')
        filas.append(fila)

    ultima = 3 + len(categorias)
    total = ["TOTAL", f"=SUM(B4:B{ultima})", f"=SUM(C4:C{ultima})"]
    if r_monto:
        total += [f"=SUM(D4:D{ultima})",
                  f"=IFERROR(D{ultima + 1}/B{ultima + 1},0)"]

    formatos = {1: FMT_ENTERO, 2: FMT_PORCENTAJE}
    if r_monto:
        formatos[3] = FMT_MONEDA
        formatos[4] = FMT_MONEDA

    libro.agregar_tabla(
        "Por estatus", encabezados, filas,
        descripcion="Distribución por estatus de la solicitud",
        formatos=formatos, fila_total=total,
        nota=f"El % del total se calcula sobre las {total_filas} filas de la hoja Datos.",
    )


def _hoja_modelos(libro, df):
    if not libro.tiene(COL_VEHICULO):
        return
    r_veh = libro.rango(COL_VEHICULO)
    r_monto = libro.rango(COL_MONTO)
    modelos = _valores(df, COL_VEHICULO)

    encabezados = ["Vehículo", "Solicitudes"]
    if r_monto:
        encabezados.append("Monto financiado")
    filas = []
    for i, modelo in enumerate(modelos):
        f = 4 + i
        # El nombre va en la celda y la fórmula la referencia, para que
        # cambiar el texto del modelo reetiquete el renglón completo.
        fila = [modelo, f'=COUNTIFS({r_veh},$A{f})']
        if r_monto:
            r_cat = libro.rango(COL_CATEGORIA)
            fila.append(f'=SUMIFS({r_monto},{r_veh},$A{f},{r_cat},"FINANCIADO")'
                        if r_cat else f'=SUMIFS({r_monto},{r_veh},$A{f})')
        filas.append(fila)

    ultima = 3 + len(modelos)
    total = ["TOTAL", f"=SUM(B4:B{ultima})"]
    if r_monto:
        total.append(f"=SUM(C4:C{ultima})")

    formatos = {1: FMT_ENTERO, 2: FMT_MONEDA}
    libro.agregar_tabla(
        "Por modelo", encabezados, filas,
        descripcion="Modelos solicitados",
        formatos=formatos, fila_total=total,
    )


def libro_mensual(df, ruta, titulo, fuente_datos):
    """Libro para los reportes de un solo mes."""
    categorias = _valores(df, COL_CATEGORIA)
    libro = LibroAnalisis(titulo, fuente_datos)
    libro.agregar_datos(df, descripcion="Bitácora del mes, ya normalizada por el reporte")
    _hoja_estatus(libro, df, categorias)
    _hoja_vendedores(libro, df, categorias)
    _hoja_modelos(libro, df)
    return libro.guardar(ruta)


def libro_comparativo(df_combinado, orden_meses, ruta, titulo, fuente_datos):
    """Libro para el comparativo: una columna por mes en cada tabla."""
    categorias = _valores(df_combinado, COL_CATEGORIA)
    libro = LibroAnalisis(
        titulo, fuente_datos,
        notas=["La columna Mes de la hoja Datos es la que separa los "
               "periodos; todas las tablas por mes filtran por ella."])
    libro.agregar_datos(df_combinado,
                        descripcion="Los meses comparados, apilados y con columna Mes")

    r_mes = libro.rango(COL_MES)
    r_cat = libro.rango(COL_CATEGORIA)
    r_vend = libro.rango(COL_VENDEDOR)
    r_monto = libro.rango(COL_MONTO)

    # ---- Resumen por mes (la tabla del resumen ejecutivo) ----
    if r_mes and r_cat:
        encabezados = ["Mes", "Total"] + [c.title() for c in categorias] + \
                      ["% Financiado"]
        if r_monto:
            encabezados += ["Monto financiado", "Ticket promedio"]
        filas = []
        for i, mes in enumerate(orden_meses):
            f = 4 + i
            fila = [str(mes).title(), f'=COUNTIFS({r_mes},$A{f})']
            for cat in categorias:
                fila.append(f'=COUNTIFS({r_mes},$A{f},{r_cat},"{cat}")')
            col_fin = chr(ord("C") + categorias.index("FINANCIADO")) \
                if "FINANCIADO" in categorias else None
            fila.append(f'=IFERROR({col_fin}{f}/B{f},0)' if col_fin else 0)
            if r_monto:
                fila.append(f'=SUMIFS({r_monto},{r_mes},$A{f},{r_cat},"FINANCIADO")')
                letra = chr(ord("C") + len(categorias) + 1)
                fila.append(f'=IF({col_fin}{f}=0,"",{letra}{f}/{col_fin}{f})'
                            if col_fin else "")
            filas.append(fila)

        formatos = {1: FMT_ENTERO}
        for k in range(len(categorias)):
            formatos[2 + k] = FMT_ENTERO
        formatos[2 + len(categorias)] = FMT_PORCENTAJE
        if r_monto:
            formatos[3 + len(categorias)] = FMT_MONEDA
            formatos[4 + len(categorias)] = FMT_MONEDA

        ultima = 3 + len(orden_meses)
        total = ["TOTAL", f"=SUM(B4:B{ultima})"]
        for k in range(len(categorias)):
            letra = chr(ord("C") + k)
            total.append(f"=SUM({letra}4:{letra}{ultima})")
        col_fin_t = chr(ord("C") + categorias.index("FINANCIADO")) \
            if "FINANCIADO" in categorias else None
        total.append(f"=IFERROR({col_fin_t}{ultima + 1}/B{ultima + 1},0)" if col_fin_t else 0)
        if r_monto:
            letra = chr(ord("C") + len(categorias) + 1)
            total.append(f"=SUM({letra}4:{letra}{ultima})")
            total.append(f'=IF({col_fin_t}{ultima + 1}=0,"",{letra}{ultima + 1}/{col_fin_t}{ultima + 1})'
                         if col_fin_t else "")

        libro.agregar_tabla(
            "Resumen por mes", encabezados, filas,
            descripcion="Comparativo por mes — equivale a la tabla del resumen ejecutivo",
            formatos=formatos, fila_total=total,
        )

    # ---- Vendedor por mes, con promedio y variación ----
    if r_mes and r_vend:
        vendedores = _valores(df_combinado, COL_VENDEDOR)
        meses = [str(m).title() for m in orden_meses]
        encabezados = ["Vendedor"] + meses + ["Total", "Promedio por mes"]
        if len(meses) >= 2:
            encabezados += ["Variación", "% Cambio"]

        filas = []
        for i, vendedor in enumerate(vendedores):
            f = 4 + i
            fila = [vendedor]
            for k, mes in enumerate(orden_meses):
                fila.append(f'=COUNTIFS({r_vend},$A{f},{r_mes},"{mes}")')
            primera = "B"
            ultima_mes = chr(ord("B") + len(meses) - 1)
            fila.append(f'=SUM({primera}{f}:{ultima_mes}{f})')
            col_total = chr(ord("B") + len(meses))
            # El promedio divide entre TODOS los meses comparados: un mes sin
            # solicitudes cuenta como cero, que es justo lo que se busca ver.
            fila.append(f'={col_total}{f}/{len(meses)}')
            if len(meses) >= 2:
                fila.append(f'={ultima_mes}{f}-{primera}{f}')
                col_var = chr(ord("B") + len(meses) + 2)
                # Partir de cero no tiene cambio porcentual medible.
                fila.append(f'=IF({primera}{f}=0,"",{col_var}{f}/{primera}{f})')
            filas.append(fila)

        ultima = 3 + len(vendedores)
        total = ["TOTAL EQUIPO"]
        for k in range(len(meses) + 2):
            letra = chr(ord("B") + k)
            total.append(f"=SUM({letra}4:{letra}{ultima})")
        if len(meses) >= 2:
            for k in (len(meses) + 2,):
                letra = chr(ord("B") + k)
                total.append(f"=SUM({letra}4:{letra}{ultima})")
            total.append("")

        formatos = {}
        for k in range(len(meses) + 1):
            formatos[1 + k] = FMT_ENTERO
        formatos[len(meses) + 2] = '0.0'
        if len(meses) >= 2:
            formatos[len(meses) + 3] = FMT_ENTERO
            formatos[len(meses) + 4] = FMT_PORCENTAJE

        libro.agregar_tabla(
            "Vendedor por mes", encabezados, filas,
            descripcion="Solicitudes por vendedor y mes, con promedio y variación",
            formatos=formatos, fila_total=total,
            nota=("La variación compara el último mes contra el primero; los "
                  "meses intermedios no entran en esa columna. El % queda en "
                  "blanco cuando el primer mes fue cero."),
        )

    _hoja_vendedores(libro, df_combinado, categorias)
    _hoja_modelos(libro, df_combinado)
    return libro.guardar(ruta)
