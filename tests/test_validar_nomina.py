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
    # 7 nov 2026 (sáb) -> 16 nov es descanso obligatorio -> lunes 23
    assert v.vence(date(2026, 11, 7)) == date(2026, 11, 23)
    assert v.vence(date(2026, 11, 15)) == date(2026, 11, 30)


def test_periodo_siguiente():
    # semanal 1-7 nov -> la semana 8-14 termina el 14
    assert v.fin_siguiente(date(2026, 11, 1), date(2026, 11, 7), "Semanal") == date(2026, 11, 14)
    # quincenal 1-15 nov -> 30 nov; 16-30 nov -> 15 dic; 16-31 dic -> 15 ene
    assert v.fin_siguiente(date(2026, 11, 1), date(2026, 11, 15), "Quincenal") == date(2026, 11, 30)
    assert v.fin_siguiente(date(2026, 11, 16), date(2026, 11, 30), "Quincenal") == date(2026, 12, 15)
    assert v.fin_siguiente(date(2026, 12, 16), date(2026, 12, 31), "Quincenal") == date(2027, 1, 15)
    # mensual octubre -> 30 nov; diciembre -> 31 ene
    assert v.fin_siguiente(date(2026, 10, 1), date(2026, 10, 31), "Mensual") == date(2026, 11, 30)
    assert v.fin_siguiente(date(2026, 12, 1), date(2026, 12, 31), "Mensual") == date(2027, 1, 31)


def _quincenas(montos, desde=(2026, 9, 16)):
    import calendar as cal
    y, m, d = desde
    out = []
    for monto in montos:
        if d == 1:
            ini, fin = date(y, m, 1), date(y, m, 15)
            d = 16
        else:
            ini, fin = date(y, m, 16), date(y, m, cal.monthrange(y, m)[1])
            y, m, d = (y + 1, 1, 1) if m == 12 else (y, m + 1, 1)
        out.append({"inicio": ini, "fin": fin, "percepciones": monto, "estado_sat": v.ESTADO_OK, "nombre": ""})
    return out


def test_quincenal_vigente_mientras_no_se_paga_la_siguiente():
    # trae hasta 1-15 nov; la 16-30 nov termina el 30: vale hasta el 14 de dic
    p = v.analizar_persona(_quincenas([8400, 8100, 8400, 8250]), hoy=date(2026, 11, 30))
    assert p["siguiente_fin"] == date(2026, 11, 30)
    assert p["vence"] == date(2026, 12, 14)
    assert p["habiles_restantes"] == 10
    p = v.analizar_persona(_quincenas([8400, 8100, 8400, 8250]), hoy=date(2026, 12, 15))
    assert p["habiles_restantes"] < 0


def test_ingreso_mensual_es_el_mes_mas_bajo():
    p = v.analizar_persona(_quincenas([8400, 8100, 8400, 8250]), hoy=date(2026, 11, 30))
    assert p["bruto_mes1"] == 16500.0 and p["bruto_mes2"] == 16650.0
    assert p["ingreso_mensual"] == 16500.0
    assert not any("mínimo" in a for a in p["avisos"])
    bajo = v.analizar_persona(_quincenas([3100, 3100, 3500, 3500]), hoy=date(2026, 11, 30))
    assert bajo["ingreso_mensual"] == 6200.0
    assert any("no llega al mínimo" in a for a in bajo["avisos"])


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
    # último recibo 8-14 nov -> la semana 15-21 termina el 21 -> vale hasta el viernes 4 de dic
    assert p["siguiente_fin"] == date(2026, 11, 21) and p["vence"] == date(2026, 12, 4)
    assert any("Falta el periodo" in a for a in p["avisos"])
    assert p["bruto_mes1"] + p["bruto_mes2"] == 8000.0
