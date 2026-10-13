"""Prueba real ejecutada dentro del contenedor web; no usa dependencias extra."""
import json
import os
import time
import urllib.request


def request(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:5000" + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.status, json.load(response)


_, status = request("/status")
assert status["status"] == "healthy", status
print("PASS: servicios saludables")
text = f"Prueba automática {time.time_ns()}"
code, created = request("/api/notes", {"content": text})
assert code == 201 and created["note"]["content"] == text, created
_, first = request("/api/notes")
assert any(note["id"] == created["note"]["id"] for note in first["notes"]), first
assert first["source"] == "postgresql", first
print("PASS: escritura y lectura en PostgreSQL")
_, second = request("/api/notes")
if os.getenv("CACHE_ENABLED", "false").lower() == "true":
    assert first["cache"] == "miss", first
    assert second["source"] == "redis" and second["cache"] == "hit", second
    print("PASS: invalidación al escribir y siguiente lectura desde Redis")
else:
    assert second["source"] == "postgresql" and second["cache"] == "disabled", second
    assert status["services"]["cache"] == "not_configured", status
    print("PASS: desarrollo sin Redis")
print("Ejecutar sin otras consultas simultáneas y con TTL suficiente (30 s por defecto).")
