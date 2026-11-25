"""Validar nómina SAT con textos SINTÉTICOS (el repo es público: aquí no
van recibos reales). Cubre los dos formatos conocidos: recibo semanal con
'Del ... al ...' y tarjetón quincenal del IMSS ('Período de pago: 1A-SEP-2026')."""

from datetime import date

from herramientas import validar_nomina_sat as v

SEMANAL = """Folio Fiscal 11111111-2222-3333-4444-555555555555
Periodo Del 2026-11-01 al 2026-11-07
RFC EMP010101AB1 receptor PEPJ900101AB2
Total de Percepciones $5,000.00
Total: 2,500.00
||1.1|11111111-2222-3333-4444-555555555555|2026-11-10T10:00:00|PAC010101AB3|SELLO==|00001||"""

IMSS = """Emisor RFC: IMS421231I45
Período de pago: 2A-SEP-2026
Nombre: PERSONA DE PRUEBA Pases de salida: 0
RFC: PEPJ900101AB2
Total Percepciones 14,509.38 Total Deducciones 5,472.38
Líquido 9,037.00
Folio Fiscal: 66666666-7777-8888-9999-000000000000
||1.0||66666666-7777-8888-9999-000000000000|2026-09-11T08:29:12|SELLO=="""


def test_lee_recibo_semanal():
    d = v.datos_de_texto("a.pdf", SEMANAL)
    assert d["uuid"] == "11111111-2222-3333-4444-555555555555"
    assert (d["rfc_emisor"], d["rfc_receptor"]) == ("EMP010101AB1", "PEPJ900101AB2")   # sin el PAC
    assert (d["percepciones"], d["total"]) == (5000.00, 2500.00)
    assert (d["inicio"], d["fin"]) == (date(2026, 11, 1), date(2026, 11, 7))


def test_lee_tarjeton_imss():
    d = v.datos_de_texto("b.pdf", IMSS)
    assert (d["rfc_emisor"], d["rfc_receptor"]) == ("IMS421231I45", "PEPJ900101AB2")
    assert (d["inicio"], d["fin"]) == (date(2026, 9, 16), date(2026, 9, 30))
    assert (d["percepciones"], d["total"]) == (14509.38, 9037.00)
    assert d["nombre"] == "PERSONA DE PRUEBA"


def test_xml():
    xml = b'''<cfdi:Comprobante Total="7431.81"><cfdi:Emisor Rfc="IMS421231I45"/>
    <cfdi:Receptor Rfc="PEPJ900101AB2" Nombre="PERSONA"/>
    <nomina12:Nomina FechaInicialPago="2026-09-16" FechaFinalPago="2026-09-30" TotalPercepciones="14509.38"/>
    <tfd:TimbreFiscalDigital UUID="66666666-7777-8888-9999-000000000000"/></cfdi:Comprobante>'''
    d = v.datos_de_xml("c.xml", xml)
    assert d["total"] == 7431.81 and d["percepciones"] == 14509.38
    assert d["fin"] == date(2026, 9, 30)


def test_codigos_sat():
    r = lambda cod, est: f"<a:CodigoEstatus>{cod}</a:CodigoEstatus><a:Estado>{est}</a:Estado>"   # noqa: E731
    assert v.interpretar(r("S - Comprobante obtenido satisfactoriamente.", "Vigente"))["estado_sat"] == v.ESTADO_OK
    assert v.interpretar(r("N - 601: La expresión impresa proporcionada no es válida.", "No Encontrado"))["estado_sat"] == v.ESTADO_NO_COINCIDE
    assert v.interpretar(r("N - 602: Comprobante no encontrado.", "No Encontrado"))["estado_sat"] == v.ESTADO_NO_EXISTE


def test_consulta_sin_red_no_truena():
    d = v.datos_de_texto("a.pdf", SEMANAL)

    def falla(_):
        raise OSError("sin red")
    assert v.consultar(d, soap=falla)["estado_sat"] == v.ESTADO_ERROR


def test_vigencia_10_habiles_salta_dia_inhabil():
    # 7 nov 2026 (sáb) -> 16 nov es descanso obligatorio -> vence el lunes 23
    assert v.vence(date(2026, 11, 7)) == date(2026, 11, 23)
    # 1A-NOV (fin 15 nov) -> 30 nov
    assert v.vence(date(2026, 11, 15)) == date(2026, 11, 30)


def test_analisis_semanal_toma_8_y_detecta_hueco():
    recibos = []
    inicio = date(2026, 9, 13)
    for i in range(9):
        if i == 4:
            continue                      # falta una semana
        ini = date.fromordinal(inicio.toordinal() + 7 * i)
        recibos.append({"inicio": ini, "fin": date.fromordinal(ini.toordinal() + 6),
                        "percepciones": 1000.0, "estado_sat": v.ESTADO_OK, "nombre": ""})
    p = v.analizar_persona(recibos, hoy=date(2026, 11, 24))
    assert p["frecuencia"] == "Semanal" and len(p["seleccion"]) == 8
    assert any("Falta el periodo" in a for a in p["avisos"])
    assert p["bruto_mes1"] + p["bruto_mes2"] == 8000.0
