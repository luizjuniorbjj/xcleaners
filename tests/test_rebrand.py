"""Rebrand verification tests."""
import os
import glob
from pathlib import Path

# Resolve the project root relative to this test file (tests/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_no_cleanclaw_in_python_files():
    """No 'cleanclaw' references in Python source files."""
    app_dir = PROJECT_ROOT / "app"
    python_files = list(app_dir.glob("**/*.py"))
    python_files.append(PROJECT_ROOT / "xcleaners_main.py")

    violations = []
    for filepath in python_files:
        if not filepath.exists():
            continue
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()
            if 'cleanclaw' in content:
                violations.append(str(filepath))

    assert violations == [], f"Files still contain 'cleanclaw': {violations}"


def test_entry_point_renamed():
    """Entry point is xcleaners_main.py, not cleanclaw_main.py."""
    assert (PROJECT_ROOT / "xcleaners_main.py").exists()
    assert not (PROJECT_ROOT / "cleanclaw_main.py").exists()


def test_dockerfile_references_xcleaners():
    """Dockerfile references xcleaners_main, not cleanclaw_main."""
    dockerfile = PROJECT_ROOT / "Dockerfile"
    with open(dockerfile, 'r') as f:
        content = f.read()
    assert "xcleaners_main" in content
    assert "cleanclaw_main" not in content
