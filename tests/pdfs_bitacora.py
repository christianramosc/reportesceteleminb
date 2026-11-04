"""PDFs FALSOS de solicitud y amortización, para probar Relación de clientes.

No son copias de los formatos reales (esos traen datos de clientes y no van
al repo, que es público). Reproducen el ACOMODO de los formatos reales
(revisado contra los ZIPs de septiembre y octubre de 2026) del que dependen
las expresiones regulares de herramientas/bitacora_zip.py: etiqueta en una
línea y valor en la de abajo; varias columnas donde el formato real las
tiene; la casilla "GAP: ☐ Contado ☐ Financiado ☐ No" dibujada (no es texto)
y, aparte, el monto del GAP financiado. Si el formato real cambia, estas
pruebas NO lo detectan: detectan que el lector siga haciendo lo que hace hoy.

Todos los nombres, teléfonos y correos son inventados.
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

IZQ, DER = 40, 320          # x de la columna izquierda y derecha
COL1, COL2, COL3 = 40, 200, 360     # renglones de tres columnas
ALTO = letter[1]


# Espacio entre renglones, en puntos. pdfplumber mete una línea en blanco
# cuando el espacio es amplio y pdftotext no; las pruebas usan varios.
INTERLINEADO = 16


def casilla(x, etiqueta, marcada):
    """Cuadrito de 9.6 pt con su etiqueta a la derecha; si está marcada,
    lleva una X de dos líneas DENTRO del cuadro, como el formato real."""
    return ("casilla", x, etiqueta, marcada)


def _pdf(ruta, renglones, interlineado=None):
    """renglones: lista de [(x, texto) | casilla(...), ...]; cada lista es
    una línea."""
    c = canvas.Canvas(str(ruta), pagesize=letter)
    c.setFont("Helvetica", 9)
    c.setLineWidth(0.6)
    y = ALTO - 50
    for renglon in renglones:
        for elemento in renglon:
            if elemento[0] == "casilla":
                _, x, etiqueta, marcada = elemento
                c.rect(x, y - 2, 9.6, 9.6, stroke=1, fill=0)
                if marcada:
                    c.line(x + 0.5, y - 1.5, x + 9.1, y + 7.1)
                    c.line(x + 0.5, y + 7.1, x + 9.1, y - 1.5)
                c.drawString(x + 12, y, etiqueta)
            else:
                x, texto = elemento
                c.drawString(x, y, texto)
        y -= interlineado or INTERLINEADO
    c.save()
    return str(ruta)


def _renglon_vendedor(vendedor):
    """En el real, el No. de vendedor viene pegado a una clave de 3 letras
    ("123456CPc") y luego el nombre."""
    return [
        [(COL1, "No. Punto de venta:"), (COL2, "No. Vendedor:"), (COL3, "Nombre del vendedor:")],
        [(COL1, "1001088160"), (COL2, "123456CPc"), (COL3, vendedor)],
    ]


def solicitud_fisica(ruta, folio, nombres, apellido1, apellido2, nacimiento,
                     fijo, movil, correo, vendedor, actividad_empresarial=False):
    """Forma CTL-008 (persona física; con actividad empresarial = PFAE).

    fijo="" deja sin capturar el teléfono fijo (el móvil y el correo se
    corren de columna en el texto extraído)."""
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
        [(COL1, "Teléfono fijo:"), (COL2, "Teléfono móvil:"), (COL3, "Correo electrónico:")],
        [(COL1, fijo), (COL2, movil), (COL3, correo)],
        [(COL1, "Tipo de residencia:"), (COL3, "Tiempo de residencia (desde año/mes):")],
        *_renglon_vendedor(vendedor),
    ])


def solicitud_fisica_formato_anterior(ruta, folio, lada, movil, correo):
    """Renglón de teléfono "Lada / Teléfono móvil" sin teléfono fijo: lo
    lee la expresión de respaldo de bitacora_zip (la de toda la vida)."""
    return _pdf(ruta, [
        [(IZQ, "CTL-008")],
        [(IZQ, "SOLICITUD DE CRÉDITO - PERSONA FÍSICA")],
        [(IZQ, f"Folio CCK: {folio}")],
        [(IZQ, "Lada:   Teléfono móvil:"), (DER, "Correo electrónico:")],
        [(IZQ, f"{lada}        {movil}"), (DER, correo)],
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
        [(COL1, "Teléfono fijo:"), (COL2, "Teléfono móvil:"), (COL3, "Correo electrónico:")],
        [(COL1, "Tipo de residencia:"), (COL3, "Tiempo de residencia (desde año/mes):")],
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
        [(IZQ, "Teléfono fijo:"), (DER, "Correo electrónico:")],
        [(IZQ, "312 999 0000"), (DER, "representante@ejemplo.com")],
        *_renglon_vendedor(vendedor),
    ])


def amortizacion(ruta, folio, vehiculo="NEW ZS 1.5T COM TURBO EXCITE AT",
                 modelo="2026", precio="420,000.00", enganche_pct="20.00",
                 enganche="84,000.00", gap="9,800.00", plazo="48",
                 tasa="14.99%", monto="358,300.00", mensual_1="10,250.00",
                 mensual_resto="9,870.00", tipo_seguro="Multianual financiado",
                 aseguradora="INBURSA", accesorios="0.00", garantia="12,500.00",
                 solicitante="JUAN CARLOS ARROYO BUSTOS", persona="FÍSICA",
                 casilla_gap="Financiado"):
    """Tabla de amortización. Marca y Vehículo comparten renglón con la
    columna del seguro (Tipo / Aseguradora), como en el formato real.

    casilla_gap: la opción marcada en "GAP: ☐ Contado ☐ Financiado ☐ No";
    None quita la casilla (formato sin ella). El GAP de contado NO se
    financia: va con gap="0.00" y la casilla en "Contado"."""
    if casilla_gap is None:
        renglon_gap = []
    else:
        renglon_gap = [[(IZQ, "GAP:")] + [
            casilla(x, opcion, opcion == casilla_gap)
            for x, opcion in ((88, "Contado"), (142, "Financiado"), (196, "No"))]]
    return _pdf(ruta, [
        [(IZQ, "TABLA DE AMORTIZACIÓN")],
        [(IZQ, f"PERSONA {persona}")],
        [(IZQ, f"Folio CCK: {folio}")],
        [(IZQ, f"Solicitante y/o acreditado: {solicitante}"),
         (420, "No. de contrato del vehículo: 9305560600")],
        [(IZQ, "VEHÍCULO"), (DER, "SEGURO")],
        [(IZQ, "Marca: MG MOTOR"), (DER, f"Tipo: {tipo_seguro}")],
        [(IZQ, f"Vehículo: {vehiculo}"), (DER, f"Aseguradora: {aseguradora}")],
        [(IZQ, f"Modelo: {modelo}"), (DER, "Tipo resto del plazo: Anual")],
        [(IZQ, "Accesorios:")],
        *renglon_gap,
        [(IZQ, "FINANCIAMIENTO")],
        [(IZQ, f"Precio de venta (con IVA): $ {precio}")],
        [(IZQ, f"Enganche*: {enganche_pct}% $ {enganche}")],
        [(IZQ, f"Accesorios (10% máximo): $ {accesorios}")],
        [(IZQ, f"Garantía extendida: $ {garantia}")],
        [(IZQ, f"GAP: $ {gap}")],
        [(IZQ, f"Plazo: {plazo} meses")],
        [(IZQ, f"Tasa de Interés (en términos anuales simples): {tasa}")],
        [(IZQ, f"Monto total a financiar: $ {monto}")],
        [(IZQ, f"Mensualidad con seguro primer año (meses 1-12): $ {mensual_1}")],
        [(IZQ, f"Mensualidad con seguro resto del plazo     $ {mensual_resto}")],
    ])
