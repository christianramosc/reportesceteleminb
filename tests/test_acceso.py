"""Acceso privado: hash de contraseña y validación de credenciales."""

from herramientas import acceso


def test_hash_verifica_y_rechaza():
    h = acceso.generar_hash("una-contrasena-larga", iteraciones=1000)
    assert acceso.verificar_hash("una-contrasena-larga", h)
    assert not acceso.verificar_hash("otra", h)


def test_hash_malformado_no_truena():
    assert not acceso.verificar_hash("x", "no-es-un-hash")
    assert not acceso.verificar_hash("x", "")


def test_credenciales():
    conf = {"usuario": "Christian", "hash": acceso.generar_hash("clave-de-prueba-123", iteraciones=1000)}
    assert acceso.credenciales_validas("christian", "clave-de-prueba-123", conf)
    assert not acceso.credenciales_validas("otro", "clave-de-prueba-123", conf)
    assert not acceso.credenciales_validas("christian", "mal", conf)


def test_sin_configuracion_queda_cerrado():
    assert not acceso.credenciales_validas("a", "b", {})
    assert not acceso.credenciales_validas("a", "b", {"usuario": "a"})
