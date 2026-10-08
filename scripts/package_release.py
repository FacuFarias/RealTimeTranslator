"""Create portable/source ZIPs after validation; omit build and cache artifacts."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def add_tree(archive, directory, prefix):
    for path in sorted(directory.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            archive.write(path, str(Path(prefix) / path.relative_to(directory)))


def package():
    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(DIST / "Traductor-Portable.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        add_tree(archive, DIST / "Traductor", "Traductor")
    with zipfile.ZipFile(DIST / "Traductor-Proyecto.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in ("README.md", "VALIDATION.md", "pyproject.toml", "requirements.lock.txt", "models.lock.json", "Traductor.spec", "main.py", ".gitignore"):
            archive.write(ROOT / name, "Traductor-Proyecto/" + name)
        for name in ("translator", "scripts", "tests", "diagnostics", "licenses", "validation"):
            add_tree(archive, ROOT / name, "Traductor-Proyecto/" + name)
    print("ZIPs creados: Traductor-Portable.zip y Traductor-Proyecto.zip", flush=True)


if __name__ == "__main__":
    package()
