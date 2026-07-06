# -*- coding: utf-8 -*-
"""Thin GitHub Git Data API client (QGIS-touching).

Used by :mod:`publisher` to commit a published dashboard. The Git Data API
(blobs -> tree -> commit -> ref) is used instead of the Contents API because it
makes an **atomic** multi-file commit and accepts files up to 100 MB (the
Contents API caps at 1 MB, and dashboards routinely exceed that).

All requests go through ``QgsNetworkAccessManager`` (so QGIS proxy/SSL settings
apply) via ``sendCustomRequest`` — one uniform path for GET/POST/PATCH — blocked
on a local event loop with a timeout. Errors surface as :class:`PublishError`
with a plain, user-facing message.
"""

import json

from qgis.PyQt.QtCore import QUrl, QByteArray, QEventLoop, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import QgsNetworkAccessManager

from .github_publish import parse_repo

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "QGIS-Dashboard-Plugin"
TIMEOUT_MS = 30000


class PublishError(Exception):
    """A publish failure with a message safe to show the user."""


class GitHubClient:
    def __init__(self, token, repo, branch="main"):
        self._token = (token or "").strip()
        self._owner, self._name = parse_repo(repo)
        self._branch = (branch or "main").strip() or "main"
        if not self._token:
            raise PublishError("No GitHub token set.")

    @property
    def branch(self):
        return self._branch

    # ---- transport ------------------------------------------------------

    def _url(self, path):
        return "{}/repos/{}/{}/{}".format(
            API_ROOT, self._owner, self._name, path.lstrip("/"))

    def _request(self, method, path, body=None, accept="application/vnd.github+json"):
        """Send one request; return ``(status_code, raw_bytes)``.

        Raises :class:`PublishError` only on transport-level failure (no reply);
        HTTP error *status codes* are returned for the caller to interpret.
        """
        nam = QgsNetworkAccessManager.instance()
        request = QNetworkRequest(QUrl(self._url(path)))
        request.setRawHeader(b"Authorization", b"Bearer " + self._token.encode())
        request.setRawHeader(b"Accept", accept.encode())
        request.setRawHeader(b"X-GitHub-Api-Version", API_VERSION.encode())
        request.setRawHeader(b"User-Agent", USER_AGENT.encode())
        if body is not None:
            request.setRawHeader(b"Content-Type", b"application/json")

        payload = QByteArray(body if body is not None else b"")
        reply = nam.sendCustomRequest(request, method.encode(), payload)

        loop = QEventLoop()
        reply.finished.connect(loop.quit)
        timer = QTimer()
        timer.setSingleShot(True)
        timed_out = {"value": False}

        def _on_timeout():
            timed_out["value"] = True
            reply.abort()

        timer.timeout.connect(_on_timeout)
        timer.start(TIMEOUT_MS)
        loop.exec()
        timer.stop()

        err = reply.error()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        data = bytes(reply.readAll())
        reply.deleteLater()

        if timed_out["value"]:
            raise PublishError("GitHub did not respond in time. Check your "
                               "connection and try again.")
        # A transport error with no HTTP status = network/proxy/SSL problem.
        if err != QNetworkReply.NetworkError.NoError and status is None:
            raise PublishError(
                "Couldn't reach GitHub ({}). Check your internet connection or "
                "QGIS proxy settings.".format(reply.errorString() or err))
        return int(status or 0), data

    def _json(self, method, path, body_obj=None, accept="application/vnd.github+json"):
        """Request expecting a JSON object back; interpret common error codes."""
        body = None
        if body_obj is not None:
            body = json.dumps(body_obj).encode("utf-8")
        status, data = self._request(method, path, body=body, accept=accept)
        self._raise_for_status(status, data, path)
        try:
            return json.loads(data.decode("utf-8")) if data else {}
        except (ValueError, UnicodeDecodeError):
            raise PublishError("GitHub returned an unexpected response.")

    def _raise_for_status(self, status, data, path):
        if 200 <= status < 300:
            return
        if status == 401:
            raise PublishError(
                "GitHub rejected your token (401). It may be wrong or expired — "
                "set a fresh fine-grained token in the Publish dialog.")
        if status == 403:
            raise PublishError(
                "GitHub refused the request (403). Your token likely lacks "
                "'Contents: read and write' on this repository, or you hit a "
                "rate limit. Try again shortly.")
        if status == 404:
            raise PublishError(
                "Repository or branch not found (404): {}/{}@{}. Check the name "
                "and that your token can access it.".format(
                    self._owner, self._name, self._branch))
        # surface GitHub's own message when present
        msg = ""
        try:
            msg = json.loads(data.decode("utf-8")).get("message", "")
        except Exception:
            pass
        raise PublishError("GitHub error {} on {}{}".format(
            status, path, ": " + msg if msg else "."))

    # ---- Git Data API primitives ---------------------------------------

    def head_commit_sha(self):
        """Latest commit sha on the target branch."""
        ref = self._json("GET", "git/ref/heads/{}".format(self._branch))
        return ref["object"]["sha"]

    def commit_tree_sha(self, commit_sha):
        commit = self._json("GET", "git/commits/{}".format(commit_sha))
        return commit["tree"]["sha"]

    def read_text_file(self, repo_path):
        """Return a repo file's text, or ``""`` if it doesn't exist (404)."""
        status, data = self._request(
            "GET", "contents/{}?ref={}".format(repo_path, self._branch),
            accept="application/vnd.github.raw")
        if status == 404:
            return ""
        self._raise_for_status(status, data, repo_path)
        return data.decode("utf-8")

    def create_blob_base64(self, content_b64):
        """Create a blob from base64 content; return its sha."""
        blob = self._json("POST", "git/blobs",
                          {"content": content_b64, "encoding": "base64"})
        return blob["sha"]

    def create_tree(self, base_tree_sha, items):
        tree = self._json("POST", "git/trees",
                          {"base_tree": base_tree_sha, "tree": items})
        return tree["sha"]

    def create_commit(self, message, tree_sha, parent_sha):
        commit = self._json("POST", "git/commits",
                            {"message": message, "tree": tree_sha,
                             "parents": [parent_sha]})
        return commit["sha"]

    def update_branch_ref(self, commit_sha):
        self._json("PATCH", "git/refs/heads/{}".format(self._branch),
                   {"sha": commit_sha, "force": False})
