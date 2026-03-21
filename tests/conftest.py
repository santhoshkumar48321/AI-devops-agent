"""
tests/conftest.py - Shared pytest fixtures.
"""

import os
import sys
import pytest

# Ensure the repo root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Provide dummy env vars so Settings can be instantiated without a real .env
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("MEMORY_DIR", "/tmp/test_memory")
os.environ.setdefault("DOCS_OUTPUT_DIR", "/tmp/test_docs")
os.environ.setdefault("AUDIT_LOG_PATH", "/tmp/test_audit.log")
