"""Copy dependency notices and model licenses into the portable distribution."""
from importlib import metadata
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "licenses"
OUT.mkdir(exist_ok=True)
records = []
for dist in metadata.distributions():
    name = dist.metadata["Name"]
    records.append(f"{name} {dist.version} — {dist.metadata.get('License', 'Ver avisos incluidos')}\n{dist.metadata.get('Home-page', '')}")
    for file in dist.files or []:
        if "license" in file.name.lower() or "copying" in file.name.lower() or "notice" in file.name.lower():
            source = Path(dist.locate_file(file))
            if source.is_file():
                target = OUT / name / str(file).replace("..", "_").replace(":", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
for name, url in {
    "Whisper-MIT.txt": "https://raw.githubusercontent.com/openai/whisper/main/LICENSE",
    "Argos-MIT.txt": "https://raw.githubusercontent.com/argosopentech/argos-translate/v1.9.6/LICENSE",
}.items():
    urllib.request.urlretrieve(url, OUT / name)
for readme in (ROOT / "models" / "argos").glob("*/README*"):
    shutil.copy2(readme, OUT / ("Modelo-Argos-" + readme.name))
(OUT / "THIRD_PARTY.txt").write_text("Bibliotecas del entorno de compilación (algunas no se distribuyen)\n\n" + "\n\n".join(sorted(records)), encoding="utf-8")
print(f"Avisos recopilados en {OUT}")
