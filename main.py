from __future__ import annotations

import json
from pathlib import Path

from src.modeling import run_pipeline


if __name__ == "__main__":
    result = run_pipeline(Path(__file__).resolve().parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
