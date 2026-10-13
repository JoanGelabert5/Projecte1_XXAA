"""Lista explícita de archivos entregables: nunca incluir los .env privados."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
output = root / "dist" / "practica1.zip"
output.parent.mkdir(exist_ok=True)
names = [
    "README.md", "Dockerfile", "Makefile", "requirements.txt", "run.sh",
    "docker-compose.dev.yml", "docker-compose.prod.yml",
    ".env.dev.example", ".env.prod.example", ".gitignore", ".dockerignore",
]
files = [root / name for name in names]
for folder in ("app", "db", "scripts", "tests", "docs"):
    files.extend(path for path in (root / folder).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, Path("practica1") / path.relative_to(root))
print(f"Creado: {output.relative_to(root)}")
