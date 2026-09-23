"""XML bomb and XXE fixtures must fail before a parser expands them."""

from __future__ import annotations

import pytest

from app.utils.xml_safety import UnsafeXMLError, assert_xml_safe

_XXE = b"""<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<opml version="2.0"><body><outline text="&xxe;"/></body></opml>
"""

_BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<opml version="2.0"><body><outline text="&lol3;"/></body></opml>
"""

_OK = b"""<?xml version="1.0"?>
<opml version="2.0"><body>
  <outline text="Example" xmlUrl="https://example.com/feed.xml"/>
</body></opml>
"""


def test_xxe_rejected():
    with pytest.raises(UnsafeXMLError):
        assert_xml_safe(_XXE, max_bytes=10_000, max_outlines=10)


def test_billion_laughs_rejected():
    with pytest.raises(UnsafeXMLError):
        assert_xml_safe(_BILLION_LAUGHS, max_bytes=10_000, max_outlines=10)


def test_oversized_rejected():
    with pytest.raises(UnsafeXMLError, match="exceeds"):
        assert_xml_safe(b"<opml/>" + b"x" * 100, max_bytes=20)


def test_too_many_outlines_rejected():
    body = b"<opml><body>" + b'<outline text="a"/>' * 5 + b"</body></opml>"
    with pytest.raises(UnsafeXMLError, match="outlines"):
        assert_xml_safe(body, max_bytes=10_000, max_outlines=2)


def test_small_opml_allowed():
    assert assert_xml_safe(_OK, max_bytes=10_000, max_outlines=10).startswith(b"<?xml")


def test_html_doctype_is_allowed():
    page = b"<!DOCTYPE html><html><head><title>Site</title></head><body>hi</body></html>"
    assert assert_xml_safe(page, max_bytes=10_000) == page
