"""Cifras clave de la columna lateral de la portada.

Cada reporte tiene un propósito distinto, así que muestra cifras distintas.
Todas se calculan aquí a partir de los datos, no de las variables internas
de cada reporte, para que la columna no dependa de cómo está escrito cada
uno por dentro.

Regla de color: una cifra sale en rojo (alerta=True) solo si cae en zona de
alerta. Hoy el único umbral es el de GAP (conclusiones.UMBRAL_ALERTA_GAP):
lo esperado es el 100%, y por debajo de la mitad se marca en rojo.

Una cifra es un dict: {"etiqueta", "valor", "nota", "alerta"}.
"""

import pandas as pd

from . import conclusiones as _c

COL_CAT, COL_GAP, COL_MONTO = "Categoria", "¿Tiene GAP?", "Monto Total a Financiar"


def _cifra(etiqueta, valor, nota="", alerta=False):
    return {"etiqueta": etiqueta, "valor": valor, "nota": nota, "alerta": alerta}


def _monto_corto(valor):
    """$2.09 M / $347,590: en la columna lateral no caben los centavos."""
    if valor >= 1_000_000:
        return f"${valor / 1_000_000:.2f} M"
    return f"${valor:,.0f}"


def _financiados(df):
    return df[df[COL_CAT] == "FINANCIADO"] if COL_CAT in df.columns else df.iloc[0:0]


def _nota_gap(con_gap, total, unidad):
    """"4 sin GAP de 6 créditos" / "todos lo llevan". Se cuenta lo que falta
    contra el total, porque lo esperado es que todos lo lleven."""
    faltan = total - con_gap
    if faltan == 0:
        return "todos lo llevan" if unidad == "créditos" else "todas lo llevan"
    return f"{faltan} sin GAP de {total} {unidad}"


def _cifra_monto(df):
    fin = _financiados(df)
    if COL_MONTO not in df.columns or fin.empty:
        return None
    monto = float(fin[COL_MONTO].fillna(0).sum())
    return _cifra("MONTO FINANCIADO", _monto_corto(monto),
                  f"ticket de ${monto / len(fin):,.0f}")


def _cifra_monto_promedio_mensual(df, n_meses):
    """Comparativo: monto financiado del periodo y su promedio POR MES.

    En un reporte que compara meses, el dato útil junto al total es cuánto se
    financia en un mes típico. El ticket (promedio por crédito) sigue en las
    tablas del reporte; en la portada lo sustituye este promedio mensual.
    Dividir el total entre los meses no depende de a qué mes se atribuya
    cada crédito, así que no le afectan los folios que cruzan de mes.
    """
    fin = _financiados(df)
    if COL_MONTO not in df.columns or fin.empty or not n_meses:
        return None
    monto = float(fin[COL_MONTO].fillna(0).sum())
    return _cifra("MONTO FINANCIADO", _monto_corto(monto),
                  f"{_monto_corto(monto / n_meses)} promedio por mes")


def _cifra_gap_financiados(df):
    fin = _financiados(df)
    if COL_GAP not in df.columns or fin.empty:
        return None
    g = int((fin[COL_GAP] == "SI").sum())
    pct = g / len(fin) * 100
    return _cifra("GAP EN FINANCIADOS", f"{pct:.0f}%", _nota_gap(g, len(fin), "créditos"),
                  alerta=pct < _c.UMBRAL_ALERTA_GAP)


def _abiertas(df):
    conteo = _c._conteo_categorias(df)
    claves = _c._abiertas_presentes(conteo)
    mask = df[COL_CAT].isin(claves) if claves else pd.Series(False, index=df.index)
    monto = float(df.loc[mask, COL_MONTO].fillna(0).sum()) if COL_MONTO in df.columns else 0.0
    return int(mask.sum()), monto


def _conversion(df):
    total = len(df)
    fin = len(_financiados(df))
    return fin, total, (fin / total * 100 if total else 0.0)


# ------------------------------------------------ contra el mes anterior
def indicadores(df):
    """Los indicadores que se comparan de un mes a otro. Los que no se
    pueden calcular (falta la columna, o no hay créditos) quedan en None."""
    fin_n, total, pct = _conversion(df)
    fin = _financiados(df)
    monto = (float(fin[COL_MONTO].fillna(0).sum())
             if COL_MONTO in df.columns and COL_CAT in df.columns else None)
    gap = (float((fin[COL_GAP] == "SI").sum()) / len(fin) * 100
           if COL_GAP in df.columns and len(fin) else None)
    return {
        "solicitudes": total,
        "financiados": fin_n if COL_CAT in df.columns else None,
        "conversion": pct if COL_CAT in df.columns else None,
        "monto": monto,
        "ticket": monto / fin_n if monto is not None and fin_n else None,
        "gap": gap,
    }


# clave, nombre en la tabla, tipo de dato
_INDICADORES = [
    ("solicitudes", "Solicitudes", "conteo"),
    ("financiados", "Créditos financiados", "conteo"),
    ("conversion", "Conversión a financiado", "pct"),
    ("monto", "Monto financiado", "monto"),
    ("ticket", "Ticket promedio", "monto"),
    ("gap", "GAP en financiados", "pct"),
]


def _texto_valor(valor, tipo):
    if valor is None:
        return "—"
    if tipo == "conteo":
        return f"{int(valor)}"
    if tipo == "pct":
        return f"{valor:.1f}%"
    return f"${valor:,.0f}"


def _texto_cambio(anterior, actual, tipo):
    """"+8 (+15%)", "+3.3 pts", "-12%", "sin cambio"."""
    if anterior is None or actual is None:
        return "—"
    delta = actual - anterior
    if tipo == "pct":
        return "sin cambio" if abs(delta) < 0.05 else f"{delta:+.1f} pts"
    if abs(delta) < 0.5:
        return "sin cambio"
    relativo = f"{delta / anterior * 100:+.0f}%" if anterior else None
    if tipo == "conteo":
        return f"{int(delta):+d}" + (f" ({relativo})" if relativo else "")
    return relativo or f"{'+' if delta > 0 else '-'}${abs(delta):,.0f}"


def comparar_meses(df, df_anterior):
    """Compara los indicadores de un mes contra los del anterior.

    Devuelve una lista de dicts, uno por indicador que exista en ambos:
    {"clave", "nombre", "anterior", "actual", "cambio", "mejora"} con los
    valores ya como texto. "mejora" es True/False/None (None = sin cambio).
    En todos estos indicadores, más es mejor.
    """
    return comparar_indicadores(indicadores(df_anterior), indicadores(df))


def comparar_indicadores(antes, ahora):
    """Lo mismo que comparar_meses, a partir de indicadores() ya calculados."""
    filas = []
    for clave, nombre, tipo in _INDICADORES:
        a, b = antes[clave], ahora[clave]
        if a is None and b is None:
            continue
        cambio = _texto_cambio(a, b, tipo)
        mejora = None if cambio in ("—", "sin cambio") else b > a
        filas.append({"clave": clave, "nombre": nombre, "anterior": _texto_valor(a, tipo),
                      "actual": _texto_valor(b, tipo), "cambio": cambio, "mejora": mejora})
    return filas


# ---------------------------------------------------------------- reportes
def cifras_resumen(df, comparacion=None, mes_anterior=""):
    """comparacion: lo que devuelve comparar_meses() si se subió la bitácora
    del mes anterior; cada cifra lleva entonces su cambio contra ese mes."""
    fin, total, pct = _conversion(df)
    n_ab, monto_ab = _abiertas(df)
    cifras = [
        _cifra("SOLICITUDES", f"{total}", "registradas en el mes"),
        _cifra("CONVERSIÓN", f"{pct:.0f}%", f"{fin} de {total} financiadas"),
        _cifra_monto(df),
        _cifra_gap_financiados(df),
        _cifra("SIN DISPERSAR", f"{n_ab}",
               f"{_monto_corto(monto_ab)} abiertos al cierre" if monto_ab else "abiertas al cierre"),
    ]
    cifras = [c for c in cifras if c]
    _anotar_cambios(cifras, comparacion, mes_anterior,
                    (("SOLICITUDES", "solicitudes"), ("CONVERSIÓN", "conversion"),
                     ("MONTO FINANCIADO", "monto"), ("GAP EN FINANCIADOS", "gap")))
    return cifras


def cifras_avance(df, ctx=None, hoja=None):
    fin, total, pct = _conversion(df)
    n_ab, monto_ab = _abiertas(df)
    cifras = [
        _cifra("SOLICITUDES", f"{total}", "a la fecha de corte"),
        _cifra("FINANCIADAS", f"{fin}", f"{pct:.0f}% de conversión"),
        _cifra("POR CERRAR", f"{n_ab}",
               f"{_monto_corto(monto_ab)} a financiar" if monto_ab else "aprobadas o en trámite"),
    ]
    if ctx:
        mes_datos = _c.mes_desde_hoja(hoja)
        coherente = not (mes_datos and ctx.get("fecha_corte") and mes_datos != ctx["fecha_corte"].month)
        if coherente:
            cifras.append(_cifra("DÍAS RESTANTES", f"{ctx['dias_restantes']}",
                                 f"de {ctx['dias_en_mes']} del mes"))
        else:
            # Mismo criterio que los focos: si el corte no es del mes de los
            # datos, los días restantes no significan nada.
            cifras.append(_cifra("DÍAS RESTANTES", "—", "el corte es de otro mes", alerta=True))
    cifras.append(_cifra_gap_financiados(df))
    return [c for c in cifras if c]


def cifras_comparativo(df_unico, tabla_comp, n_meses):
    """df_unico: un renglón por folio (ver folios.consolidar)."""
    fin, total, pct = _conversion(df_unico)
    cifras = [
        _cifra("SOLICITUDES", f"{total}", f"en {n_meses} mes{'es' if n_meses != 1 else ''}"),
        _cifra("CONVERSIÓN", f"{pct:.0f}%", f"{fin} financiadas en el periodo"),
        _cifra_monto_promedio_mensual(df_unico, n_meses),
    ]
    if n_meses >= 2 and "% Financiado" in tabla_comp.columns and not tabla_comp.empty:
        conv = tabla_comp["% Financiado"].astype(float)
        cifras.append(_cifra("MENOR CONVERSIÓN", f"{conv.min():.1f}%", str(conv.idxmin()).title()))
    cifras.append(_cifra_gap_financiados(df_unico))
    return [c for c in cifras if c]


def cifras_vendedor(df_equipo, vendedor, comparacion=None, mes_anterior=""):
    """comparacion: comparar_indicadores() del vendedor contra su mes
    anterior, si se subieron bitácoras anteriores."""
    mio = df_equipo[df_equipo["Nombre del Vendedor"] == vendedor]
    _, n, pct = _conversion(mio)
    _, total_eq, pct_eq = _conversion(df_equipo)
    cifras = [
        _cifra("TUS SOLICITUDES", f"{n}", f"de {total_eq} del equipo"),
        _cifra("TU CONVERSIÓN", f"{pct:.0f}%", f"equipo: {pct_eq:.0f}%"),
    ]
    if COL_GAP in mio.columns and n:
        g = int((mio[COL_GAP] == "SI").sum())
        pg = g / n * 100
        cifras.append(_cifra("GAP EN SOLICITUDES", f"{pg:.0f}%", _nota_gap(g, n, "solicitudes"),
                             alerta=pg < _c.UMBRAL_ALERTA_GAP))
    n_ab, _ = _abiertas(mio)
    cifras.append(_cifra("PENDIENTES", f"{n_ab}", "sin dispersar"))
    _anotar_cambios(cifras, comparacion, mes_anterior,
                    (("TUS SOLICITUDES", "solicitudes"), ("TU CONVERSIÓN", "conversion")))
    return cifras


def _anotar_cambios(cifras, comparacion, mes_anterior, pares):
    """Agrega a cada cifra su cambio contra el mes anterior ("+3 vs. septiembre")."""
    if not comparacion:
        return
    cambios = {f["clave"]: f for f in comparacion}
    contra = f"vs. {str(mes_anterior).split()[0].lower()}" if mes_anterior else "vs. mes anterior"
    for etiqueta, clave in pares:
        cifra = next((c for c in cifras if c["etiqueta"] == etiqueta), None)
        fila = cambios.get(clave)
        if cifra and fila and fila["cambio"] != "—":
            cifra["cambio"] = f"{fila['cambio']} {contra}"
            cifra["mejora"] = fila["mejora"]


def bloque_cifras(cifras):
    """Tabla con las cifras, en el lugar donde iban las tarjetas de KPI.

    En el Word se queda como una tabla normal. Al construir el PDF,
    pdf_util.construir_con_lateral la retira del flujo y la dibuja como la
    columna lateral de la portada. Por eso lleva las cifras como atributo.
    """
    from reportlab.platypus import Table
    filas = [[c["etiqueta"].title(), c["valor"],
              c["nota"] + (f" · {c['cambio']}" if c.get("cambio") else "")] for c in cifras]
    tabla = Table([["Cifra clave", "Valor", ""]] + filas)
    tabla._cifras_clave = cifras
    return tabla
