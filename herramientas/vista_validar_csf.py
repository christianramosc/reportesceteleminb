# -*- coding: utf-8 -*-
"""Resultado de "Validar CSF" dibujado en la página (sin descargar el PDF).

Recibe la lista de resumen_dict() de validar_csf.py, uno por constancia:
  1. Panorama del lote: cuántas son confiables, a revisar o alteradas.
  2. Una tarjeta por constancia: veredicto, candados que pasa, vigencia,
     observaciones (solo lo que falló o merece revisión), datos básicos,
     links a los QR y el detalle completo de los candados.
"""

import re

import pandas as pd
import streamlit as st

# Veredicto -> (color de badge, icono, frase para el analista)
VEREDICTOS = {
    "SIN INDICIOS DE ALTERACIÓN": ("green", ":material/verified_user:",
                                   "Confiable: pasó los candados técnicos. Valida los QR antes de usarla."),
    "REVISAR MANUALMENTE": ("orange", ":material/warning:",
                            "Revisar: hay avisos con explicación legítima posible. Confirma en el QR del SAT."),
    "ALTERADA / NO CONFIABLE": ("red", ":material/gpp_bad:",
                                "No confiable: hay indicios de alteración. No la uses para el expediente."),
    "NO VERIFICABLE": ("red", ":material/hide_image:",
                       "No verificable: es una foto o captura. Pide el PDF original del SAT."),
}
ESTADOS = {"OK": ("green", ":material/check_circle:"), "AVISO": ("orange", ":material/warning:"),
           "FALLA": ("red", ":material/cancel:"), "INFO": ("gray", ":material/info:")}
SECCIONES = {1: "Archivo y estructura del PDF", 2: "Códigos QR y código de barras",
             3: "Coherencia de los datos fiscales", 4: "Políticas de la financiera"}
# Datos que se muestran arriba (el resto va en "Más datos").
DATOS_PRINCIPALES = ("RFC", "Nombre / razón social", "Tipo", "Estatus en el padrón", "Emisión")


def _color(estado_o_veredicto):
    if estado_o_veredicto in VEREDICTOS:
        return VEREDICTOS[estado_o_veredicto][0]
    return ESTADOS.get(estado_o_veredicto, ("gray", ""))[0]


def _md(texto):
    """Escapa lo que Streamlit interpretaría como formato en datos del PDF.
    Las direcciones web van como código: así NO quedan como link clicable
    (una de ellas puede ser la página falsa del QR alterado)."""
    partes = re.split(r"(https?://\S+?)(?=[\s,;)\]»]|\.(?:\s|$)|$)", str(texto))
    salida = []
    for i, p in enumerate(partes):
        if i % 2:
            salida.append(f"`{p}`")
        else:
            salida.append(p.replace("$", "\\$").replace("*", "\\*").replace("_", "\\_")
                          .replace("[", "\\[").replace("`", "'"))
    return "".join(salida)


ORDEN = {"ALTERADA / NO CONFIABLE": 0, "NO VERIFICABLE": 1, "REVISAR MANUALMENTE": 2,
         "SIN INDICIOS DE ALTERACIÓN": 3}


def mostrar(resumenes):
    if not resumenes:
        st.info("No se analizó ninguna constancia.")
        return
    if len(resumenes) > 1:
        _panorama(resumenes)
    # Las no confiables primero: son las que requieren acción.
    for r in sorted(resumenes, key=lambda r: ORDEN.get(r["veredicto"], 9)):
        _tarjeta(r)


def _panorama(resumenes):
    cuenta = {v: sum(r["veredicto"] == v for r in resumenes) for v in VEREDICTOS}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Constancias", len(resumenes), border=True)
    c2.metric("Confiables", cuenta["SIN INDICIOS DE ALTERACIÓN"], border=True)
    c3.metric("A revisar", cuenta["REVISAR MANUALMENTE"], border=True)
    c4.metric("No confiables", cuenta["ALTERADA / NO CONFIABLE"] + cuenta["NO VERIFICABLE"], border=True)

    tabla = pd.DataFrame([{
        "RFC": r["datos"]["RFC"],
        "Nombre": r["datos"]["Nombre / razón social"],
        "Veredicto": r["veredicto"],
        "Candados": f"{r['tecnicos_ok']}/{r['tecnicos_total']}",
        "Fallas": r["fallas"],
        "Vigente": "Sí" if (r["dias_emision"] is not None and r["dias_emision"] <= 30) else "No",
    } for r in resumenes])
    tabla = tabla.sort_values("Veredicto", key=lambda s: s.map(ORDEN), kind="stable")
    st.dataframe(tabla, hide_index=True, width="stretch")


def _tarjeta(r):
    color, icono, frase = VEREDICTOS.get(r["veredicto"], ("gray", ":material/help:", ""))
    with st.container(border=True):
        # --- Encabezado: archivo + veredicto -------------------------------
        st.markdown(f"**{_md(r['archivo'])}**")
        st.badge(r["veredicto"], icon=icono, color=color)
        st.caption(frase)

        # --- Cifras ---------------------------------------------------------
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Candados técnicos", f"{r['tecnicos_ok']}/{r['tecnicos_total']}",
                  help="Secciones 1 a 3: archivo, códigos QR y coherencia de datos. "
                       "Los INFO cuentan como aprobados.")
        c2.metric("Fallas", r["fallas"])
        c3.metric("Avisos", r["avisos"])
        dias = r["dias_emision"]
        c4.metric("Emitida hace", f"{dias} días" if dias is not None else "—",
                  delta=("Vigente" if dias is not None and dias <= 30 else "Vencida"),
                  delta_color=("normal" if dias is not None and dias <= 30 else "inverse"),
                  delta_arrow="off", help="Política del boletín BMGFS: emitida en el último mes.")

        if r["veredicto"] == "SIN INDICIOS DE ALTERACIÓN" and not r["cumple_politicas"]:
            st.warning("Es auténtica, pero **no cumple las políticas** (vigencia o estatus): "
                       "pide al cliente una constancia reciente.", icon=":material/event_busy:")

        # --- Observaciones: solo lo que falló o pide revisión ----------------
        fallas = [c for c in r["candados"] if c["estado"] == "FALLA"]
        avisos = [c for c in r["candados"] if c["estado"] == "AVISO"]
        renglon = lambda c: f"- **{c['clave']} {_md(c['titulo'])}** — {_md(c['detalle'])}"  # noqa: E731
        if fallas or avisos:
            st.markdown("**Observaciones**")
            if fallas:
                st.error(f"**{len(fallas)} candado(s) no pasan**\n\n" + "\n".join(map(renglon, fallas)),
                         icon=":material/cancel:")
            if avisos:
                st.warning(f"**{len(avisos)} aviso(s)**\n\n" + "\n".join(map(renglon, avisos)),
                           icon=":material/warning:")
        else:
            st.success("Sin observaciones: todos los candados pasaron.", icon=":material/check_circle:")

        # --- Datos básicos ---------------------------------------------------
        st.markdown("**Datos de la constancia**")
        datos = r["datos"]
        izq, der = st.columns(2)
        for i, k in enumerate(DATOS_PRINCIPALES):
            (izq if i % 2 == 0 else der).markdown(f":gray[{k}]  \n{_md(datos.get(k, '—'))}")
        with st.expander("Más datos", icon=":material/badge:"):
            for k, v in datos.items():
                if k not in DATOS_PRINCIPALES:
                    st.markdown(f":gray[{k}]  \n{_md(v)}")

        # --- QR: validación manual obligatoria (boletín) --------------------
        if r["urls_qr"]:
            st.markdown("**Valida en el SAT** (paso obligatorio del boletín)")
            cols = st.columns(len(r["urls_qr"]))
            for i, (col, url) in enumerate(zip(cols, r["urls_qr"])):
                # Solo se ofrece abrir los QR que van al SAT; el que lleva a
                # otra página se bloquea para que nadie "valide" en el clon.
                if url.startswith("https://siat.sat.gob.mx/"):
                    col.link_button(f"Abrir QR {i + 1} en el SAT", url, icon=":material/qr_code_2:",
                                    width="stretch", type="secondary")
                else:
                    col.button(f"QR {i + 1}: página NO oficial (bloqueado)", icon=":material/dangerous:",
                               disabled=True, width="stretch", key=f"qr_falso_{r['sha256']}_{i}")
            if not all(u.startswith("https://siat.sat.gob.mx/") for u in r["urls_qr"]):
                st.caption(":red[Un QR no lleva a siat.sat.gob.mx: no lo abras para validar, "
                           "es una página que no es del SAT.]")

        # --- Detalle completo de candados -----------------------------------
        with st.expander(f"Todos los candados ({r['total']})", icon=":material/fact_check:",
                         expanded=False):
            for sec, titulo in SECCIONES.items():
                lista = [c for c in r["candados"] if c["seccion"] == sec]
                if not lista:
                    continue
                st.markdown(f"**{sec}. {titulo}**")
                for c in lista:
                    _, ic = ESTADOS[c["estado"]]
                    st.markdown(f":{_color(c['estado'])}[{ic} {c['estado']}] &nbsp; "
                                f"**{c['clave']}** {_md(c['titulo'])}  \n"
                                f":gray[{_md(c['detalle'])}]")
            st.caption(f"Huella SHA-256: {r['sha256']}")
        if r.get("reporte"):
            st.caption(f"Reporte PDF: {r['reporte']} (en Descargas)")
