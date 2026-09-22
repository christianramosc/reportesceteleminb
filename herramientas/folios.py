# -*- coding: utf-8 -*-
"""Folios que aparecen en más de un mes del comparativo.

El problema
-----------
Cada bitácora mensual es una foto del mes. Una solicitud que se aprueba en
junio y se financia en julio aparece en las dos: como APROBADO en la de
junio y como FINANCIADO en la de julio. Al apilar los meses, esa solicitud
se contaba dos veces. En junio–agosto 2026 eran 3 folios: 81 filas, 78
solicitudes reales.

La regla que se aplica (decidida con el usuario)
------------------------------------------------
- Lo que es POR MES sigue siendo la foto de cada bitácora: el renglón de
  julio del comparativo dice lo mismo que el Resumen Mensual de julio, y los
  dos reportes cuadran entre sí.
- Lo que es DEL PERIODO o POR VENDEDOR cuenta cada folio una sola vez, con
  su último estatus y en el mes en que se capturó. Así no se inflan las
  capturas de nadie.
- El reporte avisa qué folios cruzaron de mes y cómo afecta la lectura.

Qué NO resuelve
---------------
Solo se detectan cruces entre los meses que se cargaron. Un folio de mayo
que se financia en junio no se ve si mayo no está en el comparativo. Y los
reportes de un solo mes no pueden detectarlo nunca: ven un solo archivo.
"""

import math

import pandas as pd

COL_FOLIO = "Folio CCK"
COL_MES = "Mes"
COL_CAT = "Categoria"
COL_VEND = "Nombre del Vendedor"

COL_MES_CAPTURA = "Mes de captura"
COL_CUENTA = "Cuenta en periodo"

# Campos cuyo cambio entre la captura y el último estatus vale la pena
# señalar: si el vehículo o el monto cambian, lo financiado no es lo que se
# aprobó.
CAMPOS_COMPARABLES = ["Nombre del Vendedor", "Vehículo", "Monto Total a Financiar",
                      "¿Tiene GAP?"]


def normalizar_folio(valor):
    """17665240, 17665240.0 y " 17665240 " son el mismo folio."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto or None


def _preparar(df, orden_meses):
    d = df.copy()
    d["_folio"] = d[COL_FOLIO].map(normalizar_folio)
    orden = {m: i for i, m in enumerate(orden_meses)}
    d["_orden_mes"] = d[COL_MES].map(orden).fillna(len(orden))
    d["_pos"] = range(len(d))
    return d.sort_values(["_orden_mes", "_pos"], kind="stable")


def _iguales(a, b):
    if pd.isna(a) and pd.isna(b):
        return True
    try:
        return abs(float(str(a).replace("$", "").replace(",", "")) -
                   float(str(b).replace("$", "").replace(",", ""))) < 0.01
    except (TypeError, ValueError):
        return str(a).strip().upper() == str(b).strip().upper()


def consolidar(df, orden_meses):
    """Devuelve (df_unico, resultado).

    df_unico: una fila por folio, con su último estatus y sus últimos datos,
    y la columna Mes reemplazada por el mes de captura. Las filas sin folio
    se conservan tal cual, porque no hay con qué cruzarlas.

    resultado: dict con
      - "cruces": DataFrame de los folios que aparecen en 2 o más meses.
      - "repetidos_mismo_mes": folios que aparecen dos veces en un mismo mes
        (posible doble captura).
      - "financiado_doble": folios FINANCIADOS en más de un mes (posible
        doble registro de un crédito; inflaría el monto por mes).
      - "filas", "folios": conteos antes y después.
    """
    vacio = {"cruces": pd.DataFrame(), "repetidos_mismo_mes": [],
             "financiado_doble": [], "filas": len(df), "folios": len(df)}
    if COL_FOLIO not in df.columns or COL_MES not in df.columns or df.empty:
        return df.copy(), vacio

    d = _preparar(df, orden_meses)
    con_folio = d[d["_folio"].notna()]
    sin_folio = d[d["_folio"].isna()]

    primero = con_folio.groupby("_folio", sort=False).head(1).set_index("_folio")
    ultimo = con_folio.groupby("_folio", sort=False).tail(1).copy()
    ultimo[COL_MES_CAPTURA] = ultimo["_folio"].map(primero[COL_MES])
    ultimo["_mes_ultimo"] = ultimo[COL_MES]
    ultimo[COL_MES] = ultimo[COL_MES_CAPTURA]

    sin_folio = sin_folio.copy()
    sin_folio[COL_MES_CAPTURA] = sin_folio[COL_MES]
    sin_folio["_mes_ultimo"] = sin_folio[COL_MES]

    df_unico = pd.concat([ultimo, sin_folio]).sort_values(["_orden_mes", "_pos"])

    # --- Cruces entre meses
    meses_por_folio = con_folio.groupby("_folio")[COL_MES].nunique()
    folios_cruce = meses_por_folio[meses_por_folio > 1].index
    filas = []
    for folio in folios_cruce:
        g = con_folio[con_folio["_folio"] == folio]
        ini, fin = g.iloc[0], g.iloc[-1]
        cambios = [c for c in CAMPOS_COMPARABLES
                   if c in g.columns and not _iguales(ini[c], fin[c])]
        filas.append({
            "Folio": folio,
            "Vendedor": fin.get(COL_VEND, ""),
            "Mes de captura": ini[COL_MES],
            "Estatus al capturar": ini.get(COL_CAT, ""),
            "Mes del último estatus": fin[COL_MES],
            "Último estatus": fin.get(COL_CAT, ""),
            "Cambios": cambios,
        })
    cruces = pd.DataFrame(filas)

    # --- Anomalías que no son un cruce normal
    por_mes = con_folio.groupby(["_folio", COL_MES]).size()
    repetidos = sorted({f for (f, _), n in por_mes.items() if n > 1})
    financiado_doble = []
    if COL_CAT in con_folio.columns:
        fin_meses = (con_folio[con_folio[COL_CAT] == "FINANCIADO"]
                     .groupby("_folio")[COL_MES].nunique())
        financiado_doble = sorted(fin_meses[fin_meses > 1].index)

    df_unico = df_unico.drop(columns=["_folio", "_orden_mes", "_pos", "_mes_ultimo"])
    return df_unico.reset_index(drop=True), {
        "cruces": cruces,
        "repetidos_mismo_mes": repetidos,
        "financiado_doble": financiado_doble,
        "filas": len(df),
        "folios": len(df_unico),
    }


def anotar(df, orden_meses):
    """Todas las filas originales, más dos columnas para el Excel:

    - Mes de captura: el primer mes en que aparece el folio.
    - Cuenta en periodo: "SI" en la fila que representa al folio (la de su
      último estatus), "NO" en las apariciones anteriores.

    Así el libro conserva la foto completa de cada mes, y las fórmulas de las
    hojas por vendedor filtran por "Cuenta en periodo" = SI para contar cada
    folio una vez. Quien audite puede ver exactamente qué filas se excluyen.
    """
    if COL_FOLIO not in df.columns or COL_MES not in df.columns or df.empty:
        d = df.copy()
        if COL_MES in d.columns:
            d[COL_MES_CAPTURA] = d[COL_MES]
        d[COL_CUENTA] = "SI"
        return d

    d = _preparar(df, orden_meses)
    captura = d[d["_folio"].notna()].groupby("_folio")[COL_MES].first()
    d[COL_MES_CAPTURA] = d["_folio"].map(captura).fillna(d[COL_MES])
    ultima_pos = d[d["_folio"].notna()].groupby("_folio")["_pos"].max()
    d[COL_CUENTA] = [
        "SI" if (f is None or ultima_pos.get(f) == p) else "NO"
        for f, p in zip(d["_folio"], d["_pos"])
    ]
    d = d.sort_values("_pos").drop(columns=["_folio", "_orden_mes", "_pos"])
    return d.reset_index(drop=True)


def texto_aviso(resultado):
    """Viñeta para la Lectura del periodo. None si no hubo cruces."""
    cruces = resultado["cruces"]
    partes = []

    if not cruces.empty:
        # Una observación corta, sin nombres: el detalle por vendedor y por
        # folio está en la tabla "Folios que cruzaron de mes".
        frases = []
        grupos = cruces.groupby(["Mes de captura", "Mes del último estatus",
                                 "Último estatus"], sort=False)
        for (captura, ultimo, estatus), g in grupos:
            k = len(g)
            sujeto = (f"{k} solicitudes capturadas en {str(captura).title()}" if k != 1
                      else f"1 solicitud capturada en {str(captura).title()}")
            if estatus == "FINANCIADO":
                verbo = "se financiaron" if k != 1 else "se financió"
                frases.append(f"{sujeto} {verbo} en {str(ultimo).title()}")
            else:
                verbo = "pasaron" if k != 1 else "pasó"
                frases.append(f"{sujeto} {verbo} a {str(estatus).title()} en "
                              f"{str(ultimo).title()}")
        texto = ("<b>Folios entre meses:</b> "
                 + (", ".join(frases[:-1]) + " y " + frases[-1] if len(frases) > 1
                    else frases[0])
                 + ". En los totales del periodo cuentan una sola vez.")
        partes.append(texto)

    if resultado["financiado_doble"]:
        partes.append(
            f"<b>Revisa estos folios:</b> {', '.join(resultado['financiado_doble'])} "
            f"aparecen como FINANCIADOS en más de un mes. Si es el mismo crédito, el "
            f"monto financiado por mes lo está contando dos veces.")
    if resultado["repetidos_mismo_mes"]:
        partes.append(
            f"<b>Folios repetidos:</b> {', '.join(resultado['repetidos_mismo_mes'])} "
            f"aparecen dos veces dentro del mismo mes; probablemente es una doble "
            f"captura en la bitácora.")
    return partes
