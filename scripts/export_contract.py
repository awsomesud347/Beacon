import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.contract_export import OPENAPI_PATH, SSE_EXAMPLE_PATH, write_all  # noqa: E402

if __name__ == "__main__":
    write_all()
    print(f"wrote {OPENAPI_PATH}")
    print(f"wrote {SSE_EXAMPLE_PATH}")
