import re
import urllib.error

import pytest

from updates import UpdateCheck, parse_version
from version import VERSION

REPO = "N4ole/lmu-dash"


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
    assert parse_version(VERSION)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("v1.2.3", (1, 2, 3)),
        ("1.10.0", (1, 10, 0)),
        (" v2.0.0 ", (2, 0, 0)),
        ("v1.2", None),
        ("v1.2.3-beta", None),
        ("latest", None),
        (None, None),
        (123, None),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def release(tag="v1.1.0", url=None, **kw):
    return {"tag_name": tag, "html_url": url or f"https://github.com/{REPO}/releases/tag/{tag}", **kw}


def test_newer_release_is_announced():
    u = UpdateCheck(REPO, current="1.0.0", fetch=lambda repo: release("v1.1.0"))
    u.check()
    info = u.info()
    assert info["update"] is True
    assert info["latest"] == "1.1.0"
    assert info["url"] == f"https://github.com/{REPO}/releases/tag/v1.1.0"


@pytest.mark.parametrize("tag", ["v1.0.0", "v0.9.9"])
def test_same_or_older_release_is_silent(tag):
    u = UpdateCheck(REPO, current="1.0.0", fetch=lambda repo: release(tag))
    u.check()
    assert u.info()["update"] is False and u.info()["url"] is None


def test_versions_compare_numerically():
    u = UpdateCheck(REPO, current="1.9.0", fetch=lambda repo: release("v1.10.0"))
    u.check()
    assert u.info()["update"] is True


@pytest.mark.parametrize("extra", [{"prerelease": True}, {"draft": True}])
def test_prereleases_are_ignored(extra):
    u = UpdateCheck(REPO, current="1.0.0", fetch=lambda repo: release("v2.0.0", **extra))
    u.check()
    assert u.info()["update"] is False


def test_foreign_url_is_replaced():
    u = UpdateCheck(REPO, current="1.0.0", fetch=lambda repo: release("v1.1.0", url="https://evil.example/x"))
    u.check()
    assert u.info()["url"] == f"https://github.com/{REPO}/releases/latest"


@pytest.mark.parametrize(
    "exc", [urllib.error.URLError("hors-ligne"), TimeoutError(), ValueError("json"), OSError("réseau")]
)
def test_failures_are_silent(exc):
    def boom(repo):
        raise exc

    u = UpdateCheck(REPO, current="1.0.0", fetch=boom)
    u.check()  # ne lève rien
    assert u.info()["update"] is False and u.info()["latest"] is None


def test_garbage_response_is_silent():
    u = UpdateCheck(REPO, current="1.0.0", fetch=lambda repo: {"tag_name": ["x"]})
    u.check()
    assert u.info()["update"] is False


def test_disabled_never_fetches():
    calls = []
    u = UpdateCheck(REPO, enabled=False, fetch=lambda repo: calls.append(repo) or release())
    u.check()
    u.start()
    assert calls == []
    assert u.info()["enabled"] is False
