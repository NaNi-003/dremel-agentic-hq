import hashlib
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


API_BASE = "https://here.now/api/v1"
TEXT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
}


class HereNowPublishError(RuntimeError):
    pass


def _validate_slug(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
        value,
    ):
        raise HereNowPublishError("here.now site slug is invalid")
    return value


def load_api_key(environ=None, credentials_path=None):
    environ = os.environ if environ is None else environ
    value = environ.get("HERENOW_API_KEY", "").strip()
    if value:
        return value
    path = Path(credentials_path or (Path.home() / ".herenow" / "credentials"))
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HereNowPublishError(
            "No here.now credential found; sign in and save an API key first"
        ) from exc
    if not value:
        raise HereNowPublishError("The here.now credentials file is empty")
    return value


def _content_type(path):
    return TEXT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def collect_site_files(site_dir):
    site_dir = Path(site_dir).resolve()
    if not (site_dir / "index.html").is_file():
        raise HereNowPublishError("Static site is missing index.html")
    manifest = []
    paths = []
    for item in site_dir.rglob("*"):
        if item.is_symlink():
            raise HereNowPublishError("Static site may not contain symlinks")
        if item.is_file():
            resolved = item.resolve()
            if not resolved.is_relative_to(site_dir):
                raise HereNowPublishError("Static site file escapes the site directory")
            paths.append(item)
    for path in sorted(paths, key=lambda item: item.as_posix()):
        data = path.read_bytes()
        manifest.append(
            {
                "path": path.relative_to(site_dir).as_posix(),
                "size": len(data),
                "contentType": _content_type(path),
                "hash": hashlib.sha256(data).hexdigest(),
            }
        )
    return manifest


def _validate_site_url(value):
    if not isinstance(value, str):
        raise HereNowPublishError("here.now did not return a site URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".here.now"):
        raise HereNowPublishError("here.now returned an unexpected site URL")
    return value


def publish_site(site_dir, *, api_key, slug=None, session=None, timeout=60):
    """Create or update an authenticated here.now static site."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise HereNowPublishError("A here.now API key is required for permanent publishing")
    if slug is not None:
        slug = _validate_slug(slug)

    site_dir = Path(site_dir).resolve()
    files = collect_site_files(site_dir)
    client = session or requests.Session()
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "X-HereNow-Client": "dremel-hq",
    }
    payload = {
        "files": files,
        "ttlSeconds": None,
        "viewer": {
            "title": "Dremel Predictive Trend Engine",
            "description": "YouTube opportunity research and content briefing dashboard",
        },
    }
    endpoint = f"{API_BASE}/publish/{slug}" if slug else f"{API_BASE}/publish"
    try:
        if slug:
            response = client.put(endpoint, headers=headers, json=payload, timeout=timeout)
        else:
            response = client.post(endpoint, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        publication = response.json()
        upload = publication["upload"]
        version_id = upload["versionId"]
        upload_items = upload.get("uploads", [])
        if not isinstance(upload_items, list):
            raise TypeError("upload list is invalid")

        by_path = {item["path"]: item for item in files}
        for item in upload_items:
            relative_path = item["path"]
            if relative_path not in by_path:
                raise HereNowPublishError("here.now requested an unknown upload path")
            upload_url = item["url"]
            upload_headers = item.get("headers") or {
                "Content-Type": by_path[relative_path]["contentType"]
            }
            with (site_dir / Path(relative_path)).open("rb") as file_handle:
                uploaded = client.put(
                    upload_url,
                    headers=upload_headers,
                    data=file_handle,
                    timeout=timeout,
                )
            uploaded.raise_for_status()

        finalized = client.post(
            upload["finalizeUrl"],
            headers=headers,
            json={"versionId": version_id},
            timeout=timeout,
        )
        finalized.raise_for_status()
        result = finalized.json()
    except HereNowPublishError:
        raise
    except (OSError, KeyError, TypeError, ValueError, requests.RequestException) as exc:
        raise HereNowPublishError("here.now publication failed") from exc

    if result.get("success") is not True:
        raise HereNowPublishError("here.now did not finalize the publication")
    returned_slug = _validate_slug(result.get("slug") or publication.get("slug"))
    return {
        "slug": returned_slug,
        "site_url": _validate_site_url(result.get("siteUrl") or publication.get("siteUrl")),
        "version_id": result.get("currentVersionId") or version_id,
    }
