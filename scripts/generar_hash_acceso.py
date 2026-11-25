"""Genera el hash de la contraseña para la sección [acceso_privado] de los
Secrets de Streamlit. La contraseña no se guarda en ningún lado.

    python scripts/generar_hash_acceso.py

Copia lo que imprime en Streamlit Cloud > Manage app > Settings > Secrets
(y, para probar en tu máquina, en .streamlit/secrets.toml, que git ignora).
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from herramientas.acceso import generar_hash  # noqa: E402

usuario = input("Usuario: ").strip()
c1 = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
c2 = getpass.getpass("Repítela: ")
if c1 != c2:
    sys.exit("No coinciden.")
if len(c1) < 12:
    sys.exit("Usa al menos 12 caracteres.")
print("\nPega esto en Secrets:\n")
print("[acceso_privado]")
print(f'usuario = "{usuario}"')
print(f'hash = "{generar_hash(c1)}"')
