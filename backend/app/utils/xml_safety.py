"""Reject XML payloads that can expand into an XXE read or a billion-laughs bomb.

Feed and OPML documents are attacker-controlled. A DOCTYPE with entities is
enough for both attacks, and normal RSS/Atom/OPML documents do not need one.
Oversized files and huge outline lists are rejected before they are parsed.
"""

from __future__ import annotations

import re

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException

_DOCTYPE_OR_ENTITY = re.compile(rb"<!DOCTYPE|<!ENTITY", re.IGNORECASE)
_OUTLINE = re.compile(rb"<outline\b", re.IGNORECASE)


class UnsafeXMLError(ValueError):
    """Raised when a feed or OPML document fails the XML safety checks."""


def assert_xml_safe(
    payload: bytes | str,
    *,
    max_bytes: int,
    max_outlines: int | None = None,
) -> bytes:
    """Return the payload as bytes, or raise `UnsafeXMLError`.

    When `max_outlines` is set (OPML import), the document is also parsed with
    defusedxml so entity expansion cannot run even if the textual scan misses.
    """
    data = payload.encode("utf-8", errors="replace") if isinstance(payload, str) else payload
    if len(data) > max_bytes:
        raise UnsafeXMLError(f"document exceeds {max_bytes} bytes")
    if _DOCTYPE_OR_ENTITY.search(data):
        raise UnsafeXMLError("DOCTYPE and entity declarations are not allowed")
    if max_outlines is not None:
        outlines = len(_OUTLINE.findall(data))
        if outlines > max_outlines:
            raise UnsafeXMLError(f"document has {outlines} outlines; limit is {max_outlines}")
        try:
            DefusedElementTree.fromstring(data)
        except DefusedXmlException as e:
            raise UnsafeXMLError(f"unsafe XML: {e}") from e
        except Exception as e:
            # Well-formedness errors are the caller's problem (listparser will
            # report them). Entity/DOCTYPE attacks are already rejected above
            # and by defusedxml; don't turn a sloppy-but-harmless feed into a
            # hard failure here unless defusedxml itself objected.
            if "entity" in str(e).lower() or "doctype" in str(e).lower():
                raise UnsafeXMLError(f"unsafe XML: {e}") from e
    return data
