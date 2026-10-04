import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE = os.path.join(ROOT, "reference")           # committed, bundled data
DATA = os.environ.get("CALENDAR_DATA_DIR", os.path.join(ROOT, "data"))
CACHE = os.path.join(DATA, "cache")                   # fetched at runtime (persistent volume)
def first_existing(*paths):
    return next((p for p in paths if os.path.exists(p)), None)
