import json
from pathlib import Path

_FILE = Path(__file__).parent / "settings.json"

_DEFAULTS = {
    "filter_aktiv": True,
    "filter_pausiert": True,
    "filter_vermittelt": True,
}


def load() -> dict:
    if _FILE.exists():
        try:
            with open(_FILE, encoding="utf-8") as f:
                return {**_DEFAULTS, **json.load(f)}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(data: dict) -> None:
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
