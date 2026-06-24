"""Pytest config — register asyncio mode + ensure 'spec' and 'executor' are importable."""
import sys
from pathlib import Path

# Add the project root to sys.path so `import spec` / `import executor` works
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
