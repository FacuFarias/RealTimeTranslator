from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class Segment:
    id: int
    source: str
    start: float
    end: float
    original: str
    translated: str


def timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"


def export_text(path: Path, created: datetime, segments: list[Segment]) -> None:
    lines = ["Traductor local — inglés → español", f"Sesión: {created.isoformat(sep=' ', timespec='seconds')}", ""]
    for seg in sorted(segments, key=lambda s: (s.start, s.id)):
        lines.extend([
            f"[{timestamp(seg.start)} — {timestamp(seg.end)}] {seg.source}",
            f"Inglés: {seg.original}", f"Español: {seg.translated}", "",
        ])
    # Atomic replacement avoids a truncated export if writing fails.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_text("\n".join(lines), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
