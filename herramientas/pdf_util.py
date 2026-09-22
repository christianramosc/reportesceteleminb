# -*- coding: utf-8 -*-
"""Utilidades de maquetación compartidas por los cuatro reportes."""

from reportlab.platypus import PageBreak, Spacer


def quitar_espacios_antes_de_salto(elementos):
    """Quita los Spacer que quedan justo antes de un PageBreak.

    Un espacio antes de un salto de página no separa nada: el salto ya lo
    hace. Y cuando la página anterior terminó exactamente llena, ese espacio
    no cabe, ReportLab abre una página nueva solo para él y enseguida el
    PageBreak abre otra. Resultado: una hoja en blanco que depende de cuánto
    texto traiga el mes (así apareció en el Resumen Mensual de julio, con los
    focos de atención llenando la página 2).

    Se compara el tipo exacto y no isinstance: CondPageBreak hereda de
    Spacer y ese sí debe conservarse.
    """
    limpio = []
    for elemento in elementos:
        if isinstance(elemento, PageBreak):
            while limpio and type(limpio[-1]) is Spacer:
                limpio.pop()
        limpio.append(elemento)
    return limpio
