"""Acceso con usuario y contraseña para herramientas privadas.

Por qué existe
--------------
La app está publicada en Streamlit Community Cloud y el repo es público.
Algunas herramientas (ej. Validar nómina SAT) procesan datos personales y
solo debe usarlas el encargado de financiamiento. Una herramienta que declara
requiere_acceso=True (registro.py) muestra primero este formulario.

Dónde vive la contraseña
------------------------
NUNCA en el repo. Se guarda en los "Secrets" de Streamlit Cloud
(Manage app > Settings > Secrets), y en local en .streamlit/secrets.toml
(ignorado por git). Solo se guarda el HASH de la contraseña, no la
contraseña:

    [acceso_privado]
    usuario = "christian"
    hash = "pbkdf2_sha256$600000$<sal_hex>$<hash_hex>"

El hash se genera con:  python scripts/generar_hash_acceso.py

Protecciones
------------
- Comparación en tiempo constante (hmac.compare_digest).
- 5 intentos fallidos bloquean el formulario 5 minutos en esa sesión, y
  20 fallos en 10 minutos (sumando todas las sesiones, por si alguien
  recarga la página para reiniciar el contador) lo bloquean para todos.
- Si no hay secrets configurados, la herramienta queda cerrada (no se
  "abre por default").
- La sesión expira tras 30 minutos sin usar la herramienta.
"""

import hashlib
import hmac
import secrets as _secrets
import time

ITERACIONES = 600_000
MAX_INTENTOS = 5
BLOQUEO_SEG = 5 * 60
EXPIRA_SEG = 30 * 60
MAX_FALLOS_GLOBAL = 20
VENTANA_GLOBAL_SEG = 10 * 60

# Compartido por todas las sesiones del mismo proceso del servidor.
_fallos_globales: list = []


def _bloqueo_global(ahora: float) -> bool:
    _fallos_globales[:] = [t for t in _fallos_globales if ahora - t < VENTANA_GLOBAL_SEG]
    return len(_fallos_globales) >= MAX_FALLOS_GLOBAL


# ---------------------------------------------------------------------------
# Hash (sin Streamlit: se prueba en tests/test_acceso.py)
# ---------------------------------------------------------------------------
def generar_hash(contrasena: str, iteraciones: int = ITERACIONES, sal: bytes | None = None) -> str:
    sal = sal or _secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, iteraciones)
    return f"pbkdf2_sha256${iteraciones}${sal.hex()}${dk.hex()}"


def verificar_hash(contrasena: str, guardado: str) -> bool:
    try:
        algoritmo, iteraciones, sal_hex, hash_hex = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"),
                                 bytes.fromhex(sal_hex), int(iteraciones))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def credenciales_validas(usuario: str, contrasena: str, conf: dict) -> bool:
    """Valida contra la sección [acceso_privado] de los secrets."""
    if not conf or not conf.get("usuario") or not conf.get("hash"):
        return False
    ok_usuario = hmac.compare_digest(usuario.strip().lower(), str(conf["usuario"]).strip().lower())
    ok_contrasena = verificar_hash(contrasena, str(conf["hash"]))
    return ok_usuario and ok_contrasena


# ---------------------------------------------------------------------------
# Formulario (Streamlit)
# ---------------------------------------------------------------------------
def _config():
    import streamlit as st
    try:
        return dict(st.secrets.get("acceso_privado", {}))
    except Exception:   # no hay secrets.toml en absoluto
        return {}


def exigir(id_herramienta: str) -> bool:
    """Devuelve True si la sesión ya tiene acceso. Si no, dibuja el
    formulario y devuelve False (el que llama debe hacer st.stop())."""
    import streamlit as st

    estado = st.session_state.setdefault("_acceso", {"ok_hasta": 0.0, "fallos": 0, "bloqueo_hasta": 0.0})
    ahora = time.time()

    if estado["ok_hasta"] > ahora:
        estado["ok_hasta"] = ahora + EXPIRA_SEG          # renueva mientras se usa
        izq, der = st.columns([3, 1])
        izq.caption(":material/lock_open: Herramienta privada: sesión iniciada.")
        if der.button("Cerrar sesión", key=f"salir_{id_herramienta}", icon=":material/logout:"):
            estado["ok_hasta"] = 0.0
            st.rerun()
        return True

    conf = _config()
    with st.container(border=True, key=f"acceso_{id_herramienta}"):
        st.markdown("#### :material/lock: Herramienta privada")
        if not conf.get("usuario") or not conf.get("hash"):
            st.error("Esta herramienta todavía no tiene acceso configurado. "
                     "Agrega la sección [acceso_privado] en los Secrets de la app.",
                     icon=":material/key_off:")
            return False

        if estado["bloqueo_hasta"] > ahora or _bloqueo_global(ahora):
            minutos = int((estado["bloqueo_hasta"] - ahora) // 60) + 1
            st.error(f"Demasiados intentos. Vuelve a intentar en {minutos} min.",
                     icon=":material/timer:")
            return False

        with st.form(f"form_acceso_{id_herramienta}", clear_on_submit=True, border=False):
            usuario = st.text_input("Usuario", autocomplete="username")
            contrasena = st.text_input("Contraseña", type="password", autocomplete="current-password")
            entrar = st.form_submit_button("Entrar", type="primary", icon=":material/login:")

        if entrar:
            if credenciales_validas(usuario, contrasena, conf):
                estado.update(ok_hasta=ahora + EXPIRA_SEG, fallos=0, bloqueo_hasta=0.0)
                st.rerun()
            estado["fallos"] += 1
            _fallos_globales.append(ahora)
            if estado["fallos"] >= MAX_INTENTOS:
                estado.update(fallos=0, bloqueo_hasta=ahora + BLOQUEO_SEG)
                st.error("Demasiados intentos. El acceso se bloqueó 5 minutos.", icon=":material/timer:")
            else:
                st.error("Usuario o contraseña incorrectos.", icon=":material/error:")
    return False
