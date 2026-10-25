"""Every local script and stylesheet web/index.html loads is copied into the site, whatever attributes its tag has."""
import importlib.util
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_site():
    spec = importlib.util.spec_from_file_location("build_site", os.path.join(ROOT, "scripts", "build_site.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_page_script_is_shipped():
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    scripts, styles = _build_site().page_assets(html)
    wanted = set(re.findall(r'<script src="([\w.-]+\.js)"', html))
    assert wanted and wanted <= set(scripts), wanted - set(scripts)
    assert set(re.findall(r'<link rel="stylesheet" href="([\w.-]+\.css)"', html)) <= set(styles)


def test_deferred_scripts_found():
    scripts, _ = _build_site().page_assets('<script src="app.js"></script><script src="mascot.js" defer></script>')
    assert "mascot.js" in scripts and "app.js" in scripts
