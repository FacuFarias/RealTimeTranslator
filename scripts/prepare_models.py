"""Build-time downloads only. The finished app never calls this script."""
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile
from packaging.version import Version
import requests

ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
MODELS = ROOT / "models"
os.environ["ARGOS_PACKAGES_DIR"] = str(MODELS / "argos")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from huggingface_hub import HfApi, snapshot_download
import argostranslate.package
sys.path.insert(0, str(ROOT))
from translator.translation import LocalTranslation


def prepare():
    MODELS.mkdir(exist_ok=True)
    manifest = {"models": []}
    manifest_file = MODELS / "manifest.json"
    lock_file = ROOT / "models.lock.json"
    previous_file = lock_file if lock_file.exists() else manifest_file
    previous = json.loads(previous_file.read_text(encoding="utf-8")) if previous_file.exists() else {"models": []}
    pinned = {entry["name"]: entry for entry in previous["models"]}
    api = HfApi()
    for name in ("small.en", "base.en"):
        repo = f"Systran/faster-whisper-{name}"
        revision = pinned[name]["revision"] if name in pinned else api.model_info(repo).sha
        print(f"Descargando {name} ({revision})…", flush=True)
        snapshot_download(repo, revision=revision, local_dir=MODELS / name,
                          allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
        manifest["models"].append({"name": name, "repository": repo, "revision": revision})
    request = urllib.request.Request("https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json")
    with urllib.request.urlopen(request, timeout=60) as response:
        index = json.load(response)
    package = max((p for p in index if p["from_code"] == "en" and p["to_code"] == "es"), key=lambda p: Version(p["package_version"]))
    if "en_es" in pinned:
        package = {"package_version": pinned["en_es"]["version"], "links": [pinned["en_es"]["url"]]}
    argos_file = MODELS / "en_es.argosmodel"
    print(f"Descargando ingles a espanol ({package['package_version']})...", flush=True)
    urls = [u for u in package["links"] if u.startswith("https://")]
    # Official historical CDN is a fallback when argos-net rejects a request.
    urls.append("https://pub-dbae765fb25a4114aac1c88b90e94178.r2.dev/v1/translate-en_es-1_0.argosmodel")
    for url in urls:
        try:
            with requests.get(url, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                with argos_file.open("wb") as output:
                    for block in response.iter_content(1024 * 1024):
                        output.write(block)
            package["links"][0] = url
            break
        except requests.RequestException:
            if url == urls[-1]:
                raise
            print("Probando el CDN alternativo de Argos...", flush=True)
    actual_hash = hashlib.sha256(argos_file.read_bytes()).hexdigest()
    if "en_es" in pinned and actual_hash != pinned["en_es"]["sha256"]:
        raise RuntimeError("El paquete Argos no coincide con el hash fijado en manifest.json.")
    argostranslate.package.install_from_path(argos_file)
    manifest["models"].append({"name": "en_es", "version": package["package_version"], "url": package["links"][0], "sha256": actual_hash})
    print(LocalTranslation(MODELS).translate("Hello. This application works without an internet connection."), flush=True)
    (MODELS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    argos_file.unlink()


if __name__ == "__main__":
    prepare()
