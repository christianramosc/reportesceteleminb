# -*- coding: utf-8 -*-
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

try:
    from . import conclusiones as _c
except ImportError:  # ejecución suelta (Colab)
    import conclusiones as _c

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


# ---------------------------------------------------------------- reportes
def cifras_resumen(df):
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
    return [c for c in cifras if c]


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
        _cifra_monto(df_unico),
    ]
    if n_meses >= 2 and "% Financiado" in tabla_comp.columns and not tabla_comp.empty:
        conv = tabla_comp["% Financiado"].astype(float)
        cifras.append(_cifra("MENOR CONVERSIÓN", f"{conv.min():.1f}%", str(conv.idxmin()).title()))
    cifras.append(_cifra_gap_financiados(df_unico))
    return [c for c in cifras if c]


def cifras_vendedor(df_equipo, vendedor):
    mio = df_equipo[df_equipo["Nombre del Vendedor"] == vendedor]
    fin, n, pct = _conversion(mio)
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
    return cifras


def bloque_cifras(cifras):
    """Tabla con las cifras, en el lugar donde iban las tarjetas de KPI.

    En el Word se queda como una tabla normal. Al construir el PDF,
    pdf_util.construir_con_lateral la retira del flujo y la dibuja como la
    columna lateral de la portada. Por eso lleva las cifras como atributo.
    """
    from reportlab.platypus import Table
    filas = [[c["etiqueta"].title(), c["valor"], c["nota"]] for c in cifras]
    tabla = Table([["Cifra clave", "Valor", ""]] + filas)
    tabla._cifras_clave = cifras
    return tabla
