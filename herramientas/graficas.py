"""Gráficas de los cuatro reportes, con un solo criterio visual.

Criterios (tomados de "Storytelling con datos", C. Nussbaumer Knaflic):

1. Sin gráficas circulares ni de anillo: los estatus se comparan con barras.
2. El dato va escrito junto a la barra o el punto; por eso no hay eje de
   valores (sería el mismo dato dos veces).
3. El color no decora. Casi todo es gris y solo lleva color lo que nombra el
   titular de la gráfica.
4. Cuatro grupos de estatus en vez de un color por estatus:
       Financiado · Aprobado · En trámite · No procedió
5. Un solo significado por color:
       azul Inbursa = lo que se quiere destacar (el resultado)
       rojo MG      = alerta (por debajo del umbral, o lo que se perdió
                      cuando el titular habla de eso)
       gris         = contexto
6. Nada de texto inclinado: si los nombres son largos, las barras van
   horizontales.
7. Las leyendas son palabras del color de su serie, junto al título o al
   final de la línea, no un recuadro aparte.
8. Una tasa calculada con muy pocos casos se dibuja atenuada y lo dice
   ("base pequeña"), para que un "1 de 1 (100%)" no se lea como logro.
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import conclusiones as _c
from . import estatus as _est
from . import hallazgos as _h
from . import metricas as _metricas

# ------------------------------------------------------------------ paleta
AZUL = "#191970"          # énfasis: el resultado que nombra el titular
AZUL_MEDIO = "#8E9BD6"    # Aprobado: casi resultado
GRIS_BARRA = "#C9CDD6"    # contexto
GRIS_FONDO = "#E9EBEF"    # el total detrás de una parte
GRIS_OSCURO = "#868C98"   # No procedió
ROJO = "#E4002B"          # alerta, y nada más
TEXTO = "#1F2937"
TEXTO_SEC = "#6B7280"

FIN, APR, TRA, PER = "FINANCIADO", "APROBADO", "TRAMITE", "PERDIDA"
GRUPOS = [FIN, APR, TRA, PER]
ETIQUETA_GRUPO = {FIN: "Financiado", APR: "Aprobado", TRA: "En trámite", PER: "No procedió"}
COLOR_GRUPO = {FIN: AZUL, APR: AZUL_MEDIO, TRA: GRIS_BARRA, PER: GRIS_OSCURO}

# Con menos casos que esto, una tasa no se compara con nadie.
BASE_MINIMA = _c.MIN_SOLICITUDES_TASA
# En créditos financiados los números son chicos: 1 o 2 no sostienen un %.
BASE_MINIMA_FINANCIADOS = 3

COL_VEND, COL_CAT, COL_GAP = "Nombre del Vendedor", "Categoria", "¿Tiene GAP?"
COL_MONTO = "Monto Total a Financiar"


def grupo_de(clave):
    """Financiado, Aprobado, En trámite o No procedió."""
    clave = str(clave).strip().upper()
    if clave in (FIN, APR):
        return clave
    if _est.GRUPO_CATEGORIA.get(clave, _est.ABIERTA) == _est.CERRADA_NEGATIVA:
        return PER
    return TRA


def conteo_por_grupo(categorias):
    """Serie de categorías -> conteo por grupo, en el orden de GRUPOS."""
    conteo = categorias.dropna().map(grupo_de).value_counts()
    return conteo.reindex(GRUPOS).fillna(0).astype(int)


# --------------------------------------------------------------- utilidades
def _guardar(fig, guardar_como):
    if guardar_como:
        carpeta = os.path.dirname(guardar_como)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        _h.ajustar_titulos(fig)
        fig.savefig(guardar_como, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return guardar_como


def titular(ax, hallazgo, descripcion, leyenda=None):
    """Hallazgo en negritas, la descripción en gris y, si se pasa, la leyenda
    como palabras de color en un renglón: [(texto, color), ...].

    Todo se coloca en puntos sobre el borde superior de la gráfica (no en
    fracción del eje), para que quede igual en una gráfica alta que en una
    barra de un solo renglón."""
    ax.set_title(hallazgo, loc="left", fontsize=12.5, fontweight="bold",
                 pad=42 if leyenda else 24, color=TEXTO)
    ax.annotate(descripcion, xy=(0, 1), xycoords="axes fraction",
                xytext=(0, 25 if leyenda else 7), textcoords="offset points",
                fontsize=9, color=TEXTO_SEC, ha="left", va="bottom")
    if not leyenda:
        return
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    x_pt = 0.0
    for texto, color in leyenda:
        t = ax.annotate(texto, xy=(0, 1), xycoords="axes fraction", xytext=(x_pt, 7),
                        textcoords="offset points", fontsize=9, fontweight="bold",
                        color=color, ha="left", va="bottom")
        x_pt += t.get_window_extent(renderer).width * 72 / fig.dpi + 16


def _sin_eje(ax, eje):
    """Quita el eje de valores: cada barra ya lleva su número."""
    if eje == "x":
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    else:
        ax.yaxis.set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="x", length=0)


def _barras_h(ax, nombres, valores, colores, textos, colores_texto=None, margen=1.3):
    """Barras horizontales con su dato escrito al final de cada una."""
    y = np.arange(len(valores))
    ax.barh(y, valores, color=colores, height=0.66)
    tope = max(list(valores) + [1])
    colores_texto = colores_texto or [TEXTO] * len(valores)
    for i, (v, t, c) in enumerate(zip(valores, textos, colores_texto)):
        ax.text(v + tope * 0.015, i, t, va="center", fontsize=9, color=c,
                fontweight="bold" if c in (AZUL, ROJO) else "normal")
    ax.set_yticks(y)
    ax.set_yticklabels(nombres)
    ax.set_xlim(0, tope * margen)
    ax.spines["left"].set_color(GRIS_BARRA)
    _sin_eje(ax, "x")


def _resaltar_nombres(ax, nombres_destacados, color=AZUL):
    for etiqueta in ax.get_yticklabels():
        if etiqueta.get_text() in nombres_destacados:
            etiqueta.set_fontweight("bold")
            etiqueta.set_color(color)


def _alto(n, por_fila=0.46, minimo=2.6):
    return max(minimo, n * por_fila + 0.9)


def _nota_excluidos(excluidos):
    return " · sin capturas genéricas" if excluidos else ""


def _separar(posiciones, minimo):
    """Mueve lo mínimo necesario una lista de alturas para que ninguna quede
    a menos de `minimo` de otra. Conserva el orden original."""
    orden = sorted(range(len(posiciones)), key=lambda i: posiciones[i])
    nuevas = list(posiciones)
    for _ in range(60):
        movio = False
        for a, b in zip(orden, orden[1:]):
            falta = minimo - (nuevas[b] - nuevas[a])
            if falta > 1e-9:
                nuevas[a] -= falta / 2
                nuevas[b] += falta / 2
                movio = True
        if not movio:
            break
    return nuevas


# ======================================================== Resumen y Avance
def grafica_status(df, guardar_como=None):
    """Solicitudes por estatus. Solo lleva color el estatus que nombra el
    titular: azul si es un resultado, rojo si es una pérdida."""
    if COL_CAT in df.columns:
        conteo_claves = df[COL_CAT].value_counts()
    elif "STATUS" in df.columns:
        conteo_claves = df["STATUS"].value_counts()
    else:
        return None
    if conteo_claves.empty:
        return None
    conteo_claves = conteo_claves.sort_values(ascending=True, kind="stable")
    total = int(conteo_claves.sum())
    tope = conteo_claves.max()

    colores, colores_texto = [], []
    for clave, n in conteo_claves.items():
        if n == tope:
            c = ROJO if grupo_de(clave) == PER else AZUL
        else:
            c = GRIS_BARRA
        colores.append(c)
        colores_texto.append(c if c != GRIS_BARRA else TEXTO_SEC)

    nombres = [_est.etiqueta(c) for c in conteo_claves.index]
    fig, ax = plt.subplots(figsize=(8, _alto(len(conteo_claves), 0.42)))
    _barras_h(ax, nombres, conteo_claves.values, colores,
              [f"{int(n)}  ({n / total * 100:.0f}%)" for n in conteo_claves.values],
              colores_texto)
    lideres = [n for n, v in zip(nombres, conteo_claves.values) if v == tope]
    _resaltar_nombres(ax, lideres, colores[-1])
    titular(ax, _h.estatus_mayoritario(pd.Series(conteo_claves.values, index=nombres)),
            f"Solicitudes por estatus de la bitácora · {total} en total")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_mezcla_cierre(df, guardar_como=None):
    """Una sola barra al 100% con los cuatro grupos. Sustituye a la dona."""
    if COL_CAT not in df.columns or df.empty:
        return None
    conteo = conteo_por_grupo(df[COL_CAT])
    total = int(conteo.sum())
    if not total:
        return None

    fig, ax = plt.subplots(figsize=(8, 1.55))
    izquierda = 0.0
    for g in GRUPOS:
        n = int(conteo[g])
        if not n:
            continue
        pct = n / total * 100
        ax.barh([0], [pct], left=izquierda, color=COLOR_GRUPO[g], height=0.6,
                edgecolor="white", linewidth=1.5)
        if pct >= 7:
            ax.text(izquierda + pct / 2, 0, f"{pct:.0f}%\n{n}", ha="center", va="center",
                    fontsize=9, fontweight="bold", linespacing=1.15,
                    color="white" if g in (FIN, PER) else TEXTO)
        izquierda += pct
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.45, 0.45)
    ax.axis("off")
    titular(ax, _h.mezcla_por_grupo(conteo),
            f"Las {total} solicitudes, agrupadas por cómo quedaron",
            leyenda=[(ETIQUETA_GRUPO[g], COLOR_GRUPO[g] if g != TRA else TEXTO_SEC)
                     for g in GRUPOS if conteo[g]])
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_vendedores(df, guardar_como=None, sufijo=""):
    """Solicitudes por vendedor: gris, y en azul quien nombra el titular."""
    if COL_VEND not in df.columns:
        return None
    total_equipo = len(df)
    df, excluidos = _h.solo_personas(df)
    conteo = df[COL_VEND].value_counts().sort_values(ascending=True, kind="stable")
    if conteo.empty:
        return None
    tope = conteo.max()
    colores = [AZUL if v == tope else GRIS_BARRA for v in conteo.values]

    fig, ax = plt.subplots(figsize=(8, _alto(len(conteo))))
    _barras_h(ax, list(conteo.index), conteo.values, colores,
              [str(int(v)) for v in conteo.values],
              [AZUL if v == tope else TEXTO_SEC for v in conteo.values], margen=1.15)
    _resaltar_nombres(ax, [n for n, v in conteo.items() if v == tope])
    titular(ax, _h.vendedor_con_mas(conteo, total_equipo),
            f"Solicitudes ingresadas por vendedor{sufijo}" + _nota_excluidos(excluidos))
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_vendedor_status(df, guardar_como=None):
    """Cómo cerró cada vendedor, al 100% y en cuatro grupos, ordenado por
    conversión. Antes eran barras apiladas con un segmento por estatus: con
    diez segmentos solo se podía comparar el primero."""
    if not {COL_VEND, COL_CAT}.issubset(df.columns):
        return None
    df, excluidos = _h.solo_personas(df)
    if df.empty:
        return None
    hallazgo = _h.vendedor_mejor_conversion(pd.crosstab(df[COL_VEND], df[COL_CAT]))
    pivote = pd.crosstab(df[COL_VEND], df[COL_CAT].map(grupo_de))
    pivote = pivote.reindex(columns=GRUPOS).fillna(0).astype(int)
    totales = pivote.sum(axis=1)
    pct = pivote.div(totales.replace(0, np.nan), axis=0).fillna(0) * 100
    # Los de base pequeña van abajo, juntos: su % no se compara con el resto.
    chicos = totales < BASE_MINIMA
    orden = sorted(pct.index, key=lambda v: (not chicos[v], pct.loc[v, FIN], totales[v]))
    pct, totales = pct.loc[orden], totales.loc[orden]
    elegibles = pct.loc[~chicos.loc[orden], FIN]
    mejor = elegibles.max() if len(elegibles) >= 2 else None

    fig, ax = plt.subplots(figsize=(9, _alto(len(pct), 0.5)))
    y = np.arange(len(pct))
    izquierda = np.zeros(len(pct))
    for g in GRUPOS:
        alphas = [0.4 if chicos[v] else 1.0 for v in pct.index]
        barras = ax.barh(y, pct[g].values, left=izquierda, color=COLOR_GRUPO[g],
                         height=0.66, edgecolor="white", linewidth=1.2)
        for barra, a in zip(barras, alphas):
            barra.set_alpha(a)
        izquierda += pct[g].values
    for i, v in enumerate(pct.index):
        p = pct.loc[v, FIN]
        if chicos[v]:
            texto, color, peso = f"{pivote.loc[v, FIN]} de {totales[v]} · base pequeña", TEXTO_SEC, "normal"
        else:
            texto = f"{p:.0f}% financiado"
            destaca = mejor is not None and p == mejor
            color, peso = (AZUL, "bold") if destaca else (TEXTO_SEC, "normal")
        ax.text(101.5, i, texto, va="center", fontsize=9, color=color, fontweight=peso)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{v}  ({totales[v]})" for v in pct.index])
    ax.set_xlim(0, 128)
    ax.spines["left"].set_visible(False)
    _sin_eje(ax, "x")
    titular(ax, hallazgo,
            "Cómo quedaron las solicitudes de cada vendedor (entre paréntesis, cuántas ingresó)"
            + _nota_excluidos(excluidos),
            leyenda=[(ETIQUETA_GRUPO[g], COLOR_GRUPO[g] if g != TRA else TEXTO_SEC)
                     for g in GRUPOS if pivote[g].sum()])
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_monto_por_vendedor(df, guardar_como=None):
    """Monto financiado de cada vendedor y, a continuación de la misma barra,
    lo aprobado que falta dispersar."""
    if not {COL_VEND, COL_CAT, COL_MONTO}.issubset(df.columns):
        return None
    df, excluidos = _h.solo_personas(df)
    fin = df[df[COL_CAT] == FIN].groupby(COL_VEND)[COL_MONTO].sum()
    apr = df[df[COL_CAT] == APR].groupby(COL_VEND)[COL_MONTO].sum()
    vendedores = sorted(set(fin.index) | set(apr.index),
                        key=lambda v: (fin.get(v, 0), apr.get(v, 0)))
    if not vendedores:
        return None
    v_fin = np.array([fin.get(v, 0) for v in vendedores], dtype=float)
    v_apr = np.array([apr.get(v, 0) for v in vendedores], dtype=float)
    tope = max((v_fin + v_apr).max(), 1)
    lider = v_fin.max()

    fig, ax = plt.subplots(figsize=(9, _alto(len(vendedores), 0.5)))
    y = np.arange(len(vendedores))
    ax.barh(y, v_fin, color=[AZUL if f == lider and f > 0 else "#5A5FA3" for f in v_fin], height=0.66)
    ax.barh(y, v_apr, left=v_fin, color=GRIS_BARRA, height=0.66, edgecolor="white", linewidth=1.2)
    for i, (f, a) in enumerate(zip(v_fin, v_apr)):
        partes = []
        if f:
            partes.append(f"{_h.monto_corto(f)} financiado")
        if a:
            partes.append(f"{_h.monto_corto(a)} por dispersar")
        ax.text(f + a + tope * 0.015, i, "  +  ".join(partes).replace("$", r"\$"), va="center", fontsize=8.5,
                color=AZUL if f == lider and f > 0 else TEXTO_SEC,
                fontweight="bold" if f == lider and f > 0 else "normal")
    ax.set_yticks(y)
    ax.set_yticklabels(vendedores)
    ax.set_xlim(0, tope * 1.62)
    ax.spines["left"].set_color(GRIS_BARRA)
    _sin_eje(ax, "x")
    _resaltar_nombres(ax, [v for v, f in zip(vendedores, v_fin) if f == lider and f > 0])
    titular(ax, _h.monto_top_vendedor(pd.Series(v_fin, index=vendedores)),
            "Monto por vendedor" + _nota_excluidos(excluidos),
            leyenda=[("Financiado (dispersado)", AZUL), ("Aprobado (sin dispersar)", TEXTO_SEC)])
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_modelos(df, guardar_como=None, sufijo=""):
    if "Vehículo" not in df.columns:
        return None
    completo = df["Vehículo"].dropna().value_counts()
    if completo.empty:
        return None
    TOP_N = 10
    conteo = completo.head(TOP_N).sort_values(ascending=True, kind="stable")
    tope = conteo.max()

    fig, ax = plt.subplots(figsize=(8, _alto(len(conteo), 0.4)))
    _barras_h(ax, list(conteo.index), conteo.values,
              [AZUL if v == tope else GRIS_BARRA for v in conteo.values],
              [str(int(v)) for v in conteo.values],
              [AZUL if v == tope else TEXTO_SEC for v in conteo.values], margen=1.12)
    _resaltar_nombres(ax, [n for n, v in conteo.items() if v == tope])
    titular(ax, _h.modelo_lider(completo),
            f"Modelos con más solicitudes{sufijo} (top {min(TOP_N, len(completo))})")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def _linea_alerta_gap(ax, y_texto):
    u = _c.UMBRAL_ALERTA_GAP
    ax.axvline(u, color=ROJO, linestyle=(0, (4, 3)), linewidth=0.9, zorder=0)
    ax.text(u, y_texto, " alerta: menos de la mitad", color=ROJO, fontsize=8,
            ha="left", va="bottom")


def grafica_gap_por_categoria(df, guardar_como=None):
    """% con GAP en cada estatus, en barras horizontales. Azul: financiado
    (el GAP que sí se vendió). Rojo: por debajo de la mitad."""
    if not {COL_CAT, COL_GAP}.issubset(df.columns):
        return None
    con = (df[COL_GAP] == "SI").groupby(df[COL_CAT]).agg(["sum", "size"])
    con = con.reindex([c for c in _est.ORDEN_CATEGORIAS if c in con.index])
    if con.empty:
        return None
    con["pct"] = con["sum"] / con["size"] * 100
    pct_titulo = con["pct"].copy()
    con = con.iloc[::-1]       # el catálogo se lee de arriba hacia abajo

    colores, textos, colores_texto = [], [], []
    for clave, fila in con.iterrows():
        chico = fila["size"] < BASE_MINIMA
        if chico:
            c = GRIS_FONDO
        elif fila["pct"] < _c.UMBRAL_ALERTA_GAP:
            c = ROJO
        elif clave == FIN:
            c = AZUL
        else:
            c = GRIS_BARRA
        colores.append(c)
        textos.append(f"{fila['pct']:.0f}%  ·  {int(fila['sum'])} de {int(fila['size'])}"
                      + ("  · base pequeña" if chico else ""))
        colores_texto.append(c if c in (AZUL, ROJO) else TEXTO_SEC)

    fig, ax = plt.subplots(figsize=(8, _alto(len(con), 0.42)))
    _barras_h(ax, [_est.etiqueta(c) for c in con.index], con["pct"].values, colores,
              textos, colores_texto)
    ax.set_xlim(0, 150)
    _linea_alerta_gap(ax, len(con) - 0.45)
    _resaltar_nombres(ax, [_est.etiqueta(FIN)])
    titular(ax, _h.gap_por_estatus(pct_titulo), "% de solicitudes con GAP en cada estatus")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_gap_por_vendedor_total(df, guardar_como=None):
    """GAP de cada vendedor sobre su total: la barra azul va ENCIMA de la
    gris del total, en el mismo renglón."""
    if not {COL_VEND, COL_GAP}.issubset(df.columns):
        return None
    total_equipo, gap_equipo = len(df), int((df[COL_GAP] == "SI").sum())
    df, excluidos = _h.solo_personas(df)
    if not (df[COL_GAP] == "SI").any():
        return None
    totales = df[COL_VEND].value_counts().sort_values(ascending=True, kind="stable")
    con_gap = df[df[COL_GAP] == "SI"][COL_VEND].value_counts().reindex(totales.index).fillna(0).astype(int)
    tope = max(totales.max(), 1)

    fig, ax = plt.subplots(figsize=(9, _alto(len(totales), 0.5)))
    y = np.arange(len(totales))
    ax.barh(y, totales.values, color=GRIS_FONDO, height=0.66)
    hay_alerta = False
    for i, (t, g) in enumerate(zip(totales.values, con_gap.values)):
        pct = g / t * 100 if t else 0
        chico = t < BASE_MINIMA
        alerta = not chico and pct < _c.UMBRAL_ALERTA_GAP
        hay_alerta = hay_alerta or alerta
        color = ROJO if alerta else (GRIS_OSCURO if chico else AZUL)
        ax.barh([i], [g], color=color, height=0.66, alpha=0.55 if chico else 1)
        ax.text(t + tope * 0.015, i,
                f"{g} de {t}  ({pct:.0f}%)" + ("  · base pequeña" if chico else ""),
                va="center", fontsize=9, color=ROJO if alerta else TEXTO_SEC,
                fontweight="bold" if alerta else "normal")
    ax.set_yticks(y)
    ax.set_yticklabels(list(totales.index))
    ax.set_xlim(0, tope * 1.5)
    ax.spines["left"].set_color(GRIS_BARRA)
    _sin_eje(ax, "x")
    leyenda = [("Con GAP", AZUL), ("Total de solicitudes", TEXTO_SEC)]
    if hay_alerta:
        leyenda.append(("Menos de la mitad con GAP", ROJO))
    titular(ax, _h.cobertura_gap(total_equipo, gap_equipo),
            "Solicitudes con GAP sobre el total de cada vendedor" + _nota_excluidos(excluidos),
            leyenda=leyenda)
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_gap_por_vendedor_y_status(df, guardar_como=None):
    """Qué pasó con las solicitudes que llevaban GAP. En rojo, las que no
    procedieron: es GAP ofrecido que se perdió con la solicitud."""
    if not {COL_VEND, COL_CAT, COL_GAP}.issubset(df.columns):
        return None
    df_gap_equipo = df[df[COL_GAP] == "SI"]
    df, excluidos = _h.solo_personas(df)
    df_gap = df[df[COL_GAP] == "SI"]
    if df_gap.empty:
        return None
    pivote = pd.crosstab(df_gap[COL_VEND], df_gap[COL_CAT].map(grupo_de))
    pivote = pivote.reindex(columns=GRUPOS).fillna(0).astype(int)
    pivote = pivote.loc[pivote.sum(axis=1).sort_values(ascending=True, kind="stable").index]
    colores = {FIN: AZUL, APR: AZUL_MEDIO, TRA: GRIS_BARRA, PER: ROJO}
    tope = max(pivote.sum(axis=1).max(), 1)

    fig, ax = plt.subplots(figsize=(9, _alto(len(pivote), 0.5)))
    y = np.arange(len(pivote))
    izquierda = np.zeros(len(pivote))
    for g in GRUPOS:
        valores = pivote[g].values
        ax.barh(y, valores, left=izquierda, color=colores[g], height=0.66,
                edgecolor="white", linewidth=1.2)
        for i, (v, izq) in enumerate(zip(valores, izquierda)):
            if v and v / tope >= 0.045:
                ax.text(izq + v / 2, i, str(int(v)), ha="center", va="center", fontsize=8.5,
                        fontweight="bold", color="white" if g in (FIN, PER) else TEXTO)
        izquierda += valores
    for i, t in enumerate(pivote.sum(axis=1).values):
        ax.text(t + tope * 0.015, i, f"{int(t)} con GAP", va="center", fontsize=9, color=TEXTO_SEC)
    ax.set_yticks(y)
    ax.set_yticklabels(list(pivote.index))
    ax.set_xlim(0, tope * 1.2)
    ax.spines["left"].set_color(GRIS_BARRA)
    _sin_eje(ax, "x")
    titular(ax, _h.gap_que_no_procede(df_gap_equipo[COL_CAT].map(grupo_de)),
            "Solicitudes con GAP de cada vendedor, según cómo quedaron" + _nota_excluidos(excluidos),
            leyenda=[(ETIQUETA_GRUPO[g], colores[g] if g != TRA else TEXTO_SEC)
                     for g in GRUPOS if pivote[g].sum()])
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_gap_financiado_por_vendedor(df, guardar_como=None):
    """GAP dentro de los créditos ya financiados, por vendedor."""
    fin_equipo = df[df[COL_CAT] == FIN] if COL_CAT in df.columns else df.iloc[0:0]
    gap_fin_equipo = int((fin_equipo[COL_GAP] == "SI").sum()) if COL_GAP in df.columns else 0
    df, excluidos = _h.solo_personas(df)
    if not {COL_VEND, COL_CAT, COL_GAP}.issubset(df.columns):
        return None
    fin = df[df[COL_CAT] == FIN]
    if fin.empty:
        return None
    financiados = fin[COL_VEND].value_counts()
    con_gap = fin[fin[COL_GAP] == "SI"][COL_VEND].value_counts().reindex(financiados.index).fillna(0).astype(int)
    datos = pd.DataFrame({"fin": financiados, "gap": con_gap})
    datos["pct"] = datos["gap"] / datos["fin"] * 100
    datos = datos.sort_values(["fin", "gap"], ascending=True, kind="stable")
    tope = max(datos["fin"].max(), 1)

    fig, ax = plt.subplots(figsize=(8.5, _alto(len(datos), 0.5)))
    y = np.arange(len(datos))
    ax.barh(y, datos["fin"].values, color=GRIS_FONDO, height=0.66)
    hay_alerta = False
    for i, (_, fila) in enumerate(datos.iterrows()):
        chico = fila["fin"] < BASE_MINIMA_FINANCIADOS
        alerta = not chico and fila["pct"] < _c.UMBRAL_ALERTA_GAP
        hay_alerta = hay_alerta or alerta
        ax.barh([i], [fila["gap"]], height=0.66, alpha=0.55 if chico else 1,
                color=ROJO if alerta else (GRIS_OSCURO if chico else AZUL))
        ax.text(fila["fin"] + tope * 0.015, i,
                _metricas.etiqueta_gap(fila["gap"], fila["fin"], fila["pct"])
                + ("  · base pequeña" if chico else ""),
                va="center", fontsize=9, color=ROJO if alerta else TEXTO_SEC,
                fontweight="bold" if alerta else "normal")
    ax.set_yticks(y)
    ax.set_yticklabels(list(datos.index))
    ax.set_xlim(0, tope * 1.75)
    ax.spines["left"].set_color(GRIS_BARRA)
    _sin_eje(ax, "x")
    leyenda = [("Con GAP", AZUL), ("Créditos financiados", TEXTO_SEC)]
    if hay_alerta:
        leyenda.append(("Menos de la mitad con GAP", ROJO))
    titular(ax, _h.gap_en_financiados(gap_fin_equipo, len(fin_equipo)),
            "GAP dentro de los créditos financiados de cada vendedor" + _nota_excluidos(excluidos),
            leyenda=leyenda)
    plt.tight_layout()
    return _guardar(fig, guardar_como)


# ============================================================= Comparativo
def grafica_comp_totales_por_mes(datos_por_mes, orden_meses, guardar_como=None):
    """Solicitudes por mes, apiladas en los cuatro grupos."""
    meses = [m for m in orden_meses if COL_CAT in datos_por_mes[m]["df"].columns]
    if not meses:
        return None
    etiquetas = [m.title() for m in meses]
    conteos = [conteo_por_grupo(datos_por_mes[m]["df"][COL_CAT]) for m in meses]
    totales = [int(c.sum()) for c in conteos]
    tope = max(totales + [1])

    fig, ax = plt.subplots(figsize=(max(7, len(meses) * 1.5), 4.8))
    x = np.arange(len(meses))
    abajo = np.zeros(len(meses))
    for g in GRUPOS:
        valores = np.array([int(c[g]) for c in conteos])
        ax.bar(x, valores, bottom=abajo, color=COLOR_GRUPO[g], width=0.62,
               edgecolor="white", linewidth=1.2)
        for i, (v, b) in enumerate(zip(valores, abajo)):
            if v and v / tope >= 0.05:
                ax.text(i, b + v / 2, str(v), ha="center", va="center", fontsize=9,
                        fontweight="bold" if g == FIN else "normal",
                        color="white" if g in (FIN, PER) else TEXTO)
        abajo += valores
    for i, t in enumerate(totales):
        ax.text(i, t + tope * 0.02, str(t), ha="center", va="bottom", fontsize=10.5,
                fontweight="bold", color=TEXTO)
    ax.set_xticks(x)
    ax.set_xticklabels(etiquetas)
    ax.set_ylim(0, tope * 1.1)
    ax.spines["bottom"].set_color(GRIS_BARRA)
    _sin_eje(ax, "y")
    titular(ax, _h.volumen_por_mes(meses, totales),
            "Solicitudes de cada mes, según cómo quedaron (arriba, el total)",
            leyenda=[(ETIQUETA_GRUPO[g], COLOR_GRUPO[g] if g != TRA else TEXTO_SEC) for g in GRUPOS])
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def _lineas_con_rotulo(ax, meses, series, minimo_sep, extras=()):
    """series: [(nombre, valores, color, principal)]. Cada línea lleva su
    nombre al final, del color de la línea; la principal rotula todos sus
    puntos y las demás solo el primero y el último."""
    x = np.arange(len(meses))
    for _nombre, valores, color, principal in series:
        ax.plot(x, valores, marker="o", color=color, zorder=3 if principal else 2,
                linewidth=2.8 if principal else 1.6, markersize=6.5 if principal else 4.5)
    # Rótulos de punto, sin choques, mes por mes.
    for i in range(len(meses)):
        visibles = [(s[1][i], s) for s in series if s[3] or i in (0, len(meses) - 1)]
        base = [v for v, _ in visibles]
        pos = _separar([v + minimo_sep * 0.75 for v in base], minimo_sep)
        for (v, (_, _, color, principal)), yv in zip(visibles, pos):
            ax.text(i, yv, f"{v:.0f}%", ha="center", va="center", color=color,
                    fontsize=10 if principal else 8.5,
                    fontweight="bold" if principal else "normal", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.85))
    # Nombre de cada serie al final de su línea.
    # extras: [(texto, y, color)] — otros rótulos del margen derecho (una
    # línea de referencia), que se separan junto con los nombres.
    finales = _separar([float(s[1][-1]) for s in series] + [float(e[1]) for e in extras], minimo_sep)
    for (texto, _, color), yv in zip(extras, finales[len(series):]):
        ax.text(len(meses) - 1 + 0.16, yv, texto, ha="left", va="center", color=color, fontsize=8.5,
                zorder=6, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none"))
    for (nombre, _, color, principal), yv in zip(series, finales):
        ax.text(len(meses) - 1 + 0.16, yv, nombre, ha="left", va="center", color=color,
                fontsize=9.5 if principal else 9, fontweight="bold" if principal else "normal")
    ax.set_xticks(x)
    ax.set_xticklabels([str(m).title() for m in meses])
    ax.set_xlim(-0.3, len(meses) - 1 + 0.95)
    ax.spines["bottom"].set_color(GRIS_BARRA)
    _sin_eje(ax, "y")


def grafica_comp_tasa_conversion(tabla_comp, guardar_como=None):
    """Conversión por mes. La línea que importa (% financiado) en azul; el
    resto en gris. Si un mes fue claramente el más bajo, su punto va en rojo."""
    if tabla_comp.empty or "% Financiado" not in tabla_comp.columns:
        return None
    meses = tabla_comp.index.tolist()
    pct_fin = tabla_comp["% Financiado"].astype(float).values
    series = [("Financiado", pct_fin, AZUL, True)]
    for columna, nombre, color in (("Aprobado", "Aprobado", AZUL_MEDIO), ("Rechazado", "Rechazado", GRIS_OSCURO)):
        if columna in tabla_comp.columns:
            series.append((nombre, ((tabla_comp[columna] / tabla_comp["Total"]).fillna(0) * 100).values,
                           color, False))
    tope = max(float(np.max(s[1])) for s in series)

    fig, ax = plt.subplots(figsize=(max(7, len(meses) * 1.5), 4.6))
    ax.set_ylim(0, tope * 1.25 + 4)
    _lineas_con_rotulo(ax, meses, series, minimo_sep=(tope * 1.25 + 4) * 0.07)
    if len(pct_fin) >= 2 and pct_fin.max() - pct_fin.min() >= _c.UMBRAL_PUNTOS:
        i = int(np.argmin(pct_fin))
        ax.plot([i], [pct_fin[i]], marker="o", markersize=9, color=ROJO, zorder=4)
    titular(ax, _h.por_mes_minimo(meses, list(pct_fin), "la conversión"),
            "% de las solicitudes de cada mes que terminó en cada estatus")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_comp_montos_por_mes(tabla_comp, guardar_como=None):
    """Monto financiado por mes. Lo solicitado ya no se dibuja (era cinco
    veces más alto y aplastaba la barra que importa): va escrito como %."""
    if tabla_comp.empty or "Monto Financiado" not in tabla_comp.columns:
        return None
    meses = tabla_comp.index.tolist()
    fin = tabla_comp["Monto Financiado"].fillna(0).astype(float).values
    tot = (tabla_comp["Monto Total"].fillna(0).astype(float).values
           if "Monto Total" in tabla_comp.columns else np.zeros(len(meses)))
    promedio = float(fin.mean()) if len(fin) else 0
    tope = max(fin.max(), 1)
    destaca = len(fin) >= 2 and promedio and (fin.max() - fin.min()) / promedio * 100 >= 10

    fig, ax = plt.subplots(figsize=(max(7, len(meses) * 1.5), 4.6))
    x = np.arange(len(meses))
    ax.bar(x, fin, width=0.58,
           color=[AZUL if destaca and v == fin.max() else GRIS_BARRA for v in fin])
    for i, (v, t) in enumerate(zip(fin, tot)):
        es_max = destaca and v == fin.max()
        ax.text(i, v + tope * 0.02, _h.monto_corto(v), ha="center", va="bottom", fontsize=10.5,
                fontweight="bold", color=AZUL if es_max else TEXTO)
        if t and v / tope > 0.12:
            ax.text(i, v - tope * 0.03, f"{v / t * 100:.0f}% de lo\nsolicitado", ha="center",
                    va="top", fontsize=8.5, color="white" if es_max else TEXTO, linespacing=1.2)
    if promedio:
        ax.axhline(promedio, color=TEXTO_SEC, linestyle=(0, (4, 3)), linewidth=1, zorder=0)
        ax.text(len(meses) - 0.3, promedio, f"promedio\n{_h.monto_corto(promedio)}",
                ha="left", va="center", fontsize=8.5, color=TEXTO_SEC)
    ax.set_xticks(x)
    ax.set_xticklabels([str(m).title() for m in meses])
    ax.set_xlim(-0.6, len(meses) - 1 + 1.25)
    ax.set_ylim(0, tope * 1.14)
    ax.spines["bottom"].set_color(GRIS_BARRA)
    _sin_eje(ax, "y")
    titular(ax, _h.montos_por_mes(meses, list(fin)), "Monto financiado (dispersado) por mes")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_comp_gap_vs_gap_financiado(tabla_comp, guardar_como=None):
    """GAP por mes: en créditos financiados (azul) y en todas las solicitudes
    (gris). La línea roja marca el umbral de alerta."""
    if tabla_comp.empty or "% GAP Financiado" not in tabla_comp.columns or \
       tabla_comp["% GAP Financiado"].isna().all():
        return None
    meses = tabla_comp.index.tolist()
    gap_fin = tabla_comp["% GAP Financiado"].fillna(0).astype(float).values
    series = [("En créditos financiados", gap_fin, AZUL, True)]
    if "% GAP" in tabla_comp.columns:
        series.append(("En todas las solicitudes", tabla_comp["% GAP"].fillna(0).astype(float).values,
                       GRIS_OSCURO, False))

    fig, ax = plt.subplots(figsize=(max(7.6, len(meses) * 1.6), 4.6))
    u = _c.UMBRAL_ALERTA_GAP
    # Líneas: no necesitan partir de cero. La escala se ajusta a los datos
    # (siempre con el umbral de alerta a la vista) para que se lea el cambio.
    valores = np.concatenate([s[1] for s in series])
    piso = max(0, min(valores.min(), u) - 14)
    techo = min(108, max(valores.max(), u) + 14)
    ax.set_ylim(piso, techo)
    ax.axhline(u, color=ROJO, linestyle=(0, (4, 3)), linewidth=0.9, zorder=1)
    _lineas_con_rotulo(ax, meses, series, minimo_sep=(techo - piso) * 0.085,
                       extras=[("alerta: menos de la mitad", u, ROJO)])
    for i, v in enumerate(gap_fin):
        if v < u:
            ax.plot([i], [v], marker="o", markersize=9, color=ROJO, zorder=4)
    ax.set_xlim(-0.3, len(meses) - 1 + 1.35)
    titular(ax, _h.gap_financiados_por_mes(meses, list(gap_fin)),
            "% con GAP por mes · lo esperado es 100% · la escala no parte de cero")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_pendiente_vendedores(df_combinado, orden_meses, guardar_como=None):
    """Gráfica de pendiente: solicitudes de cada vendedor en el primer mes y
    en el último. Azul quien subió, rojo quien bajó, gris quien se movió
    menos de lo que se considera un cambio."""
    if not {COL_VEND, "Mes"}.issubset(df_combinado.columns):
        return None
    # Varias bitácoras concatenadas pueden repetir índice.
    df, excluidos = _h.solo_personas(df_combinado.reset_index(drop=True))
    pivote = pd.crosstab(df[COL_VEND], df["Mes"])
    meses = [m for m in orden_meses if m in pivote.columns]
    if len(meses) < 2 or pivote.empty:
        return None
    ini, fin = pivote[meses[0]], pivote[meses[-1]]
    cambio = fin - ini
    tope = max(ini.max(), fin.max(), 1)
    sep = tope * 0.062

    fig, ax = plt.subplots(figsize=(8, max(4.2, len(pivote) * 0.5 + 1.4)))
    # Empates: se ordenan por el otro extremo, para que las líneas no se
    # crucen de más al llegar a sus rótulos.
    y_izq = dict(zip(pivote.index, _separar([float(a) + float(b) * 1e-6 for a, b in zip(ini, fin)], sep)))
    y_der = dict(zip(pivote.index, _separar([float(b) + float(a) * 1e-6 for a, b in zip(ini, fin)], sep)))
    for v in sorted(pivote.index, key=lambda n: abs(cambio[n])):
        d = int(cambio[v])
        if d >= _c.MIN_CAMBIO_VENDEDOR:
            color, peso, ancho = AZUL, "bold", 2.6
        elif d <= -_c.MIN_CAMBIO_VENDEDOR:
            color, peso, ancho = ROJO, "bold", 2.6
        else:
            color, peso, ancho = GRIS_BARRA, "normal", 1.4
        texto = color if color != GRIS_BARRA else TEXTO_SEC
        ax.plot([0, 1], [ini[v], fin[v]], color=color, linewidth=ancho, marker="o",
                markersize=5.5, zorder=3 if color != GRIS_BARRA else 2)
        ax.text(-0.04, y_izq[v], f"{_h.nombre_corto(v)}   {int(ini[v])}", ha="right", va="center",
                fontsize=9, color=texto, fontweight=peso)
        ax.text(1.04, y_der[v], f"{int(fin[v])}   ({d:+d})" if d else f"{int(fin[v])}   (igual)",
                ha="left", va="center", fontsize=9, color=texto, fontweight=peso)
    ax.set_xlim(-0.75, 1.5)
    ax.set_ylim(min(min(y_izq.values()), min(y_der.values())) - sep,
                max(max(y_izq.values()), max(y_der.values())) + sep * 1.6)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([str(meses[0]).title(), str(meses[-1]).title()], fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", length=0, pad=6)
    for lado in ("left", "bottom", "top", "right"):
        ax.spines[lado].set_visible(False)
    ax.yaxis.set_visible(False)
    titular(ax, _h.quien_subio_y_bajo(cambio),
            "Solicitudes por vendedor, del primer mes al último" + _nota_excluidos(excluidos),
            leyenda=[("Subió", AZUL), ("Bajó", ROJO), ("Sin cambio relevante", TEXTO_SEC)])
    plt.tight_layout()
    return _guardar(fig, guardar_como)


# ====================================================== Resumen por vendedor
def grafica_estatus_vendedor(df_v, vendedor, guardar_como=None):
    """Las solicitudes del vendedor por estatus. Sustituye a la dona: en
    azul lo financiado, lo demás en gris."""
    if COL_CAT not in df_v.columns or df_v.empty:
        return None
    conteo = df_v[COL_CAT].value_counts()
    orden = [c for c in _est.ORDEN_CATEGORIAS if c in conteo.index][::-1]
    conteo_ord = conteo.reindex(orden)
    total = int(conteo_ord.sum())

    fig, ax = plt.subplots(figsize=(7.5, _alto(len(conteo_ord), 0.42)))
    _barras_h(ax, [_est.etiqueta(c) for c in orden], conteo_ord.values,
              [AZUL if c == FIN else GRIS_BARRA for c in orden],
              [f"{int(n)}  ({n / total * 100:.0f}%)" for n in conteo_ord.values],
              [AZUL if c == FIN else TEXTO_SEC for c in orden])
    _resaltar_nombres(ax, [_est.etiqueta(FIN)])
    titular(ax, _h.tu_cierre(conteo), "Tus solicitudes por estatus")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_equipo_destacado(df_total, vendedor, guardar_como=None):
    """Volumen de cada vendedor del equipo; solo el del reporte va en azul."""
    if COL_VEND not in df_total.columns:
        return None
    df_total, excluidos = _h.solo_personas(df_total, conservar=vendedor)
    conteo = df_total[COL_VEND].value_counts().sort_values(ascending=True, kind="stable")
    if conteo.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, _alto(len(conteo))))
    _barras_h(ax, list(conteo.index), conteo.values,
              [AZUL if n == vendedor else GRIS_BARRA for n in conteo.index],
              [f"Tú: {int(v)}" if n == vendedor else str(int(v)) for n, v in conteo.items()],
              [AZUL if n == vendedor else TEXTO_SEC for n in conteo.index], margen=1.18)
    _resaltar_nombres(ax, [vendedor])
    titular(ax, _h.tu_lugar(conteo, vendedor),
            "Tus solicitudes frente al resto del equipo" + _nota_excluidos(excluidos))
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_modelos_vendedor(df_v, vendedor, guardar_como=None):
    if "Vehículo" not in df_v.columns:
        return None
    conteo = df_v["Vehículo"].dropna().value_counts().sort_values(ascending=True, kind="stable")
    if conteo.empty:
        return None
    tope = conteo.max()
    fig, ax = plt.subplots(figsize=(8, _alto(len(conteo), 0.4, minimo=2.2)))
    _barras_h(ax, list(conteo.index), conteo.values,
              [AZUL if v == tope else GRIS_BARRA for v in conteo.values],
              [str(int(v)) for v in conteo.values],
              [AZUL if v == tope else TEXTO_SEC for v in conteo.values], margen=1.12)
    _resaltar_nombres(ax, [n for n, v in conteo.items() if v == tope])
    titular(ax, _h.tu_modelo(conteo), "Tus modelos solicitados en el mes")
    plt.tight_layout()
    return _guardar(fig, guardar_como)


def grafica_historial_vendedor(historial, guardar_como=None):
    """Solicitudes (gris) y créditos financiados (azul) del vendedor por mes."""
    if not historial or len(historial) < 2:
        return None
    meses = [h["mes"] for h in historial]
    solicitudes = [h["ind"]["solicitudes"] or 0 for h in historial]
    financiados = [h["ind"]["financiados"] or 0 for h in historial]
    if not any(solicitudes):
        return None
    x = np.arange(len(meses))
    ancho = 0.34
    tope = max(solicitudes) or 1
    fig, ax = plt.subplots(figsize=(8, 3.9))
    ax.bar(x - ancho / 2, solicitudes, ancho, color=GRIS_BARRA)
    ax.bar(x + ancho / 2, financiados, ancho, color=AZUL)
    for i in range(len(historial)):
        ax.text(x[i] - ancho / 2, solicitudes[i] + tope * 0.02, str(solicitudes[i]),
                ha="center", va="bottom", fontsize=9, color=TEXTO_SEC)
        ax.text(x[i] + ancho / 2, financiados[i] + tope * 0.02, str(financiados[i]),
                ha="center", va="bottom", fontsize=10, fontweight="bold", color=AZUL)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{m}\n{h['ind']['conversion']:.0f}% de conversión" if h["presente"]
                        else f"{m}\nsin solicitudes" for m, h in zip(meses, historial)])
    ax.set_ylim(0, tope * 1.16)
    ax.spines["bottom"].set_color(GRIS_BARRA)
    _sin_eje(ax, "y")
    primero = next((h for h in historial if h["presente"]), historial[0])
    ultimo = historial[-1]
    antes, ahora = primero["ind"]["conversion"] or 0, ultimo["ind"]["conversion"] or 0
    if primero is ultimo or abs(ahora - antes) < 0.5:
        hallazgo = f"Tu conversión se mantiene en {ahora:.0f}%"
    else:
        hallazgo = (f"Tu conversión {'subió' if ahora > antes else 'bajó'} de "
                    f"{antes:.0f}% a {ahora:.0f}% desde {primero['mes']}")
    titular(ax, hallazgo, "Tu historial por mes",
            leyenda=[("Solicitudes", TEXTO_SEC), ("Créditos financiados", AZUL)])
    plt.tight_layout()
    return _guardar(fig, guardar_como)
