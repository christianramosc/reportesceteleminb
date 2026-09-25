# -*- coding: utf-8 -*-
"""Conclusiones y focos de atención de los cuatro reportes.

Por qué existe este módulo
--------------------------
Antes cada reporte redactaba sus conclusiones por su cuenta, y al revisarlas
con datos reales aparecieron los mismos vicios en todos:

1. Repetían lo que ya estaba en una tabla o en una tarjeta de KPI
   ("se dispersaron $5,384,222.22"), sin interpretarlo.
2. Coronaban un "mejor" y un "peor" aunque la diferencia fuera ruido: 26
   contra 28 solicitudes se reportaba como "Agosto el mes con más volumen".
3. Llamaban "mejor conversión" a lo que era un conteo de créditos.
4. Pedían al lector "validar" algo que el propio reporte ya sabía
   ("conviene validar si esto se traduce en créditos financiados").
5. Cerraban con recomendaciones que aplican a cualquier mes y cualquier
   equipo ("identificar qué hace bien para replicarlo").
6. Sacaban conclusiones de muestras de tres o cuatro casos sin advertirlo.
7. En el comparativo, las diez viñetas se imprimían DOS veces.

Aquí se concentra todo con criterios explícitos. Cada regla de abajo existe
para evitar uno de esos vicios, y los umbrales están en un solo lugar para
que los cuatro reportes digan lo mismo con los mismos datos.

Qué va en cada sección
----------------------
- Focos de atención: lo que pide una acción. Va en el resumen ejecutivo,
  arriba, porque es lo primero que alguien con poco tiempo debe leer.
- Conclusiones: la lectura de los resultados. Va al final.
Ningún texto aparece en las dos.
"""

import re

import pandas as pd

try:
    from . import estatus as _est
except ImportError:  # ejecución suelta (Colab)
    import estatus as _est

# ---------------------------------------------------------------- umbrales
# Si (máximo - mínimo) / promedio del volumen mensual queda por debajo de
# esto, el volumen se reporta como estable en vez de nombrar un mes "mejor".
UMBRAL_VOLUMEN_PCT = 10.0

# Dos tasas que difieren menos que esto se consideran iguales. Con los
# tamaños de muestra de un punto de venta, 3 puntos suele ser una o dos
# solicitudes de diferencia.
UMBRAL_PUNTOS = 3.0

# Diferencia que sí amerita señalarse como contraste entre personas o meses.
UMBRAL_CONTRASTE = 8.0

# Por debajo de este número de solicitudes, la tasa de un vendedor no se
# compara con nadie: con 2 solicitudes, una sola mueve la tasa 50 puntos.
MIN_SOLICITUDES_TASA = 5

# Mínimo de casos en cada grupo para comparar promedios entre estatus.
MIN_CASOS_GRUPO = 5

# Cambio mínimo, en solicitudes, para decir que un vendedor "subió" o "bajó".
MIN_CAMBIO_VENDEDOR = 3

# GAP: lo esperado es que TODAS las solicitudes y TODOS los créditos
# financiados lo lleven (100%). No hay "meta de 50%": presentarlo así hacía
# que quien llegaba a la mitad leyera que ya había cumplido.
# El 50% es solo el UMBRAL DE ALERTA: por debajo de la mitad, el reporte lo
# marca en rojo. Si la política cambia, se cambia aquí y nada más.
# Exactamente la mitad no es alerta.
UMBRAL_ALERTA_GAP = 50.0

# Rojo MG, solo para la etiqueta de "Alerta de GAP".
_ROJO_LLAMADO = "#E4002B"

COL_VEND = "Nombre del Vendedor"
COL_CAT = "Categoria"
COL_MONTO = "Monto Total a Financiar"
COL_GAP = "¿Tiene GAP?"


# ================================================================ utilidades
def _n(cantidad, singular, plural=None):
    """'1 solicitud', '3 solicitudes', '1 día', '4 días'.

    Plural del español: vocal + s; consonante + es. Para frases de varias
    palabras ("crédito financiado") se pasa el plural explícito.
    """
    cantidad = int(cantidad)
    if cantidad == 1:
        return f"{cantidad} {singular}"
    if plural is None:
        plural = singular + ("s" if singular[-1].lower() in "aeiouáéíóú" else "es")
    return f"{cantidad} {plural}"


def _lista(nombres):
    nombres = [str(n) for n in nombres]
    if len(nombres) <= 1:
        return "".join(nombres)
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _pct(parte, total):
    return parte / total * 100 if total else None


def _moneda(valor):
    """Montos redondeados: en una conclusión, $2,085,541.78 no aporta más
    que $2.09 millones y se lee peor."""
    if valor >= 1_000_000:
        return f"${valor / 1_000_000:,.2f} millones"
    return f"${valor:,.0f}"


def _es_nombre_de_persona(nombre):
    """Un asesor se registra con nombre y apellido. Una sola palabra
    ("Casa", "Piso", "Gerencia") suele ser una captura que no corresponde a
    una persona y distorsiona las comparaciones individuales."""
    return len(str(nombre).split()) >= 2


def _detalle_abiertas(conteo, abiertas):
    """"7 en APROBADO y 4 en CONTRAPROPUESTA", o "todas en APROBADO" si solo
    hay una categoría: repetir "3 solicitudes (3 en APROBADO)" no aporta."""
    if len(abiertas) == 1:
        return f"todas en {_est.etiqueta(abiertas[0]).upper()}"
    return _lista([f"{conteo[c]} en {_est.etiqueta(c).upper()}" for c in abiertas])


def _abiertas_presentes(conteo):
    """Categorías abiertas presentes en el periodo, en orden de catálogo."""
    return [c for c in _est.claves_por_grupo(_est.ABIERTA) if conteo.get(c, 0) > 0]


def _conteo_categorias(df):
    if COL_CAT not in df.columns:
        return {}
    return df[COL_CAT].value_counts().to_dict()


def mes_desde_hoja(nombre_hoja):
    """Número de mes a partir del nombre de la hoja ("JULIO 2026" -> 7)."""
    if not nombre_hoja:
        return None
    meses = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
             "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
    texto = str(nombre_hoja).upper()
    for i, mes in enumerate(meses, start=1):
        if re.search(rf"\b{mes}\b", texto):
            return i
    return None


# ========================================================= bloques comunes
def _foco_pendientes(df, modo, ctx=None):
    """Solicitudes que todavía pueden financiarse, con monto y a quién seguir.

    Es el foco más accionable de un reporte mensual, y antes no decía ni
    cuánto dinero representaban ni quién las tenía.
    """
    conteo = _conteo_categorias(df)
    abiertas = _abiertas_presentes(conteo)
    if not abiertas:
        return None

    mask = df[COL_CAT].isin(abiertas)
    n_abiertas = int(mask.sum())
    detalle = _detalle_abiertas(conteo, abiertas)

    monto = ""
    if COL_MONTO in df.columns:
        valor = float(df.loc[mask, COL_MONTO].fillna(0).sum())
        if valor > 0:
            monto = f", por {_moneda(valor)} a financiar"

    if modo == "avance":
        verbo = "puede" if n_abiertas == 1 else "pueden"
        if ctx is None:
            # Fecha de corte incoherente con los datos: no se habla de "fin
            # de mes" porque el foco anterior acaba de advertir que ese mes
            # probablemente ya cerró.
            texto = (f"<b>Solicitudes abiertas:</b> {_n(n_abiertas, 'solicitud')} "
                     f"{'sigue' if n_abiertas == 1 else 'siguen'} sin dispersar "
                     f"({detalle}){monto}.")
        else:
            # Los días restantes no se repiten aquí: la portada del avance ya
            # los muestra en el encabezado y en la introducción.
            texto = (f"<b>Por cerrar antes de fin de mes:</b> "
                     f"{_n(n_abiertas, 'solicitud')} todavía {verbo} financiarse "
                     f"({detalle}){monto}.")
    else:
        verbo = "quedó" if n_abiertas == 1 else "quedaron"
        texto = (f"<b>Sin dispersar al cierre:</b> {_n(n_abiertas, 'solicitud')} "
                 f"{verbo} abierta{'s' if n_abiertas != 1 else ''} ({detalle}){monto}. "
                 f"Pasan al siguiente mes si siguen vigentes.")

    if COL_VEND in df.columns:
        por_vend = df.loc[mask, COL_VEND].value_counts()
        if len(por_vend) == 1:
            texto += f" Todas son de {por_vend.index[0]}."
        elif por_vend.iloc[0] >= 2:
            top = por_vend[por_vend >= 2].head(3)
            texto += (" Se concentran en " +
                      _lista([f"{v} ({int(n)})" for v, n in top.items()]) + ".")
    return texto


def _foco_rechazo_vs_financiado(df):
    """Diferencias entre rechazadas y financiadas, solo con muestra suficiente.

    La versión anterior afirmaba que un enganche bajo "podría estar asociado
    al rechazo" comparando 9 contra 6 casos. Aquí se exige un mínimo por
    grupo y se dice explícitamente cuántos casos respaldan la cifra.
    """
    focos = []
    conteo = _conteo_categorias(df)
    n_rech, n_fin = conteo.get("RECHAZADO", 0), conteo.get("FINANCIADO", 0)
    if n_rech < MIN_CASOS_GRUPO or n_fin < MIN_CASOS_GRUPO:
        return focos

    rech = df[df[COL_CAT] == "RECHAZADO"]
    fin = df[df[COL_CAT] == "FINANCIADO"]

    if {"Enganche", "Precio Venta (c/IVA)"}.issubset(df.columns):
        def _eng(g):
            base = g["Precio Venta (c/IVA)"].replace(0, pd.NA)
            return (g["Enganche"] / base * 100).dropna().astype(float).mean()
        e_rech, e_fin = _eng(rech), _eng(fin)
        if pd.notna(e_rech) and pd.notna(e_fin) and e_fin - e_rech >= UMBRAL_PUNTOS:
            focos.append(
                f"<b>Enganche en rechazadas:</b> las solicitudes rechazadas dieron en "
                f"promedio {e_rech:.1f}% de enganche; las financiadas, {e_fin:.1f}%. "
                f"Con {n_rech} y {n_fin} casos es una señal a vigilar, no una causa "
                f"demostrada.")

    if COL_GAP in df.columns:
        g_rech = int((rech[COL_GAP] == "SI").sum())
        g_fin = int((fin[COL_GAP] == "SI").sum())
        p_rech, p_fin = _pct(g_rech, n_rech), _pct(g_fin, n_fin)
        if p_rech is not None and p_fin is not None and p_rech - p_fin >= 15:
            focos.append(
                f"<b>GAP en solicitudes que no se financian:</b> {g_rech} de {n_rech} "
                f"rechazadas llevaban GAP, contra {g_fin} de {n_fin} financiadas. Buena "
                f"parte del GAP que se ofrece se pierde junto con la solicitud.")
    return focos


def _foco_datos(df, resumen=None):
    """Problemas de captura que distorsionan el propio reporte."""
    focos = []
    if COL_VEND in df.columns:
        raros = df[COL_VEND].dropna()
        raros = raros[~raros.map(_es_nombre_de_persona)].value_counts()
        for nombre, n in raros.items():
            focos.append(
                f"<b>Vendedor por revisar:</b> “{nombre}” aparece como vendedor "
                f"({_n(n, 'solicitud')}) y no parece el nombre de un asesor. Si es "
                f"venta de piso o una captura genérica, conviene registrarla aparte: "
                f"hoy se mezcla con el desempeño de las personas.")
    incompletas = (resumen or {}).get("incompletas") or 0
    if incompletas:
        focos.append(
            f"<b>Datos incompletos:</b> {_n(incompletas, 'solicitud')} "
            f"{'tiene' if incompletas == 1 else 'tienen'} marca, vehículo o monto sin "
            f"capturar, y {'queda' if incompletas == 1 else 'quedan'} fuera de "
            f"algunos cálculos.")
    return focos


def _conclusion_conversion_vendedores(df, prefijo=""):
    """Conversión del equipo y contraste entre vendedores comparables.

    Sustituye dos viñetas anteriores:
      - "Carga de trabajo: X concentra más solicitudes; conviene validar si
        se traduce en créditos" -> ahora se responde con el dato.
      - "Mejor conversión: X lidera en créditos FINANCIADOS (2)" -> era un
        conteo, no una tasa. Ahora es una tasa y solo entre vendedores con
        volumen suficiente para compararse.
    """
    if not {COL_VEND, COL_CAT}.issubset(df.columns) or df.empty:
        return None

    personas = df[df[COL_VEND].map(_es_nombre_de_persona)]
    total, fin = len(df), int((df[COL_CAT] == "FINANCIADO").sum())
    tasa_eq = _pct(fin, total) or 0.0

    por_vend = personas.groupby(COL_VEND)[COL_CAT].agg(
        total="size", fin=lambda s: int((s == "FINANCIADO").sum()))
    por_vend["tasa"] = por_vend["fin"] / por_vend["total"] * 100
    elegibles = por_vend[por_vend["total"] >= MIN_SOLICITUDES_TASA]

    texto = (f"<b>Conversión{prefijo}:</b> el equipo ha financiado {tasa_eq:.0f}% de sus "
             f"solicitudes ({fin} de {total})." if prefijo else
             f"<b>Conversión:</b> el equipo financió {tasa_eq:.0f}% de sus solicitudes "
             f"({fin} de {total}).")

    if len(elegibles) >= 2:
        mejor = elegibles["tasa"].idxmax()
        peor = elegibles["tasa"].idxmin()
        t_mejor, t_peor = elegibles.loc[mejor, "tasa"], elegibles.loc[peor, "tasa"]
        top = por_vend["total"].idxmax()
        if t_mejor - t_peor >= UMBRAL_CONTRASTE:
            # Si quien menos convierte es también quien más solicitudes
            # ingresa, esa es la lectura importante: mucho volumen que no se
            # traduce en crédito. Antes el reporte la dejaba como pregunta.
            aclaracion = (", pese a ser quien más solicitudes ingresó"
                          if peor == top else "")
            texto += (f" Entre quienes tienen al menos {MIN_SOLICITUDES_TASA} solicitudes, "
                      f"{mejor} convierte {t_mejor:.0f}% "
                      f"({int(elegibles.loc[mejor, 'fin'])} de "
                      f"{int(elegibles.loc[mejor, 'total'])}) y {peor} {t_peor:.0f}% "
                      f"({int(elegibles.loc[peor, 'fin'])} de "
                      f"{int(elegibles.loc[peor, 'total'])}){aclaracion}.")
        else:
            texto += (f" Entre quienes tienen al menos {MIN_SOLICITUDES_TASA} solicitudes "
                      f"las tasas son parejas, de {t_peor:.0f}% a {t_mejor:.0f}%.")

        # Quien más volumen trae, si convierte claramente por debajo y no
        # quedó ya nombrado arriba.
        if top in elegibles.index and top not in (mejor, peor):
            t_top = elegibles.loc[top, "tasa"]
            if tasa_eq - t_top >= UMBRAL_CONTRASTE:
                texto += (f" {top}, con el mayor volumen ({int(por_vend.loc[top, 'total'])}), "
                          f"convierte por debajo del equipo ({t_top:.0f}%).")
    elif len(elegibles) == 1:
        v = elegibles.index[0]
        texto += (f" Solo {v} tiene {MIN_SOLICITUDES_TASA} o más solicitudes "
                  f"({elegibles.loc[v, 'tasa']:.0f}% de conversión); con menos casos, "
                  f"la tasa individual no es comparable.")
    return texto


def _conclusion_gap(df, prefijo=""):
    """GAP efectivamente vendido: el colocado en créditos financiados."""
    if not {COL_GAP, COL_CAT}.issubset(df.columns):
        return None
    fin = df[df[COL_CAT] == "FINANCIADO"]
    if fin.empty:
        return None
    n_fin = len(fin)
    n_gap = int((fin[COL_GAP] == "SI").sum())
    texto = (f"<b>GAP{prefijo}:</b> {n_gap} de {_n(n_fin, 'crédito financiado', 'créditos financiados')} "
             f"{'lleva' if n_gap == 1 else 'llevan'} GAP ({_pct(n_gap, n_fin):.0f}%).")

    # Solo se nombra a alguien si colocó GAP en 2 o más créditos: con uno
    # solo, "destaca" es una exageración.
    if COL_VEND in fin.columns and n_gap:
        por_vend = fin[fin[COL_GAP] == "SI"][COL_VEND].value_counts()
        por_vend = por_vend[por_vend.index.map(_es_nombre_de_persona)]
        if not por_vend.empty and por_vend.iloc[0] >= 2:
            lideres = por_vend[por_vend == por_vend.iloc[0]].index.tolist()
            texto += (f" {_lista(lideres)} {'suman' if len(lideres) > 1 else 'suma'} "
                      f"{int(por_vend.iloc[0])} cada uno." if len(lideres) > 1 else
                      f" {lideres[0]} colocó {int(por_vend.iloc[0])} de ellos.")
    return texto


# ================================================================ mensuales
def focos_y_conclusiones_mensual(df, modo, resumen=None, ctx=None, hoja=None):
    """Focos y conclusiones del Avance Preliminar ("avance") o del Resumen
    Mensual ("cierre").

    Devuelve (focos, conclusiones): dos listas sin textos en común.
    """
    focos, conclusiones = [], []

    # --- Coherencia entre fecha de corte y mes de los datos (solo avance).
    # Correr el avance sobre un mes ya cerrado sin mover la fecha de corte
    # producía "quedan 10 días para el cierre" de un mes que terminó hace
    # semanas. Si no coinciden, se advierte y no se habla de días restantes.
    ctx_util = ctx
    if modo == "avance" and ctx:
        mes_datos = mes_desde_hoja(hoja)
        mes_corte = ctx["fecha_corte"].month if ctx.get("fecha_corte") else None
        if mes_datos and mes_corte and mes_datos != mes_corte:
            nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                       "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            focos.append(
                f"<b>Revisa la fecha de corte:</b> los datos son de "
                f"{nombres[mes_datos - 1]}, pero la fecha de corte es el "
                f"{ctx['dia_actual']} de {nombres[mes_corte - 1]}. Si el mes ya "
                f"cerró, el reporte que corresponde es el Resumen Mensual; los "
                f"días restantes no se calculan porque no aplicarían.")
            ctx_util = None

    pendientes = _foco_pendientes(df, modo, ctx_util)
    if pendientes:
        focos.append(pendientes)
    focos.extend(_foco_rechazo_vs_financiado(df))
    focos.extend(_foco_datos(df, resumen))

    prefijo = " a la fecha" if modo == "avance" else ""
    conv = _conclusion_conversion_vendedores(df, prefijo)
    if conv:
        conclusiones.append(conv)
    # Si el foco de "GAP en solicitudes que no se financian" ya salió, ese
    # texto trae el mismo dato (X de Y financiadas con GAP). Repetirlo aquí
    # es justo lo que este módulo busca evitar.
    if not any("GAP en solicitudes que no se financian" in f for f in focos):
        gap = _conclusion_gap(df, prefijo)
        if gap:
            conclusiones.append(gap)

    if not conclusiones:
        conclusiones.append(
            "No hay suficientes datos para una lectura automática: revisa que el "
            "archivo traiga STATUS, Nombre del Vendedor y Monto Total a Financiar.")
    return focos, conclusiones


# ============================================================== comparativo
def _participacion(tabla_comp, columna):
    if columna not in tabla_comp.columns:
        return None
    return tabla_comp[columna] / tabla_comp["Total"].replace(0, pd.NA) * 100


def lectura_y_conclusiones_comparativo(tabla_comp, orden_meses, df_combinado):
    """Devuelve (lectura, conclusiones) del comparativo, sin textos en común.

    - Lectura del periodo (resumen ejecutivo): qué pasó con volumen,
      conversión y GAP.
    - Conclusiones (al final): qué implica, y a quién mirar.
    Antes eran la MISMA lista impresa dos veces.
    """
    lectura, conclusiones = [], []
    meses = [str(m).title() for m in orden_meses]
    n_meses = len(meses)

    if n_meses == 1:
        lectura.append(
            f"<b>Un solo mes:</b> el reporte solo incluye {meses[0]}, así que todavía "
            f"no hay evolución que comparar.")

    # ---------------------------------------------------------- volumen
    if n_meses >= 2 and "Total" in tabla_comp.columns:
        tot = tabla_comp["Total"].astype(float)
        dispersion = (tot.max() - tot.min()) / tot.mean() * 100 if tot.mean() else 0
        if dispersion < UMBRAL_VOLUMEN_PCT:
            lectura.append(
                f"<b>Volumen estable:</b> entre {int(tot.min())} y {int(tot.max())} "
                f"solicitudes por mes. La diferencia no es suficiente para hablar de "
                f"un mes mejor que otro.")
        else:
            cambio = _pct(tot.iloc[-1] - tot.iloc[0], tot.iloc[0])
            direccion = "creció" if (cambio or 0) > 0 else "cayó"
            lectura.append(
                f"<b>Volumen:</b> de {int(tot.iloc[0])} solicitudes en {meses[0]} a "
                f"{int(tot.iloc[-1])} en {meses[-1]} ({direccion} {abs(cambio or 0):.0f}%). "
                f"El mes más alto fue {tot.idxmax()} ({int(tot.max())}) y el más bajo, "
                f"{tot.idxmin()} ({int(tot.min())}).")

    # -------------------------------------------------------- conversión
    # En vez de "conviene revisar si se debió al seguimiento o a la calidad
    # de las solicitudes", se mira qué cambió en el mes de menor conversión:
    # si subió el rechazo, o si se acumularon abiertas sin dispersar.
    if n_meses >= 2 and "% Financiado" in tabla_comp.columns:
        conv = tabla_comp["% Financiado"].astype(float)
        if conv.max() - conv.min() < UMBRAL_PUNTOS:
            lectura.append(
                f"<b>Conversión pareja:</b> entre {conv.min():.1f}% y {conv.max():.1f}% "
                f"de las solicitudes se financiaron cada mes.")
        else:
            peor = conv.idxmin()
            otros = conv.drop(peor)
            texto = (f"<b>Conversión:</b> {peor} fue el mes más débil, con "
                     f"{conv[peor]:.1f}% financiado contra "
                     f"{otros.min():.1f}–{otros.max():.1f}% del resto."
                     if len(otros) > 1 else
                     f"<b>Conversión:</b> {peor} fue el mes más débil, con "
                     f"{conv[peor]:.1f}% financiado contra {otros.iloc[0]:.1f}% de "
                     f"{otros.index[0]}.")

            rech = _participacion(tabla_comp, "Rechazado")
            cols_abiertas = [c for c in tabla_comp.columns
                             if c in ("Aprobado", "Contrapropuesta", "En trámite")]
            abiertas = (tabla_comp[cols_abiertas].sum(axis=1)
                        / tabla_comp["Total"].replace(0, pd.NA) * 100) if cols_abiertas else None

            d_rech = (rech[peor] - rech.drop(peor).mean()) if rech is not None else 0
            d_abi = (abiertas[peor] - abiertas.drop(peor).mean()) if abiertas is not None else 0
            if rech is not None and d_rech >= UMBRAL_CONTRASTE and d_rech >= d_abi:
                texto += (f" Lo explica el rechazo: {rech[peor]:.0f}% de sus solicitudes "
                          f"se rechazaron, contra "
                          f"{rech.drop(peor).min():.0f}–{rech.drop(peor).max():.0f}% en los "
                          f"demás meses." if len(rech.drop(peor)) > 1 else
                          f" Lo explica el rechazo: {rech[peor]:.0f}% de sus solicitudes "
                          f"se rechazaron, contra {rech.drop(peor).iloc[0]:.0f}%.")
            elif abiertas is not None and d_abi >= UMBRAL_CONTRASTE:
                texto += (f" Lo explica el seguimiento: {abiertas[peor]:.0f}% de sus "
                          f"solicitudes quedaron aprobadas o en trámite sin dispersar, "
                          f"más que en los demás meses.")
            else:
                texto += (" No coincide con un aumento claro de rechazos ni de "
                          "solicitudes sin dispersar.")
            lectura.append(texto)

    # --------------------------------------------------------------- GAP
    # Una sola viñeta en vez de cuatro. La medida principal es el GAP dentro
    # de créditos financiados; el general solo se usa para explicar la
    # diferencia entre ambos.
    if "% GAP Financiado" in tabla_comp.columns and tabla_comp["% GAP Financiado"].notna().any():
        gfin = tabla_comp["% GAP Financiado"].dropna().astype(float)
        if n_meses >= 2 and gfin.max() - gfin.min() >= UMBRAL_PUNTOS:
            texto = (f"<b>GAP vendido:</b> dentro de los créditos financiados, el GAP "
                     f"fue de {gfin.min():.0f}% ({gfin.idxmin()}) a {gfin.max():.0f}% "
                     f"({gfin.idxmax()}).")
        else:
            texto = (f"<b>GAP vendido:</b> alrededor de {gfin.mean():.0f}% de los "
                     f"créditos financiados llevan GAP.")
        if "% GAP" in tabla_comp.columns:
            ggen = tabla_comp["% GAP"].dropna().astype(float)
            if not ggen.empty and ggen.mean() - gfin.mean() >= 10:
                texto += (f" Sobre todas las solicitudes la cifra sube a "
                          f"{ggen.mean():.0f}%: una parte del GAP se coloca en "
                          f"solicitudes que no llegan a financiarse.")
        lectura.append(texto)

    # ======================================================== conclusiones
    tiene_vend = COL_VEND in df_combinado.columns and "Mes" in df_combinado.columns

    # Quién subió y quién bajó: la historia que la viñeta de "vendedor con
    # más actividad" escondía. En junio–agosto la más activa del periodo era
    # también la que más cayó.
    if tiene_vend and n_meses >= 2:
        piv = pd.crosstab(df_combinado[COL_VEND], df_combinado["Mes"])
        cols = [m for m in orden_meses if m in piv.columns]
        if len(cols) >= 2:
            piv = piv[cols]
            piv = piv[piv.index.map(_es_nombre_de_persona)]
            cambio = piv[cols[-1]] - piv[cols[0]]
            subio = cambio[cambio >= MIN_CAMBIO_VENDEDOR].sort_values(ascending=False)
            bajo = cambio[cambio <= -MIN_CAMBIO_VENDEDOR].sort_values()
            partes = []
            for v in subio.index[:2]:
                partes.append(f"{v} pasó de {int(piv.loc[v, cols[0]])} a "
                              f"{int(piv.loc[v, cols[-1]])} solicitudes")
            for v in bajo.index[:2]:
                partes.append(f"{v} bajó de {int(piv.loc[v, cols[0]])} a "
                              f"{int(piv.loc[v, cols[-1]])}")
            if partes:
                conclusiones.append(
                    f"<b>Movimiento del equipo ({meses[0]} a {meses[-1]}):</b> "
                    f"{_lista(partes)}.")
            else:
                conclusiones.append(
                    f"<b>Movimiento del equipo:</b> ningún vendedor cambió su volumen en "
                    f"{MIN_CAMBIO_VENDEDOR} o más solicitudes entre {meses[0]} y {meses[-1]}.")

            # Ausencias: un vendedor con actividad que desaparece un mes.
            if len(cols) >= 3:
                ausentes = []
                for v in piv.index:
                    fila = piv.loc[v]
                    if fila.sum() >= MIN_CAMBIO_VENDEDOR:
                        vacios = [str(m).title() for m in cols if fila[m] == 0]
                        if vacios and len(vacios) < len(cols):
                            ausentes.append(f"{v} ({_lista(vacios)})")
                if ausentes:
                    conclusiones.append(
                        f"<b>Meses sin actividad:</b> {_lista(ausentes)} no "
                        f"{'registró' if len(ausentes) == 1 else 'registraron'} "
                        f"solicitudes. Conviene tenerlo presente al leer sus totales.")

    conv_vend = _conclusion_conversion_vendedores(df_combinado)
    if conv_vend:
        conclusiones.append(conv_vend.replace("<b>Conversión:</b>",
                                              "<b>Conversión en el periodo:</b>"))

    # Concentración: solo se menciona si de verdad es un riesgo.
    if COL_VEND in df_combinado.columns:
        personas = df_combinado[df_combinado[COL_VEND].map(_es_nombre_de_persona)]
        vc = personas[COL_VEND].value_counts()
        if len(vc) >= 3:
            p1 = vc.iloc[0] / len(df_combinado) * 100
            p2 = vc.iloc[:2].sum() / len(df_combinado) * 100
            if p1 >= 35 or p2 >= 60:
                conclusiones.append(
                    f"<b>Dependencia del volumen:</b> {vc.index[0]} aporta {p1:.0f}% de "
                    f"todas las solicitudes"
                    + (f" y, con {vc.index[1]}, {p2:.0f}%" if p2 >= 60 else "")
                    + ". Una ausencia ahí mueve el mes completo.")

    conclusiones.extend(_foco_datos(df_combinado))
    return lectura, conclusiones


# ========================================================== por vendedor
def _mensaje_gap(mio, n, fin):
    """Un solo mensaje de GAP por vendedor.

    Lo esperado es que todas las solicitudes y todos los créditos lleven GAP.
    Niveles, del más severo al más leve (se usa el más severo que aplique):
      1. Alerta de GAP (rojo): 0% en solicitudes, o menos de la mitad
         (UMBRAL_ALERTA_GAP) en créditos financiados.
      2. Oportunidad en GAP: entre 1% y menos de la mitad en solicitudes.
      3. Neutral: de la mitad hacia arriba, pero no en todas. Dice cuántas
         quedaron sin GAP; ya no se presenta como "meta cumplida".
      4. GAP completo: todas las solicitudes y todos los créditos lo llevan.

    Lo que falta se cuenta contra el total, no contra la mitad: "a 3 de tus
    solicitudes les faltó", no "te faltó 1 para cumplir".

    Sin mínimo de casos: un crédito sin GAP es una venta perdida. Por eso
    cada mensaje lleva el conteo ("0 de 1").
    """
    g_sol = int((mio[COL_GAP] == "SI").sum())
    p_sol = _pct(g_sol, n) or 0.0
    fin_df = mio[mio[COL_CAT] == "FINANCIADO"]
    g_fin = int((fin_df[COL_GAP] == "SI").sum())
    p_fin = _pct(g_fin, fin) if fin else None
    esperado = "Lo esperado es que todas lo lleven."
    alerta = f"<font color='{_ROJO_LLAMADO}'><b>Alerta de GAP:</b></font>"

    falla_sol_cero = g_sol == 0
    falla_fin = p_fin is not None and p_fin < UMBRAL_ALERTA_GAP

    # ---- 1. Alerta
    if falla_sol_cero and falla_fin:
        creditos = "tu crédito financiado" if fin == 1 else f"tus {fin} créditos financiados"
        return (f"{alerta} ninguna de tus {_n(n, 'solicitud')} lleva GAP, y tampoco "
                f"{creditos}. {esperado} Para el próximo mes, ofrécelo en cada "
                f"solicitud desde la primera cotización y confírmalo antes de formalizar.")

    if falla_sol_cero:
        return (f"{alerta} ninguna de tus {_n(n, 'solicitud')} lleva GAP. {esperado} "
                f"Para el próximo mes, ofrécelo en cada solicitud desde la primera "
                f"cotización.")

    if falla_fin:
        if fin == 1:
            hecho = "tu único crédito financiado salió sin GAP (0 de 1)"
        elif g_fin == 0:
            hecho = f"ninguno de tus {fin} créditos financiados lleva GAP"
        else:
            hecho = (f"solo {g_fin} de tus {fin} créditos financiados "
                     f"{'lleva' if g_fin == 1 else 'llevan'} GAP ({p_fin:.0f}%)")
        texto = f"{alerta} {hecho}; lo esperado es que todos lo lleven."
        if p_sol >= UMBRAL_ALERTA_GAP:
            # Lo ofrece, pero se pierde en el camino: la acción es cuidar
            # que el GAP llegue hasta la dispersión, no ofrecerlo más.
            texto += (f" En solicitudes lo ofreciste en {g_sol} de {n}: el GAP se está "
                      f"perdiendo entre la solicitud y la dispersión. Confírmalo antes "
                      f"de formalizar cada crédito.")
        else:
            texto += (f" En solicitudes también es bajo ({g_sol} de {n}, {p_sol:.0f}%). "
                      f"Ofrécelo desde la cotización y confírmalo antes de formalizar "
                      f"cada crédito.")
        return texto

    sin_sol = n - g_sol
    detalle_fin = ""
    if fin:
        sin_fin = fin - g_fin
        detalle_fin = (f" En tus créditos financiados, {g_fin} de {fin} lo "
                       f"{'lleva' if g_fin == 1 else 'llevan'}"
                       + (f"; a {sin_fin} le{'s' if sin_fin != 1 else ''} faltó." if sin_fin else "."))

    # ---- 2. Oportunidad (menos de la mitad en solicitudes)
    if p_sol < UMBRAL_ALERTA_GAP:
        return (f"<b>Oportunidad en GAP:</b> {g_sol} de tus {_n(n, 'solicitud')} "
                f"{'lleva' if g_sol == 1 else 'llevan'} GAP ({p_sol:.0f}%); a {sin_sol} "
                f"le{'s' if sin_sol != 1 else ''} faltó. {esperado}{detalle_fin}")

    # ---- 4. Completo
    if sin_sol == 0 and (not fin or g_fin == fin):
        cierre = (f" y {'tu crédito financiado' if fin == 1 else f'tus {fin} créditos financiados'}"
                  if fin else "")
        return (f"<b>GAP completo:</b> todas tus solicitudes ({n}){cierre} llevan GAP.")

    # ---- 3. Neutral: de la mitad hacia arriba, sin llegar a todas
    texto = (f"<b>GAP:</b> {g_sol} de tus {_n(n, 'solicitud')} "
             f"{'lleva' if g_sol == 1 else 'llevan'} GAP ({p_sol:.0f}%)")
    texto += (f"; a {sin_sol} le{'s' if sin_sol != 1 else ''} faltó." if sin_sol else ".")
    if fin:
        texto += detalle_fin
    else:
        texto += " Aún no tienes créditos financiados."
    return texto


def conclusiones_vendedor(df, vendedor):
    """Conclusiones del reporte individual.

    Todas las comparaciones son contra la conversión REAL del equipo
    (financiados / solicitudes), no contra el promedio simple de las tasas
    de cada vendedor, y el GAP que se mide es el colocado en créditos
    financiados, igual que en los demás reportes.
    """
    conclusiones = []
    if not {COL_VEND, COL_CAT}.issubset(df.columns):
        return conclusiones

    mio = df[df[COL_VEND] == vendedor]
    n = len(mio)
    if not n:
        return conclusiones

    total_eq = len(df)
    fin_eq = int((df[COL_CAT] == "FINANCIADO").sum())
    tasa_eq = _pct(fin_eq, total_eq) or 0.0
    fin = int((mio[COL_CAT] == "FINANCIADO").sum())
    rech = int((mio[COL_CAT] == "RECHAZADO").sum())

    # --- Conversión
    if n < MIN_SOLICITUDES_TASA:
        conclusiones.append(
            f"<b>Conversión:</b> financiaste {fin} de {n} ({_pct(fin, n):.0f}%); el "
            f"equipo, {tasa_eq:.0f}%. Con {_n(n, 'solicitud')}, cada una mueve tu tasa "
            f"{100 / n:.0f} puntos, así que todavía no es una comparación justa.")
    else:
        tasa = _pct(fin, n)
        dif = tasa - tasa_eq
        if abs(dif) < UMBRAL_PUNTOS:
            conclusiones.append(
                f"<b>Conversión:</b> financiaste {fin} de {n} ({tasa:.0f}%), en línea "
                f"con el equipo ({tasa_eq:.0f}%).")
        elif dif > 0:
            conclusiones.append(
                f"<b>Fortaleza:</b> financiaste {fin} de {n} ({tasa:.0f}%), "
                f"{dif:.0f} puntos arriba del equipo ({tasa_eq:.0f}%).")
        else:
            conclusiones.append(
                f"<b>Área de oportunidad:</b> financiaste {fin} de {n} ({tasa:.0f}%), "
                f"{abs(dif):.0f} puntos abajo del equipo ({tasa_eq:.0f}%).")

    # --- Pendientes: lo único accionable para el siguiente mes.
    conteo = mio[COL_CAT].value_counts().to_dict()
    abiertas = _abiertas_presentes(conteo)
    if abiertas:
        n_ab = sum(conteo[c] for c in abiertas)
        detalle = _detalle_abiertas(conteo, abiertas)
        conclusiones.append(
            f"<b>Pendientes:</b> {'te queda' if n_ab == 1 else 'te quedan'} "
            f"{_n(n_ab, 'solicitud')} sin dispersar ({detalle}).")

    # --- GAP: lo esperado es el 100% (ver _mensaje_gap)
    if COL_GAP in df.columns:
        if _es_nombre_de_persona(vendedor):
            gap = _mensaje_gap(mio, n, fin)
        else:
            # Capturas genéricas ("Casa"): no reciben llamado, porque no hay
            # a quién dirigirlo. Se deja solo el dato.
            g = int((mio[COL_GAP] == "SI").sum())
            gap = (f"<b>GAP:</b> {g} de {_n(n, 'solicitud')} con GAP "
                   f"({_pct(g, n):.0f}%).")
        # Primera viñeta: es el indicador que más importa a la operación.
        conclusiones.insert(0, gap)

    # --- Rechazo: solo si es claramente mayor que el del equipo.
    rech_eq = _pct(int((df[COL_CAT] == "RECHAZADO").sum()), total_eq) or 0.0
    if n >= MIN_SOLICITUDES_TASA and rech:
        p_rech = _pct(rech, n)
        if p_rech - rech_eq >= UMBRAL_CONTRASTE:
            conclusiones.append(
                f"<b>Rechazos:</b> {rech} de tus {n} solicitudes ({p_rech:.0f}%), "
                f"por encima del equipo ({rech_eq:.0f}%).")
    return conclusiones
