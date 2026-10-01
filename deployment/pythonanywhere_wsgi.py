"""Paste this into the WSGI configuration linked from PythonAnywhere's Web tab."""
import sys
from pathlib import Path

project_home = Path.home() / 'artha-finance'
if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))

from backend.app import app as application
