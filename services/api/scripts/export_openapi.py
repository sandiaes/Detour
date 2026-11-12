"""Write the OpenAPI contract to packages/shared/openapi.json (or the path given as argument).

The contract is generated from the application with fixed settings, so the output does not
depend on the machine or its environment.
"""

import json
import sys
from pathlib import Path

from detour_api.main import create_app
from detour_api.settings import Settings

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "packages" / "shared" / "openapi.json"


def contract_text() -> str:
    app = create_app(Settings(environment="test", log_level="WARNING"))
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contract_text(), encoding="utf-8")
    print(f"wrote {target}")
