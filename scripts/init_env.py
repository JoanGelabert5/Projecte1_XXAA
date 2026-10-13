"""Genera configuración privada sin sobreescribir archivos existentes."""
from pathlib import Path
import os
import secrets

root = Path(__file__).resolve().parent.parent
for environment in ("dev", "prod"):
    target = root / f".env.{environment}"
    template = (root / f".env.{environment}.example").read_text()
    lines = []
    for line in template.splitlines():
        key, separator, value = line.partition("=")
        if value == "GENERAR":
            value = secrets.token_hex(24)
        lines.append(key + separator + value)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{target.name}: ya existe, no se modifica.")
        continue
    with os.fdopen(descriptor, "w") as stream:
        stream.write("\n".join(lines) + "\n")
    print(f"{target.name}: creado con contraseñas aleatorias y permisos 600.")
