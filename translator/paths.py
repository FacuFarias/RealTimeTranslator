import os
import sys
from pathlib import Path

EXECUTABLE_ROOT = Path(sys.executable).parent
ROOT = EXECUTABLE_ROOT if getattr(sys, "frozen", False) or (EXECUTABLE_ROOT / "models" / "manifest.json").exists() else Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
# Configure before importing Argos. Never use its global user model cache.
os.environ["ARGOS_PACKAGES_DIR"] = str(MODELS / "argos")
os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
os.environ["ARGOS_MODEL_PROVIDER"] = "OPENNMT"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
