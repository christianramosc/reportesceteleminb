"""Resultado de "Validar nómina SAT" dibujado en la página."""

import pandas as pd
import streamlit as st

from . import validar_nomina_sat as _v

COLOR = {_v.ESTADO_OK: "green", _v.ESTADO_CANCELADO: "red", _v.ESTADO_NO_EXISTE: "red",
         _v.ESTADO_NO_COINCIDE: "orange", _v.ESTADO_SIN_DATOS: "gray", _v.ESTADO_ERROR: "gray"}


def _dinero(x):
    return "—" if x is None else f"${x:,.2f}"


def _fecha(d):
    return d.strftime("%d/%m/%Y") if d else "—"


def mostrar(resumen):
    filas, personas, hoy = resumen["filas"], resumen["personas"], resumen["hoy"]
    ok = sum(f.get("estado_sat") == _v.ESTADO_OK for f in filas)
    c1, c2, c3 = st.columns(3)
    c1.metric("Recibos leídos", len(filas))
    c2.metric("Vigentes en el SAT", ok)
    c3.metric("Personas", len(personas))

    if any(f.get("estado_sat") == _v.ESTADO_NO_COINCIDE and f.get("origen") == "PDF" for f in filas):
        st.info(
            "Algunos folios **existen en el SAT** pero el total del PDF no coincide con el del CFDI. "
            "Pasa con los tarjetones del IMSS y otras dependencias: el 'Líquido' del recibo no es el "
            "total timbrado. **Sube el XML** de esos recibos (se descarga del visor de nómina del SAT) "
            "para validarlos.",
            icon=":material/info:",
        )

    for p in personas:
        with st.container(border=True):
            titulo = p["nombre"] or "Receptor"
            st.markdown(f"#### {titulo} · `{p['rfc']}`")
            if not p.get("seleccion"):
                for a in p["avisos"]:
                    st.warning(a, icon=":material/warning:")
                continue
            r = p["habiles_restantes"]
            sig = _fecha(p["siguiente_fin"])
            if r < 0:
                st.error(f"Último recibo vencido hace {-r} día(s) hábil(es) (venció el {_fecha(p['vence'])}). "
                         f"Pide la nómina del periodo siguiente, que terminó el {sig}.",
                         icon=":material/event_busy:")
            elif r <= 2:
                st.warning(f"Último recibo vence el {_fecha(p['vence'])}: quedan {r} día(s) hábil(es). "
                           f"Si el folio llegará a Financiación después, pide la nómina que terminó el {sig}.",
                           icon=":material/schedule:")
            else:
                st.success(f"Último recibo vigente hasta el {_fecha(p['vence'])} ({r} días hábiles): "
                           f"10 días hábiles desde que termina el periodo siguiente ({sig}).",
                           icon=":material/event_available:")
            a, b, c, d = st.columns(4)
            a.metric("Frecuencia", p["frecuencia"])
            m1 = p["periodo_mes1"]
            a2 = p["periodo_mes2"]
            b.metric("Bruto mes 1", _dinero(p["bruto_mes1"]), help=f"{_fecha(m1[0])} a {_fecha(m1[1])}")
            c.metric("Bruto mes 2", _dinero(p["bruto_mes2"]),
                     help=f"{_fecha(a2[0])} a {_fecha(a2[1])}" if a2 else None)
            d.metric("Ingreso mensual", _dinero(p.get("ingreso_mensual")),
                     help="El mes más bajo de los dos. Debe llegar a $6,500 brutos sin ingresos adicionales.")
            for aviso in p["avisos"]:
                st.warning(aviso, icon=":material/warning:")

            tabla = pd.DataFrame([{
                "Periodo": f"{_fecha(x['inicio'])} – {_fecha(x['fin'])}",
                "Percepciones": _dinero(x.get("percepciones")),
                "Total CFDI": _dinero(x.get("total")),
                "SAT": x.get("estado_sat", ""),
                "Origen": x.get("origen", ""),
                "Cuenta": "Sí" if x in p["seleccion"] else "",
            } for x in reversed(p["recibos"])])
            st.dataframe(tabla, hide_index=True, width="stretch")
    st.caption(f"Vigencia calculada al {_fecha(hoy)}: cada recibo vale hasta 10 días hábiles después de que "
               "termina el periodo siguiente (la nómina que ya debió timbrarse), sin sábados, domingos ni días "
               "de descanso obligatorio (LFT art. 74).")
