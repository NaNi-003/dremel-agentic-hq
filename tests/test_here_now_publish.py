import hashlib
from pathlib import Path

import here_now_publish
import pytest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url == "https://here.now/api/v1/publish":
            files = kwargs["json"]["files"]
            return FakeResponse(
                {
                    "slug": "dremel-demo",
                    "siteUrl": "https://dremel-demo.here.now/",
                    "upload": {
                        "versionId": "version-1",
                        "finalizeUrl": "https://here.now/api/v1/publish/dremel-demo/finalize",
                        "uploads": [
                            {
                                "path": item["path"],
                                "url": f"https://uploads.example/{item['path']}",
                                "headers": {"Content-Type": item["contentType"]},
                            }
                            for item in files
                        ],
                        "skipped": [],
                    },
                }
            )
        return FakeResponse(
            {
                "success": True,
                "slug": "dremel-demo",
                "siteUrl": "https://dremel-demo.here.now/",
                "currentVersionId": "version-1",
            }
        )

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return FakeResponse({})


def test_collect_site_files_returns_posix_manifest_with_hashes(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<h1>Dremel</h1>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")

    files = here_now_publish.collect_site_files(tmp_path)

    assert [item["path"] for item in files] == ["assets/app.js", "index.html"]
    index = next(item for item in files if item["path"] == "index.html")
    assert index["contentType"] == "text/html; charset=utf-8"
    assert index["hash"] == hashlib.sha256(b"<h1>Dremel</h1>").hexdigest()


def test_collect_site_files_rejects_symlink_escape(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>Dremel</h1>", encoding="utf-8")
    secret = tmp_path / "outside.txt"
    secret.write_text("do not publish", encoding="utf-8")
    try:
        (site / "outside.txt").symlink_to(secret)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows host")

    with pytest.raises(here_now_publish.HereNowPublishError, match="symlink"):
        here_now_publish.collect_site_files(site)


def test_publish_site_uploads_and_finalizes_authenticated_site(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Dremel</h1>", encoding="utf-8")
    session = FakeSession()

    result = here_now_publish.publish_site(
        tmp_path,
        api_key="test-key-not-a-real-secret",
        session=session,
    )

    assert result == {
        "slug": "dremel-demo",
        "site_url": "https://dremel-demo.here.now/",
        "version_id": "version-1",
    }
    create = session.calls[0]
    assert create[0:2] == ("POST", "https://here.now/api/v1/publish")
    assert create[2]["headers"]["Authorization"] == "Bearer test-key-not-a-real-secret"
    assert any(call[0] == "PUT" for call in session.calls)
    finalize = session.calls[-1]
    assert finalize[0:2] == (
        "POST",
        "https://here.now/api/v1/publish/dremel-demo/finalize",
    )
    assert finalize[2]["json"] == {"versionId": "version-1"}


@pytest.mark.parametrize("slug", ["../other", "site/path", "site?x=1", "site#fragment"])
def test_publish_site_rejects_path_manipulating_slug(tmp_path, slug):
    (tmp_path / "index.html").write_text("<h1>Dremel</h1>", encoding="utf-8")

    with pytest.raises(here_now_publish.HereNowPublishError, match="slug"):
        here_now_publish.publish_site(
            tmp_path,
            api_key="test-key-not-a-real-secret",
            slug=slug,
            session=FakeSession(),
        )


def test_publish_site_rejects_success_response_without_valid_slug(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Dremel</h1>", encoding="utf-8")
    session = FakeSession()
    original_post = session.post

    def post_without_slug(url, **kwargs):
        response = original_post(url, **kwargs)
        if url.endswith("/finalize"):
            response.payload["slug"] = None
        elif url == "https://here.now/api/v1/publish":
            response.payload["slug"] = None
        return response

    session.post = post_without_slug

    with pytest.raises(here_now_publish.HereNowPublishError, match="slug"):
        here_now_publish.publish_site(
            tmp_path,
            api_key="test-key-not-a-real-secret",
            session=session,
        )


def test_load_api_key_prefers_environment_without_exposing_value(tmp_path):
    credentials = tmp_path / "credentials"
    credentials.write_text("file-key\n", encoding="utf-8")

    assert here_now_publish.load_api_key(
        environ={"HERENOW_API_KEY": "environment-key"},
        credentials_path=credentials,
    ) == "environment-key"


def test_load_api_key_reads_credentials_file(tmp_path):
    credentials = tmp_path / "credentials"
    credentials.write_text("file-key\n", encoding="utf-8")

    assert here_now_publish.load_api_key(
        environ={},
        credentials_path=credentials,
    ) == "file-key"
