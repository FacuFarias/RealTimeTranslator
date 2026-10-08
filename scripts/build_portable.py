"""Package with an unmodified, officially signed CPython GUI runtime.

PyInstaller still performs dependency analysis/collection. Its unsigned launcher
is retained separately. No signing certificates or Windows policies are changed.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
EMBED_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"


def build():
    source = ROOT / "dist" / "Traductor-PyInstaller" / "_internal"
    if not source.exists():
        raise RuntimeError("Primero compila Traductor.spec con PyInstaller.")
    target = ROOT / "dist" / "Traductor"
    target.mkdir(exist_ok=True)
    archive = ROOT / ".tools" / "python-embed.zip"
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        urllib.request.urlretrieve(EMBED_URL, archive)
    with zipfile.ZipFile(archive) as package:
        package.extractall(target)
    shutil.copytree(source, target / "_internal", dirs_exist_ok=True)
    analysis = ast.literal_eval((ROOT / "build" / "Traductor" / "Analysis-00.toc").read_text(encoding="utf-8"))
    count = 0
    for section in analysis:
        if not isinstance(section, list):
            continue
        for entry in section:
            if not isinstance(entry, tuple) or len(entry) != 3 or entry[2] != "PYMODULE":
                continue
            name, filename, _ = entry
            if not filename:
                continue
            original = Path(filename)
            # Standard library comes from the official runtime ZIP. Collect the
            # application/dependencies from PyInstaller's analyzed module set.
            if "site-packages" not in original.parts and not original.is_relative_to(ROOT / "translator"):
                continue
            relative = Path(*name.split("."))
            relative = relative / "__init__.py" if original.name == "__init__.py" else relative.with_suffix(".py")
            destination = target / "_internal" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
            count += 1
    shutil.copy2(ROOT / "main.py", target / "main.py")
    shutil.copy2(target / "pythonw.exe", target / "Traductor.exe")
    (target / "python311._pth").write_text("python311.zip\n.\n_internal\nimport site\n", encoding="utf-8")
    # With a script argument CPython handles CLI diagnostics normally. With no
    # arguments (double click), sitecustomize opens the GUI and exits cleanly.
    (target / "sitecustomize.py").write_text('''import os
import sys
if len(sys.orig_argv) == 1:
    try:
        from main import main
        code = main()
    except BaseException:
        import traceback
        from pathlib import Path
        import ctypes
        path = Path(sys.executable).parent / "error-inicio.log"
        path.write_text(traceback.format_exc(), encoding="utf-8")
        ctypes.windll.user32.MessageBoxW(None, "No se pudo abrir Traductor. Consulta error-inicio.log en la carpeta de la aplicación.", "Traductor local", 0x10)
        code = 1
    os._exit(code)
''', encoding="utf-8")
    for directory in ("models", "licenses", "diagnostics", "validation"):
        shutil.copytree(ROOT / directory, target / directory, dirs_exist_ok=True)
    shutil.copy2(ROOT / "README.md", target / "README.md")
    shutil.copy2(ROOT / "VALIDATION.md", target / "VALIDATION.md")
    shutil.copy2(ROOT / "scripts" / "Probar-Compatibilidad.cmd", target / "Probar-Compatibilidad.cmd")
    shutil.copy2(ROOT / "scripts" / "benchmark.py", target / "diagnostics" / "benchmark.py")
    shutil.copy2(ROOT / "scripts" / "capture_smoke.py", target / "diagnostics" / "capture_smoke.py")
    shutil.copy2(target / "LICENSE.txt", target / "licenses" / "CPython-3.11.9.txt")
    (target / "runtime-manifest.json").write_text(json.dumps({"packaging": "official-embedded-cpython", "python": "3.11.9", "url": EMBED_URL, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "collected_python_modules": count}, indent=2), encoding="utf-8")
    print(f"Portable preparada: {target}", flush=True)


if __name__ == "__main__":
    build()
