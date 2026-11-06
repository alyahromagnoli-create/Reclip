"""Writable portable data stays beside the executable, on any drive."""
from pathlib import Path
import sys

def database_path(name,executable=None,frozen=None,module_file=None):
    frozen=getattr(sys,'frozen',False) if frozen is None else frozen
    base=Path(executable or sys.executable).parent if frozen else Path(module_file or __file__).resolve().parents[1]
    return base/'data'/f'{name}.db'
