# -*- coding: utf-8 -*-
"""Assemble the final single-file ``index.html``.

Inlines the theme CSS variables, the structural runtime CSS, the dashboard
markup shell, the embedded JSON data model, and the runtime JS — in that order
— into one self-contained document that opens offline by double-click.

The data is embedded in a ``<script type="application/json">`` block (read with
``JSON.parse`` at runtime, never fetched, so it works under ``file://``). The
JSON is escaped so it cannot terminate the script element early.

``build_html`` is pure (given the asset strings); :func:`load_assets` does the
file I/O of reading the bundled runtime, kept separate so the assembly is
unit-testable without touching disk.
"""

import json
import os

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _read_asset(name):
    with open(os.path.join(ASSETS_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def load_assets():
    """Return ``(runtime_css, runtime_js, leaflet_css, leaflet_js)``."""
    return (_read_asset("runtime.css"), _read_asset("runtime.js"),
            _read_asset("leaflet.css"), _read_asset("leaflet.js"))


def _escape_html(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def embed_json(model):
    """Serialize *model* for safe embedding in a ``<script>`` element.

    ``</`` is neutralized so the JSON can never close the script tag early, and
    U+2028 / U+2029 (valid in JSON but illegal in JS string literals) are
    stripped so the embedded data parses everywhere.
    """
    text = json.dumps(model, ensure_ascii=False, default=str)
    text = text.replace("</", "<\\/")
    text = text.replace(chr(0x2028), " ").replace(chr(0x2029), " ")
    return text


def build_html(
        model,
        css_vars,
        runtime_css,
        runtime_js,
        leaflet_css="",
        leaflet_js="",
        title="Dashboard",
        font_faces=""):
    """Return the complete ``index.html`` document as a string.

    Leaflet's CSS is inlined before the runtime CSS, and its JS in a dedicated
    ``<script>`` before the runtime ``<script>`` so ``L`` is defined when the
    runtime executes. *font_faces* (an ``@font-face`` block for embedded custom
    fonts) is inlined before ``css_vars`` so the families exist when the
    ``:root`` ``--font-family`` variables reference them.
    """
    data_json = embed_json(model)
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>{}</title>".format(_escape_html(title)),
        "<style>",
        font_faces,
        css_vars,
        leaflet_css,
        runtime_css,
        "</style>",
        "</head>",
        "<body>",
        '<div id="app"></div>',
        '<script type="application/json" id="dashboard-data">',
        data_json,
        "</script>",
        "<script>",
        leaflet_js,
        "</script>",
        "<script>",
        runtime_js,
        "</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)
