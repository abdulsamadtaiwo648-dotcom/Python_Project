"""Escaping of user-controlled text in server templates and the React helper."""

import json
import os
import re
import shutil
import subprocess

import pytest
from jinja2 import Environment

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOSTILE_NAME = 'Ada </script><img src=x onerror=alert(1)> "quoted" \'single\'   back\\slash'


def test_storefront_share_title_is_encoded_for_javascript():
    source = open(os.path.join(REPO_ROOT, "client", "templates", "storefront.html"), encoding="utf-8").read()
    match = re.search(r"title: (\{\{ .*?\}\}),", source)
    assert match, "share title expression not found"
    env = Environment(autoescape=True)
    rendered = env.from_string(match.group(1)).render(profile={"company_name": HOSTILE_NAME})
    # A JSON string literal: it can never end the script block or the string.
    value = json.loads(rendered)
    assert value == HOSTILE_NAME + " Storefront"
    assert "</script" not in rendered
    assert "<img" not in rendered


def test_storefront_share_title_falls_back_when_no_name():
    source = open(os.path.join(REPO_ROOT, "client", "templates", "storefront.html"), encoding="utf-8").read()
    expression = re.search(r"title: (\{\{ .*?\}\}),", source).group(1)
    rendered = Environment(autoescape=True).from_string(expression).render(profile={"company_name": None})
    assert json.loads(rendered) == "SoloBiz Storefront"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the TypeScript helper")
def test_react_escape_helper_encodes_every_html_special_character():
    script = (
        "import { escapeHtml } from './web/src/escape.ts';"
        "const input = process.argv[1];"
        "process.stdout.write(escapeHtml(input));"
    )
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script, HOSTILE_NAME],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    for raw in ("<", ">", '"', "'", "`", "&"):
        assert raw not in out.replace("&amp;", "").replace("&lt;", "").replace("&gt;", "").replace("&quot;", "").replace("&#39;", "").replace("&#96;", ""), raw
    assert "&lt;/script&gt;" in out
    assert "&quot;quoted&quot;" in out
    assert "&#39;single&#39;" in out
