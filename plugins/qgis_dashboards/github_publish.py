# -*- coding: utf-8 -*-
"""Pure (Qt-free) logic for the *Publish to public* feature.

Everything here is plain Python so it unit-tests under a bare ``PYTHONPATH``
without QGIS/Qt (run ``test/test_github_publish.py`` directly). The QGIS-touching
half — rendering the thumbnail and talking to GitHub — lives in
:mod:`github_client` and :mod:`publisher`.

The website and the plugin meet at one contract: ``public/dashboards/manifest.json``,
an array of entries shaped like :func:`build_entry`. The plugin commits a
dashboard's ``index.html`` + ``thumb.png`` under ``public/dashboards/<slug>/`` and
upserts its manifest entry; the website's gallery reads it.
"""

import json
import re
import unicodedata

# Default gallery target (overridable in the publish dialog). The website and
# its public/dashboards/ store now live in the QGIS-Plugins monorepo, served at
# the /qdashboards route segment of the hub.
DEFAULT_REPO = "isaacenage/QGIS-Plugins"
DEFAULT_BRANCH = "main"
PUBLIC_BASE_URL = "https://qgis.byzenterra.org/qdashboards"

# Where published assets live in the website repo (relative to repo root).
DASHBOARDS_ROOT = "public/dashboards"
MANIFEST_PATH = "public/dashboards/manifest.json"
# Paths recorded *inside* manifest.json are relative to public/ (the web root).
MANIFEST_REL_ROOT = "dashboards"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title, fallback="dashboard"):
    """Return a URL-safe slug for *title*.

    Lowercase, accents stripped, non-alphanumeric runs collapsed to single
    hyphens, trimmed. Empty/symbol-only titles fall back to *fallback*.
    """
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = _SLUG_STRIP.sub("-", text.lower()).strip("-")
    return text or fallback


def asset_repo_path(slug, name):
    """Path of an asset in the website repo, e.g. ``public/dashboards/<slug>/index.html``."""
    return "{}/{}/{}".format(DASHBOARDS_ROOT, slug, name)


def asset_manifest_path(slug, name):
    """Path recorded in manifest.json (relative to public/), e.g. ``dashboards/<slug>/index.html``."""
    return "{}/{}/{}".format(MANIFEST_REL_ROOT, slug, name)


def public_view_url(slug, base=PUBLIC_BASE_URL):
    """The public viewer URL for a published *slug* (mirrors lib/site.ts:viewUrl)."""
    from urllib.parse import quote
    return "{}/view?d={}".format(base.rstrip("/"), quote(slug))


def build_entry(slug, title, author, date, description=None):
    """A single manifest entry. *date* is an ISO ``YYYY-MM-DD`` string."""
    entry = {
        "slug": slug,
        "title": title or slug,
        "author": author or "",
        "date": date,
        "path": asset_manifest_path(slug, "index.html"),
        "thumb": asset_manifest_path(slug, "thumb.png"),
    }
    if description:
        entry["description"] = description
    return entry


def manifest_upsert(entries, entry):
    """Return a NEW list with *entry* added or replaced by matching ``slug``.

    Existing entries keep their position (a re-publish updates in place); a new
    slug is appended. The input list is never mutated (immutable update).
    """
    slug = entry.get("slug")
    out = []
    replaced = False
    for existing in entries:
        if existing.get("slug") == slug:
            out.append(dict(entry))
            replaced = True
        else:
            out.append(existing)
    if not replaced:
        out.append(dict(entry))
    return out


def parse_manifest(raw_text):
    """Decode manifest JSON tolerantly: a missing/blank/non-list payload is ``[]``."""
    if not raw_text or not raw_text.strip():
        return []
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def merge_manifest(raw_text, entry):
    """Upsert *entry* into the manifest *raw_text*; return ``(new_text, is_update)``.

    *new_text* is pretty-printed JSON ending in a newline (clean git diffs).
    """
    entries = parse_manifest(raw_text)
    existing_slugs = {e.get("slug") for e in entries}
    merged = manifest_upsert(entries, entry)
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    return text, entry.get("slug") in existing_slugs


def tree_items(blob_specs):
    """Build a Git Data API tree array from ``[(repo_path, blob_sha), ...]``.

    Every item is a normal (non-executable) file blob.
    """
    return [
        {"path": path, "mode": "100644", "type": "blob", "sha": sha}
        for path, sha in blob_specs
    ]


def parse_repo(repo):
    """Split ``"owner/name"`` into ``(owner, name)``; raise ``ValueError`` if malformed."""
    parts = (repo or "").strip().strip("/").split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            "Repository must be in 'owner/name' form, e.g. isaacenage/QGIS-Plugins")
    return parts[0], parts[1]


def estimate_committed_bytes(*raw_byte_lengths):
    """Rough size of the commit's blobs once base64-encoded (~+33%)."""
    return int(sum(raw_byte_lengths) * 4 / 3)
