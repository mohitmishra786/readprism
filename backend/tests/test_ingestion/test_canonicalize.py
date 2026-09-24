from app.services.ingestion.canonicalize import canonicalize_url


def test_strips_tracking_params_and_www():
    left = canonicalize_url("https://www.Example.com/post/?utm_source=hn&id=1")
    right = canonicalize_url("https://example.com/post?id=1&fbclid=abc")
    assert left == right == "https://example.com/post?id=1"


def test_does_not_merge_different_paths():
    assert canonicalize_url("https://example.com/a") != canonicalize_url("https://example.com/b")


def test_keeps_a_non_default_port():
    assert canonicalize_url("https://example.com:8443/a") == "https://example.com:8443/a"
