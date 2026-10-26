# -*- coding: utf-8 -*-
"""Titulares de hallazgo para las gráficas.

Antes cada gráfica repetía el título de su barra de sección ("Tasa de
conversión por mes" debajo de "03 TASA DE CONVERSIÓN POR MES"). Ahora el
título dice lo que la gráfica muestra ("Agosto tuvo la conversión más baja:
18%") y debajo, en gris, una línea describe qué se está graficando.

Los hallazgos usan los mismos umbrales que las conclusiones
(conclusiones.UMBRAL_PUNTOS, UMBRAL_CONTRASTE, MIN_SOLICITUDES_TASA): si la
diferencia entre meses es ruido, el titular lo dice en vez de coronar un mes.
"""

import matplotlib.ticker as _mticker

try:
    from . import conclusiones as _c
except ImportError:  # ejecución suelta (Colab)
    import conclusiones as _c

GRIS = "#6B7280"
ROJO_ALERTA = "#E4002B"


# ------------------------------------------------------------ utilidades
def titular(ax, hallazgo, descripcion):
    """Hallazgo en negritas, alineado a la izquierda, y la descripción en
    gris debajo. Sustituye a ax.set_title()."""
    ax.set_title(hallazgo, loc="left", fontsize=12.5, fontweight="bold", pad=24, color="#1F2937")
    ax.text(0, 1.025, descripcion, transform=ax.transAxes, fontsize=9, color=GRIS,
            ha="left", va="bottom")


def monto_corto(valor):
    if abs(valor) >= 1_000_000:
        return f"${valor / 1_000_000:.2f} M"
    if abs(valor) >= 1_000:
        return f"${valor / 1_000:.0f} mil"
    return f"${valor:,.0f}"


def _monto_eje(v):
    """"$1.25 M", "$2 M", "$350 mil". Con un solo decimal fijo, un eje que
    iba de 50 en 50 mil se leía "$0.1 M, $0.1 M, $0.1 M" (0.05, 0.10, 0.15
    redondeados): tres marcas distintas con la misma etiqueta."""
    if not v:
        return "0"
    if abs(v) >= 1_000_000:
        texto = f"{v / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"${texto} M"
    return f"${v / 1_000:,.0f} mil"


def formato_millones(ax, eje="y"):
    """Eje de montos: "$1.5 M" en lugar de "1,500,000", o "$250 mil" si no
    llega al millón."""
    f = _mticker.FuncFormatter(lambda v, _: _monto_eje(v))
    (ax.yaxis if eje == "y" else ax.xaxis).set_major_formatter(f)


# ------------------------------------------------ anti-traslapes (gráficas)
def etiquetas_categorias_x(ax, textos, ancho=14, rotar_desde=7):
    """Pone los nombres de estatus en el eje X sin que se encimen.

    "DOCUMENTACION ADICIONAL" inclinado a 30° bajaba tanto que se metía en
    la leyenda. Ahora el nombre se parte en renglones ("DOCUMENTACION /
    ADICIONAL") y se deja horizontal; solo con muchas barras, donde ni
    partido cabe, se inclina.
    """
    import textwrap
    partidos = [textwrap.fill(str(t), ancho, break_long_words=False) for t in textos]
    ax.set_xticks(range(len(partidos)))
    if len(partidos) >= rotar_desde:
        ax.set_xticklabels(partidos, rotation=30, ha="right", rotation_mode="anchor")
        return
    ax.set_xticklabels(partidos, rotation=0, ha="center")
    # Una palabra sola no se puede partir ("CONTRAPROPUESTA"): si aun así
    # dos nombres vecinos se tocan, primero se achica la letra y, si no
    # basta, se inclinan.
    for tam in (None, 8, 7):
        if tam:
            for t in ax.get_xticklabels():
                t.set_fontsize(tam)
        if not _etiquetas_se_tocan(ax):
            return
    ax.set_xticklabels(partidos, rotation=30, ha="right", rotation_mode="anchor")


def _etiquetas_se_tocan(ax, holgura_pt=3):
    fig = ax.figure
    fig.tight_layout()          # se mide con el ancho final de la gráfica
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    holgura = holgura_pt * fig.dpi / 72
    cajas = sorted((t.get_window_extent(renderer) for t in ax.get_xticklabels()
                    if t.get_text()), key=lambda c: c.x0)
    return any(b.x0 - a.x1 < holgura for a, b in zip(cajas, cajas[1:]))


def leyenda_bajo_eje(ax, separacion_pt=6, **kwargs):
    """Leyenda centrada debajo de TODO lo que hay bajo el eje (nombres,
    etiqueta del eje), sin importar cuánto ocupen.

    Con un desplazamiento fijo (bbox_to_anchor=(0.5, -0.24)) la leyenda
    quedaba bien con nombres cortos y encima de ellos con nombres largos o
    en dos renglones. Aquí se mide dónde terminan y se coloca justo abajo.
    Llamarla al final, después de tight_layout().
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    cajas = [t.get_window_extent(renderer) for t in ax.get_xticklabels() if t.get_text()]
    if ax.xaxis.label.get_text():
        cajas.append(ax.xaxis.label.get_window_extent(renderer))
    fondo = min([c.y0 for c in cajas], default=ax.get_window_extent(renderer).y0)
    fondo -= separacion_pt * fig.dpi / 72
    y_ejes = ax.transAxes.inverted().transform((0, fondo))[1]
    kwargs.setdefault("frameon", False)
    return ax.legend(loc="upper center", bbox_to_anchor=(0.5, y_ejes), **kwargs)


def etiquetas_lineas(ax, series, separacion=0.075):
    """Rotula cada punto de varias líneas sin que los rótulos choquen.

    series: lista de (valores, color, kwargs_de_texto). Llamarla DESPUÉS de
    fijar set_ylim, porque la separación se calcula sobre la escala final.

    Con desplazamientos fijos (+4 arriba de una línea, -4 abajo de otra),
    dos líneas cercanas —15% financiado y 8% aprobado— dejaban sus rótulos
    pegados y cruzados: el "15%" quedaba junto a la línea del 8%. Aquí, en
    cada mes, los rótulos se ordenan por valor: el de la línea más baja va
    debajo de su punto si choca con el siguiente, y los demás se empujan
    hacia arriba hasta guardar una distancia mínima.
    """
    y0, y1 = ax.get_ylim()
    sep = (y1 - y0) * separacion
    desp = sep * 0.6
    if not series:
        return
    n = min(len(s[0]) for s in series)
    for i in range(n):
        puntos = sorted(((float(s[0][i]), s) for s in series), key=lambda t: t[0])
        pos = [v + desp for v, _ in puntos]
        if len(puntos) > 1 and pos[1] - pos[0] < sep and puntos[0][0] - desp - sep / 2 >= y0:
            pos[0] = puntos[0][0] - desp
        for k in range(1, len(pos)):
            if pos[k] < puntos[k][0]:          # va debajo de su punto: no se empuja
                continue
            if pos[k] - pos[k - 1] < sep:
                pos[k] = pos[k - 1] + sep
        for (v, (_, color, kw)), y in zip(puntos, pos):
            ax.text(i, y, f"{v:.0f}%", ha="center", va="center", color=color,
                    clip_on=False, **(kw or {}))


def ajustar_titulos(fig, margen_pt=4):
    """Parte en renglones el titular de una gráfica si no cabe a lo ancho.

    Un titular con varios modelos empatados ("Tus modelos más solicitados:
    MG3 1.5L STYLE MT, MG5 EXCITE MT y ZS 1.5T LUX ...") salía más ancho
    que la gráfica; al exportar con bbox "tight" la imagen se ensanchaba y,
    al escalarla al ancho del PDF, la gráfica quedaba diminuta.
    """
    import textwrap
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    derecha = fig.bbox.x1 - margen_pt * fig.dpi / 72
    cambio = False
    for ax in fig.axes:
        titulo = getattr(ax, "_left_title", None)
        if titulo is None or not titulo.get_text() or "\n" in titulo.get_text():
            continue
        caja = titulo.get_window_extent(renderer)
        disponible = derecha - caja.x0
        if caja.width <= disponible or disponible <= 0:
            continue
        caracteres = max(20, int(len(titulo.get_text()) * disponible / caja.width) - 1)
        titulo.set_text(textwrap.fill(titulo.get_text(), caracteres, break_long_words=False))
        cambio = True
    if cambio:
        fig.tight_layout()


def nombre_corto(nombre):
    """"Jessica Elizabeth Machuca Roque" -> "Jessica Elizabeth": cabe en un
    titular y en este equipo sigue siendo inequívoco."""
    partes = str(nombre).split()
    return " ".join(partes[:2]) if len(partes) > 2 else str(nombre)


def solo_personas(df, columna="Nombre del Vendedor", conservar=None):
    """Quita capturas genéricas ("Casa") de las gráficas por vendedor.
    Devuelve (df_filtrado, hubo_exclusiones).

    conservar: un nombre que se deja aunque no parezca de persona. En el
    reporte individual de "Casa", quitarla de su propia gráfica la dejaría
    sin el vendedor al que se refiere el reporte.
    """
    if columna not in df.columns:
        return df, False
    mask = df[columna].map(_c._es_nombre_de_persona)
    if conservar is not None:
        mask = mask | (df[columna] == conservar)
    return df[mask], bool((~mask).any())


def referencia_alerta_gap(ax):
    """Zona de alerta de GAP (menos de la mitad) y línea de lo esperado (100%).

    Van en la LEYENDA, no como texto dentro de la gráfica: un rótulo junto a
    la línea del 50% quedaba tapado por los datos cuando un mes caía cerca.
    """
    u = _c.UMBRAL_ALERTA_GAP
    ax.axhspan(0, u, color=ROJO_ALERTA, alpha=0.05, zorder=0,
               label="Zona de alerta: menos de la mitad")
    ax.axhline(u, color=ROJO_ALERTA, linestyle=(0, (4, 3)), linewidth=1, zorder=1)
    ax.axhline(100, color=GRIS, linestyle=":", linewidth=1.2, zorder=1,
               label="Lo esperado: todas (100%)")


def _lideres(serie):
    """Todos los que empatan en el máximo, en orden estable.

    Los titulares nombraban al "primero" con idxmax aunque hubiera empate: en
    julio decía "Tu modelo más solicitado: MG3 1.5L STYLE CVT (2)" cuando
    MG5 ELEGANCE AT también tenía 2 y aparecía arriba en la misma gráfica.
    """
    if serie.empty:
        return [], 0
    tope = serie.max()
    return [i for i in serie.sort_index().index if serie[i] == tope], tope


def _y(nombres):
    nombres = [str(n) for n in nombres]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


# ------------------------------------------------------------ hallazgos
def por_mes_minimo(meses, valores, que, formato="{:.0f}%"):
    """"Agosto tuvo {que} más baja: 18%" o "{Que} pareja: entre X y Y"."""
    valores = list(valores)
    if len(valores) < 2:
        return f"{que.capitalize()}: {formato.format(valores[0])}" if valores else que.capitalize()
    lo, hi = min(valores), max(valores)
    if hi - lo < _c.UMBRAL_PUNTOS:
        return f"{que.capitalize()} pareja: entre {formato.format(lo)} y {formato.format(hi)}"
    mes = str(meses[valores.index(lo)]).title()
    return f"{mes} tuvo {que} más baja: {formato.format(lo)}"


def rechazo_por_mes(meses, totales, rechazos):
    pct = [r / t * 100 if t else 0 for r, t in zip(rechazos, totales)]
    if len(pct) < 2 or max(pct) - min(pct) < _c.UMBRAL_CONTRASTE:
        return f"El rechazo se mantuvo entre {min(pct):.0f}% y {max(pct):.0f}%"
    i = pct.index(max(pct))
    return f"{str(meses[i]).title()} concentró el mayor rechazo: {rechazos[i]} de {totales[i]} ({pct[i]:.0f}%)"


def montos_por_mes(meses, montos):
    montos = list(montos)
    if not montos:
        return "Monto financiado por mes"
    prom = sum(montos) / len(montos)
    texto = f"Se financian {monto_corto(prom)} al mes en promedio"
    if len(montos) >= 2 and prom and (max(montos) - min(montos)) / prom * 100 >= 10:
        texto += f"; {str(meses[montos.index(max(montos))]).title()} fue el más alto"
    return texto


def gap_financiados_por_mes(meses, pct):
    pct = list(pct)
    if not pct:
        return "GAP en créditos financiados"
    lo = min(pct)
    mes = str(meses[pct.index(lo)]).title()
    if lo < _c.UMBRAL_ALERTA_GAP:
        return f"En {mes}, solo {lo:.0f}% de los créditos financiados llevó GAP"
    return f"GAP en créditos financiados: entre {lo:.0f}% y {max(pct):.0f}%"


def vendedor_con_mas(conteo, total=None):
    """conteo: Serie vendedor -> solicitudes (ya sin capturas genéricas).
    total: solicitudes de TODO el equipo, para que cuadre con la portada."""
    if conteo.empty:
        return "Solicitudes por vendedor"
    lideres, tope = _lideres(conteo)
    total = int(total if total is not None else conteo.sum())
    if len(lideres) > 1:
        return f"{_y([nombre_corto(x) for x in lideres])} ingresaron más solicitudes: {int(tope)} cada uno"
    return f"{nombre_corto(lideres[0])} ingresó más solicitudes: {int(tope)} de {total}"


def vendedor_mejor_conversion(pivote):
    """pivote: vendedor x categoría. Solo compara a quien tiene volumen."""
    if "FINANCIADO" not in pivote.columns:
        return "Estatus de cierre por vendedor"
    tot = pivote.sum(axis=1)
    elegibles = tot[tot >= _c.MIN_SOLICITUDES_TASA].index
    if len(elegibles) < 2:
        return "Estatus de cierre por vendedor"
    tasa = (pivote.loc[elegibles, "FINANCIADO"] / tot[elegibles] * 100).round(1)
    lideres, tope = _lideres(tasa)
    if len(lideres) > 1:
        return f"{_y([nombre_corto(x) for x in lideres])} financian {tope:.0f}% de sus solicitudes, la tasa más alta"
    return f"{nombre_corto(lideres[0])} financia {tope:.0f}% de sus solicitudes, la tasa más alta"


def cobertura_gap(total, con_gap):
    """total y con_gap: enteros de TODO el equipo (cuadran con la portada)."""
    t, g = int(total), int(con_gap)
    pct = g / t * 100 if t else 0
    return f"GAP en {g} de {t} solicitudes del equipo ({pct:.0f}%)"


def gap_en_financiados(con_gap, financiados):
    g, n = int(con_gap), int(financiados)
    pct = g / n * 100 if n else 0
    return f"{g} de {n} créditos financiados llevan GAP ({pct:.0f}%)"


def modelo_lider(conteo):
    if conteo.empty:
        return "Modelos más solicitados"
    total = int(conteo.sum())
    lideres, tope = _lideres(conteo)
    if len(lideres) > 1:
        return f"{_y(lideres)} empatan con {int(tope)} solicitudes cada uno"
    return f"{lideres[0]} encabeza con {int(tope)} solicitudes ({tope / total * 100:.0f}% del total)"


# ------------------------------------------- Resumen Mensual y Avance
def estatus_mayoritario(conteo):
    """conteo: Serie estatus -> solicitudes."""
    if conteo.empty:
        return "Solicitudes por estatus"
    total = int(conteo.sum())
    lideres, tope = _lideres(conteo)
    if len(lideres) > 1:
        return f"{_y([str(x).title() for x in lideres])} empatan con {int(tope)} solicitudes cada uno"
    return f"{str(lideres[0]).title()} concentra {int(tope)} de {total} solicitudes ({tope / total * 100:.0f}%)"


def mezcla_de_cierre(conteo):
    """conteo: Serie categoría -> solicitudes."""
    total = int(conteo.sum())
    if not total:
        return "Proporción por estatus"
    fin = int(conteo.get("FINANCIADO", 0)) / total * 100
    rech = int(conteo.get("RECHAZADO", 0)) / total * 100
    return f"Se financió {fin:.0f}% y se rechazó {rech:.0f}% de las solicitudes"


def monto_top_vendedor(monto_financiado):
    """monto_financiado: Serie vendedor -> monto financiado."""
    serie = monto_financiado[monto_financiado > 0] if len(monto_financiado) else monto_financiado
    if serie.empty:
        return "Ningún crédito financiado todavía"
    lideres, tope = _lideres(serie)
    return (f"{_y([nombre_corto(x) for x in lideres])} "
            f"{'colocaron' if len(lideres) > 1 else 'colocó'} el mayor monto financiado: {monto_corto(tope)}")


def gap_por_estatus(pct_gap):
    """pct_gap: Serie categoría -> % con GAP."""
    if "FINANCIADO" in pct_gap.index and "RECHAZADO" in pct_gap.index:
        return (f"GAP en {pct_gap['FINANCIADO']:.0f}% de las financiadas "
                f"y en {pct_gap['RECHAZADO']:.0f}% de las rechazadas")
    if pct_gap.empty:
        return "% con GAP por estatus"
    return f"{str(pct_gap.idxmax()).title()} lleva GAP en {pct_gap.max():.0f}% de los casos"


def gap_que_se_rechaza(df_gap):
    """df_gap: solicitudes CON GAP. Cuántas terminaron rechazadas."""
    n = len(df_gap)
    if not n or "Categoria" not in df_gap.columns:
        return "GAP por vendedor y estatus"
    r = int((df_gap["Categoria"] == "RECHAZADO").sum())
    return f"{r} de {n} solicitudes con GAP terminaron rechazadas"


# ------------------------------------------------- reporte individual
def tu_cierre(conteo):
    total = int(conteo.sum())
    fin = int(conteo.get("FINANCIADO", 0))
    if not total:
        return "Tus solicitudes por estatus"
    return f"Financiaste {fin} de {total} solicitudes ({fin / total * 100:.0f}%)"


def tu_lugar(totales, vendedor):
    """totales: Serie vendedor -> solicitudes (solo personas + el vendedor)."""
    if vendedor not in totales.index:
        return "Tu volumen frente al equipo"
    orden = totales.sort_values(ascending=False)
    lugar = list(orden.index).index(vendedor) + 1
    return f"Ocupas el lugar {lugar} de {len(orden)} en solicitudes"


def tu_modelo(conteo):
    if conteo.empty:
        return "Tus modelos solicitados"
    lideres, tope = _lideres(conteo)
    if len(lideres) > 1:
        return f"Tus modelos más solicitados: {_y(lideres)} ({int(tope)} cada uno)"
    return f"Tu modelo más solicitado: {lideres[0]} ({int(tope)})"
