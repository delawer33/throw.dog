import sys
from pathlib import Path

# Tests import the app package from the repository root regardless of the
# directory pytest was started from.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
