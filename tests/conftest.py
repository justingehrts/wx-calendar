import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calendar_core import db

@pytest.fixture(params=["sqlite", "libsql"])
def con(tmp_path, request):
    """Every test using `con` runs against both storage drivers (libsql in local-file mode)."""
    return db.connect(str(tmp_path / f"t_{request.param}.db"), libsql=(request.param == "libsql"))
