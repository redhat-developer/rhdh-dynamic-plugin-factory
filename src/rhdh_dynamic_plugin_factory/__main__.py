"""
Main entry point for the RHDH Plugin Factory CLI.
"""

import sys
from pathlib import Path
try:
    from .cli import main  # For module execution
except ImportError:
    # For direct directory execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rhdh_dynamic_plugin_factory.cli import main
    
if __name__ == "__main__":
    main()

