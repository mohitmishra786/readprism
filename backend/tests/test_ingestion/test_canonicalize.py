from app.services.ingestion.canonicalize import canonicalize_url


def test_strips_tracking_params_and_www():
    left = canonicalize_url("https://www.Example.com/post/?utm_source=hn&id=1")
    right = canonicalize_url("https://example.com/post?id=1&fbclid=abc")
    assert left == right == "https://example.com/post?id=1"


def test_does_not_merge_different_paths():
    assert canonicalize_url("https://example.com/a") != canonicalize_url("https://example.com/b")


def test_keeps_a_non_default_port():
    assert canonicalize_url("https://example.com:8443/a") == "https://example.com:8443/a"


def test_http_443_is_not_treated_as_the_default():
    assert canonicalize_url("http://example.com:443/a") == "http://example.com:443/a"


def test_strips_any_utm_prefix():
    assert (
        canonicalize_url("https://example.com/a?utm_reader=1&id=2") == "https://example.com/a?id=2"
    )


def test_bad_port_returns_none():
    assert canonicalize_url("https://example.com:bad/a") is None


def test_ipv6_keeps_brackets():
    assert canonicalize_url("https://[2001:db8::1]/a") == "https://[2001:db8::1]/a"
