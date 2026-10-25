"""Keep test projects and the synthetic catalog separate from user documents."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
_REGISTRY = tempfile.TemporaryDirectory(prefix='latex-local-tests-')
os.environ['LATEX_PROJECTS_DIR'] = _REGISTRY.name

@pytest.fixture(autouse=True)
def synthetic_catalog(monkeypatch, request):
    import references
    import doi_lookup
    path = ROOT / 'tests/fixtures/reference_catalog.json'
    monkeypatch.setattr(references, 'CATALOG', path)
    monkeypatch.setattr(doi_lookup, 'CATALOG', path)
    if hasattr(request.module, 'CATALOG'):
        monkeypatch.setattr(request.module, 'CATALOG', path)
