"""
The scrapers import the backend's `app` package (URL safety, the deadline rules, the models), as
the pipelines do after putting both directories on the path themselves. CI runs a bare
`pytest ../scrapers/tests` from backend/, and backend/pytest.ini's `pythonpath` does not apply to a
path outside backend/, so the tests do the same here.
"""
from pathlib import Path
import sys

_REPO = Path(__file__).resolve().parents[2]
for _path in (_REPO, _REPO / "backend"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
