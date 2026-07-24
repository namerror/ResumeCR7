from __future__ import annotations

import importlib
import sys

if __name__ == "__main__":
    from app.resume_generation.main import main

    raise SystemExit(main())
else:
    _main = importlib.import_module("app.resume_generation.main")

    sys.modules[__name__] = _main
