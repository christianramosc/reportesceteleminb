"""PDFs FALSOS de solicitud y amortización, para probar Relación de clientes.

No son copias de los formatos reales (esos traen datos de clientes y no van
al repo, que es público). Reproducen el ACOMODO del que dependen las
expresiones regulares de herramientas/bitacora_zip.py: etiqueta en una línea
y valor en la de abajo, y dos columnas (izquierda en x=40, derecha en x=320)
donde el formato real las tiene. Si el formato real cambia, estas pruebas NO
lo detectan: detectan que el lector siga haciendo lo que hace hoy.

Todos los nombres, teléfonos y correos son inventados.
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

IZQ, DER = 40, 320          # x de la columna izquierda y derecha
ALTO = letter[1]


# Espacio entre renglones, en puntos. pdfplumber mete una línea en blanco
# cuando el espacio es amplio y pdftotext no; las pruebas usan varios.
INTERLINEADO = 16


def _pdf(ruta, renglones, interlineado=None):
    """renglones: lista de [(x, texto), ...]; cada lista es una línea."""
    c = canvas.Canvas(str(ruta), pagesize=letter)
    c.setFont("Helvetica", 9)
    y = ALTO - 50
    for renglon in renglones:
        for x, texto in renglon:
            c.drawString(x, y, texto)
        y -= interlineado or INTERLINEADO
    c.save()
    return str(ruta)


def solicitud_fisica(ruta, folio, nombres, apellido1, apellido2, nacimiento,
                     lada, movil, correo, vendedor, actividad_empresarial=False):
    """Forma CTL-008 (persona física; con actividad empresarial = PFAE)."""
    titulo = ("SOLICITUD DE CRÉDITO - PERSONA FÍSICA CON ACTIVIDAD EMPRESARIAL"
              if actividad_empresarial else "SOLICITUD DE CRÉDITO - PERSONA FÍSICA")
    return _pdf(ruta, [
        [(IZQ, "CTL-008")],
        [(IZQ, titulo)],   # en su propia línea: no cabe en la columna derecha
        [(IZQ, f"Folio CCK: {folio}")],
        [(IZQ, "Datos del solicitante")],
        [(IZQ, "Nombre(s):")],
        [(IZQ, nombres)],
        [(IZQ, "Primer apellido:"), (DER, "Segundo apellido:")],
        [(IZQ, apellido1), (DER, apellido2)],
        [(IZQ, "Fecha de nacimiento(dd/mm/aaaa):"), (DER, "RFC:")],
        [(IZQ, nacimiento), (DER, "XAXX010101000")],
        [(IZQ, "Lada:   Teléfono móvil:"), (DER, "Correo electrónico:")],
        [(IZQ, f"{lada}        {movil}"), (DER, correo)],
        [(IZQ, "Nombre del vendedor:")],
        [(IZQ, f"1234   MGCOL   {vendedor}")],
    ])


def solicitud_fisica_en_blanco(ruta, folio):
    """La misma forma sin capturar: debajo de cada etiqueta viene otra
    etiqueta, no un valor (el lector devolvía "P" de "Primer apellido")."""
    return _pdf(ruta, [
        [(IZQ, "CTL-008"), (DER, "SOLICITUD DE CRÉDITO - PERSONA FÍSICA")],
        [(IZQ, f"Folio CCK: {folio}")],
        [(IZQ, "Nombre(s):")],
        [(IZQ, "Primer apellido:"), (DER, "Segundo apellido:")],
        [(IZQ, "Fecha de nacimiento(dd/mm/aaaa):"), (DER, "RFC:")],
    ])


def solicitud_moral(ruta, folio, razon_social, constitucion, telefono, correo,
                    vendedor, representante=("PEDRO", "LUNA", "SOTO")):
    """Forma CTL-022 (persona moral). Incluye el bloque del representante
    legal, que tiene Nombre(s)/apellidos como el de persona física: el
    cliente debe ser la razón social, no el representante."""
    nombre_rep, ap1_rep, ap2_rep = representante
    return _pdf(ruta, [
        [(IZQ, "CTL-022"), (DER, "SOLICITUD DE CRÉDITO - PERSONA MORAL")],
        [(IZQ, f"Folio CCK: {folio}")],
        [(IZQ, "Denominación o razón social:"), (DER, "Nacionalidad:")],
        [(IZQ, razon_social), (DER, "MEXICANA")],
        [(IZQ, "Fecha de constitución (dd/mm/aaaa):"), (DER, "RFC:")],
        [(IZQ, constitucion), (DER, "TPA150201AB1")],
        [(IZQ, "Teléfono fijo:"), (DER, "Correo electrónico:")],
        [(IZQ, telefono), (DER, correo)],
        [(IZQ, "Datos del representante legal")],
        [(IZQ, "Nombre(s):")],
        [(IZQ, nombre_rep)],
        [(IZQ, "Primer apellido:"), (DER, "Segundo apellido:")],
        [(IZQ, ap1_rep), (DER, ap2_rep)],
        [(IZQ, "Nombre del vendedor:")],
        [(IZQ, f"1234   MGCOL   {vendedor}")],
    ])


def amortizacion(ruta, folio, vehiculo="NEW ZS 1.5T COM TURBO EXCITE AT",
                 modelo="2026", precio="420,000.00", enganche_pct="20.00",
                 enganche="84,000.00", gap="9,800.00", plazo="48",
                 tasa="14.99%", monto="358,300.00", mensual_1="10,250.00",
                 mensual_resto="9,870.00", tipo_seguro="Multianual financiado",
                 aseguradora="INBURSA", accesorios="0.00", garantia="12,500.00"):
    """Tabla de amortización. Marca y Vehículo comparten renglón con la
    columna del seguro (Tipo / Aseguradora), como en el formato real."""
    return _pdf(ruta, [
        [(IZQ, "TABLA DE AMORTIZACIÓN")],
        [(IZQ, f"Folio CCK: {folio}")],
        [(IZQ, "VEHÍCULO"), (DER, "SEGURO")],
        [(IZQ, "Marca: MG MOTOR"), (DER, f"Tipo: {tipo_seguro}")],
        [(IZQ, f"Vehículo: {vehiculo}"), (DER, f"Aseguradora: {aseguradora}")],
        [(IZQ, f"Modelo: {modelo}"), (DER, "Tipo resto del plazo: Anual")],
        [(IZQ, f"Precio de venta (con IVA): $ {precio}")],
        [(IZQ, f"Enganche*: {enganche_pct}% $ {enganche}")],
        [(IZQ, "FINANCIAMIENTO")],
        [(IZQ, f"Accesorios (10% máximo): $ {accesorios}")],
        [(IZQ, f"Garantía extendida: $ {garantia}")],
        [(IZQ, f"GAP: $ {gap}")],
        [(IZQ, f"Plazo: {plazo} meses")],
        [(IZQ, f"Tasa de Interés (en términos anuales simples): {tasa}")],
        [(IZQ, f"Monto total a financiar: $ {monto}")],
        [(IZQ, f"Mensualidad con seguro primer año (meses 1-12): $ {mensual_1}")],
        [(IZQ, f"Mensualidad con seguro resto del plazo     $ {mensual_resto}")],
    ])
