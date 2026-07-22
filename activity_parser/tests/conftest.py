import sys
from pathlib import Path

# All modules in activity_parser/ use flat imports ("import parser", "from
# staleness import ...") rather than package-relative ones, so tests need
# the parent directory on sys.path regardless of where pytest is invoked
# from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
