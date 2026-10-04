import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calendar_core import db

@pytest.fixture
def con(tmp_path): return db.connect(str(tmp_path / "t.db"))
