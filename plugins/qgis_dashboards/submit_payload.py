# -*- coding: utf-8 -*-
"""Pure (Qt-free) helpers for the *Publish to public* flow.

The plugin publishes straight to Supabase now: the dashboard's files go into
the public ``dashboards`` storage bucket and one metadata row goes into the
``dashboards`` table (see ``submit_client`` for the QGIS-touching HTTP side).
There is no GitHub, no Pull Request and no 4 MB Vercel body cap anymore — the
only size limit is the bucket's per-file cap, mirrored here.

Everything in this module is plain Python so it unit-tests under a bare
``PYTHONPATH`` (run ``test/test_submit_payload.py`` directly).
"""

import re
import unicodedata
from urllib.parse import quote

# Mirror the dashboards bucket's file_size_limit (50 MB) so the user gets an
# actionable message client-side instead of an opaque storage rejection.
MAX_HTML_BYTES = 50 * 1024 * 1024

# Mirror the dashboards table's check constraints.
MAX_TITLE = 200
MAX_AUTHOR = 120
MAX_DESC = 400

# How many "slug", "slug-2", "slug-3", … candidates to try before giving up.
MAX_SLUG_ATTEMPTS = 25

VIEW_BASE_URL = "https://qgis.byzenterra.org/qdashboards/view"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title, fallback="dashboard"):
    """Return a URL-safe slug for *title*.

    Lowercase, accents stripped, non-alphanumeric runs collapsed to single
    hyphens, trimmed. Empty/symbol-only titles fall back to *fallback*.
    Mirrors lib/submit-core.mjs:slugify so plugin and site agree.
    """
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = _SLUG_STRIP.sub("-", text.lower()).strip("-")
    return text or fallback


def candidate_slug(base, attempt):
    """The *attempt*-th slug candidate: ``base``, ``base-2``, ``base-3``, …"""
    return base if attempt == 0 else "{}-{}".format(base, attempt + 1)


def object_key(slug, name):
    """An object's key inside the dashboards bucket, e.g. ``<slug>/index.html``."""
    return "{}/{}".format(slug, name)


def storage_path(slug, name):
    """The bucket-qualified path recorded in the table (what the site turns
    into a public URL), e.g. ``dashboards/<slug>/index.html``."""
    return "dashboards/{}".format(object_key(slug, name))


def view_url(slug):
    """The public viewer URL for a published *slug* (mirrors lib/site.ts:viewUrl)."""
    return "{}?d={}".format(VIEW_BASE_URL, quote(slug))


def build_row(slug, title, author, description, html_bytes_len, has_thumb=True):
    """The dashboards-table insert body for one published dashboard."""
    row = {
        "slug": slug,
        "title": (title or slug)[:MAX_TITLE],
        "author": (author or "").strip()[:MAX_AUTHOR] or None,
        "html_path": storage_path(slug, "index.html"),
        "thumb_path": storage_path(slug, "thumb.png") if has_thumb else None,
        "html_bytes": html_bytes_len,
    }
    desc = (description or "").strip()
    if desc:
        row["description"] = desc[:MAX_DESC]
    return row


def exceeds_size_limit(html_bytes):
    """True if the HTML is over the bucket's per-file cap (boundary inclusive:
    exactly at the cap is still accepted)."""
    return len(html_bytes) > MAX_HTML_BYTES
