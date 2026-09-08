# -*- coding: utf-8 -*-
"""
Piezas compartidas por las pruebas.

Las pruebas NO usan bitácoras reales: arman un Excel sintético con las
mismas columnas que exporta el sistema. Así se pueden correr en cualquier
máquina, no dependen de datos de clientes y los totales son conocidos de
antemano (que es lo que permite verificar los cálculos).
"""

import os
import random

import matplotlib
matplotlib.use("Agg")          # sin pantalla: las pruebas no abren ventanas

import pandas as pd
import pytest

VENDEDORES = ["Ana Ruiz", "Luis Mora", "Sofia Paz", "Diego Lara"]
MODELOS = ["MG 5", "MG ZS", "MG HS"]

# Los 14 estatus del catálogo, escritos como podrían venir del Excel real
# (con variantes de mayúsculas y plurales, a propósito).
ESTATUS_DE_PRUEBA = [
    "FINANCIADO", "financiados", "APROBADO", "CONTRAPROPUESTA",
    "EXCEPCIONES", "VALIDACION INTERNA", "EN PROCESO", "EN REVISION",
    "ANALISIS", "Documentacion Adicional", "PENDIENTE", "SONDEO",
    "NO FINANCIABLE", "RECHAZADO", "CANCELADO",
]


def construir_bitacora(estatus=None, n=60, semilla=7):
    """DataFrame con la forma de la bitácora real."""
    estatus = estatus or ESTATUS_DE_PRUEBA
    rnd = random.Random(semilla)
    filas = []
    for i in range(n):
        st = estatus[i % len(estatus)]
        precio = rnd.randint(280, 520) * 1000
        enganche = int(precio * rnd.uniform(0.10, 0.35))
        tiene_gap = "SI" if i % 2 == 0 else "NO"
        filas.append({
            "Folio CCK": f"CCK{i:04d}",
            "STATUS": st,
            "Nombre Completo": f"Cliente {i}",
            "Fecha de Nacimiento": "01/01/1990",
            "Teléfono Móvil": "9931234567",
            "Correo Electrónico": f"cliente{i}@ejemplo.com",
            "Nombre del Vendedor": VENDEDORES[i % len(VENDEDORES)],
            "Marca": "MG",
            "Vehículo": MODELOS[i % len(MODELOS)],
            "Año Modelo": 2026,
            "Precio Venta (c/IVA)": precio,
            "Enganche": enganche,
            "¿Tiene GAP?": tiene_gap,
            "Monto GAP": 12000 if tiene_gap == "SI" else 0,
            "Plazo (meses)": 48,
            "Tasa Interés Anual": round(rnd.uniform(0.12, 0.21), 4),
            "Monto Total a Financiar": precio - enganche,
            "Mensualidad Mínima": 8000,
            "Mensualidad Máxima": 12000,
        })
    return pd.DataFrame(filas)


@pytest.fixture
def bitacora_excel(tmp_path):
    """Excel con los 14 estatus. Devuelve la ruta."""
    ruta = tmp_path / "bitacora.xlsx"
    construir_bitacora().to_excel(ruta, index=False)
    return str(ruta)


@pytest.fixture
def bitacora_clasica_excel(tmp_path):
    """Excel con solo los 4 estatus originales, para comprobar que los
    reportes no se rompieron al ampliar el catálogo."""
    ruta = tmp_path / "bitacora_clasica.xlsx"
    construir_bitacora(
        estatus=["FINANCIADO", "APROBADO", "CONTRAPROPUESTA", "RECHAZADO"],
        n=40,
    ).to_excel(ruta, index=False)
    return str(ruta)
