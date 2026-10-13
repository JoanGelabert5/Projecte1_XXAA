"""Pruebas de integración: ejecutar sobre un entorno de esta práctica ya arrancado.

Crea una nota, recrea el contenedor db sin borrar su volumen y simula caídas.
No ejecutar en paralelo con otras pruebas ni cambios en el entorno.
"""
import json
import subprocess
import sys
import time
import uuid

environment = sys.argv[1]
if environment not in ("dev", "prod"):
    raise SystemExit("Entorno válido: dev o prod")


def compose(*args, capture=False):
    return subprocess.run(
        ["./run.sh", "compose", environment, *args],
        check=True, text=True, capture_output=capture,
    ).stdout


def api(path, payload=None):
    # Se ejecuta dentro de web: sin librerías externas ni lectura de contraseñas.
    code = '''
import json, sys, urllib.request, urllib.error
path, payload = json.loads(sys.argv[1])
body = None if payload is None else json.dumps(payload).encode()
request = urllib.request.Request("http://127.0.0.1:5000" + path, data=body,
    headers={"Content-Type": "application/json"})
try:
    response = urllib.request.urlopen(request, timeout=12)
except urllib.error.HTTPError as error:
    response = error
with response:
    print(json.dumps({"code": response.code, "data": json.load(response)}))
'''
    return json.loads(compose("exec", "-T", "web", "python", "-c", code,
                              json.dumps([path, payload]), capture=True))


def wait_healthy():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = api("/status")
        if state["code"] == 200:
            return
        time.sleep(2)
    raise AssertionError("Los servicios no se recuperaron en 90 segundos")


assert api("/status")["code"] == 200, "Primero arranca el entorno"
config = json.loads(compose("config", "--format", "json", capture=True))
assert config["networks"]["backend"]["internal"] is True
for service, settings in config["services"].items():
    if service != "web":
        assert not settings.get("ports"), f"Puerto publicado por {service}"
    assert settings.get("healthcheck"), f"Falta healthcheck: {service}"
print("PASS: configuración de redes, puertos y healthchecks", flush=True)

marker = "Persistencia " + uuid.uuid4().hex
created = api("/api/notes", {"content": marker})
assert created["code"] == 201, created
note_id = created["data"]["note"]["id"]

try:
    compose("stop", "db")
    state = api("/status")
    assert state["code"] == 503 and state["data"]["services"]["database"] == "disconnected", state
    print("PASS: caída real de PostgreSQL detectada", flush=True)
    compose("rm", "-f", "db")
    compose("up", "-d", "--wait", "db")
    wait_healthy()
    # Consultar SQL directamente evita que Redis falsee la prueba de persistencia.
    query = f"SELECT content FROM notes WHERE id = {int(note_id)}"
    stored = compose("exec", "-T", "db", "sh", "-c",
                     'PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U "$DB_USER" '
                     '-d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc "$1"',
                     "sh", query, capture=True).strip()
    assert stored == marker, stored
    print("PASS: nota conservada tras eliminar y recrear el contenedor db", flush=True)

    if environment == "prod":
        # Una escritura invalida la lista antes de comprobar miss/hit.
        assert api("/api/notes", {"content": "Caché " + uuid.uuid4().hex})["code"] == 201
        first = api("/api/notes")
        second = api("/api/notes")
        assert first["data"]["cache"] == "miss", first
        assert second["data"]["cache"] == "hit", second
        print("PASS: lectura PostgreSQL seguida de lectura Redis", flush=True)
        compose("stop", "cache")
        state = api("/status")
        assert state["code"] == 503 and state["data"]["services"]["cache"] == "disconnected", state
        fallback = api("/api/notes")
        assert fallback["code"] == 200 and fallback["data"]["source"] == "postgresql", fallback
        print("PASS: caída Redis detectada; consulta alternativa en PostgreSQL", flush=True)
        compose("up", "-d", "--wait", "cache")
        wait_healthy()
finally:
    dependencies = ["db", "cache"] if environment == "prod" else ["db"]
    compose("up", "-d", "--wait", *dependencies)

print(f"PASS: integración {environment} terminada; nota de persistencia #{note_id}", flush=True)
