import sys
from pathlib import Path

import pytest

# Tests import the app package from the repository root regardless of the
# directory pytest was started from.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    """Point thrown files at a temp dir for every test.

    The production default is the docker volume (``/data/throws``), which a
    test run must never touch and usually cannot create. Patching the module
    default rather than every ``Settings(...)`` in the suite keeps the file
    store out of tests that have nothing to do with files — they still build an
    app, and building an app makes the directory.
    """
    import app.main

    monkeypatch.setattr(app.main, "DEFAULT_FILES_DIR", str(tmp_path / "throws"))
