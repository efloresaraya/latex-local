"""Exercise the portable CLI and release defaults in an isolated registry."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_links_and_compiles_from_another_working_directory(tmp_path):
    source = tmp_path / 'document with spaces'
    source.mkdir()
    (source / 'main.tex').write_text(r'\documentclass{article}\begin{document}Portable example.\end{document}')
    registry = tmp_path / 'registry with spaces'
    env = dict(os.environ, LATEX_PYTHON=sys.executable, LATEX_PROJECTS_DIR=str(registry))
    cli = str(ROOT / 'latex-cli')
    created = subprocess.run([cli, 'new', str(source), '--name', 'Portable'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert created.returncode == 0, created.stderr
    config = subprocess.run([cli, 'config', 'Portable'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert config.returncode == 0, config.stderr
    assert json.loads(config.stdout)['linked_path'] == str(source)
    compiled = subprocess.run([cli, 'compile', 'Portable'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    assert (source / 'main.pdf').is_file()
    assert list((source / '.latex-local/snapshots').glob('*.zip'))


def test_release_starts_without_private_catalog():
    assert json.loads((ROOT / 'backend/reference_catalog.json').read_text()) == []


def test_web_launcher_rejects_an_invalid_port(tmp_path):
    env = dict(os.environ, LATEX_PYTHON=sys.executable, LATEX_PORT='0')
    result = subprocess.run([str(ROOT / 'start.sh')], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'LATEX_PORT' in result.stderr
