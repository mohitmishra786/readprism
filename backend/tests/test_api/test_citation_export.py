"""BibTeX and RIS export of saved items (#250)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.integrations.citations import kind_of, to_bibtex, to_ris


def _row(url, title, **kw):
    item = ContentItem(
        url=url,
        title=title,
        author=kw.get("author"),
        summary_brief=kw.get("summary"),
        topic_clusters=kw.get("topics", []),
        published_at=kw.get("published", datetime(2025, 3, 14, tzinfo=UTC)),
    )
    ix = UserContentInteraction(
        saved=True, saved_at=datetime(2026, 10, 1, tzinfo=UTC), tags=kw.get("tags")
    )
    return item, ix


ROWS = [
    _row(
        "https://arxiv.org/abs/2403.01234v2",
        "Scaling laws for sparse retrieval",
        author="Ada Lovelace and Alan Turing",
        topics=["retrieval"],
    ),
    _row("https://doi.org/10.1145/3639476.3639777", "Vacuum in practice", author="Ines Varga"),
    _row(
        "https://blog.example.com/post",
        "Costs & benefits: 100% {weird} title_with $pecial #chars",
        summary="50% faster ~ really",
        tags=["to-read"],
    ),
    _row("https://blog.example.com/post2", "Costs again", author=None),
]


def _bib_entries(text: str) -> list[dict]:
    """Strict parser: balanced braces, one key per entry, name = {value} fields."""
    entries = []
    for block in re.split(r"\n(?=@)", text.strip()):
        m = re.match(r"@(\w+)\{([^,\s]+),\n(.*)\n\}$", block, re.S)
        assert m, block
        depth = 0
        for ch in re.sub(r"\\[{}]", "", m.group(3)):
            depth += {"{": 1, "}": -1}.get(ch, 0)
            assert depth >= 0, block
        assert depth == 0, block
        fields = dict(re.findall(r"^  (\w+) = \{(.*)\},?$", m.group(3), re.M))
        entries.append({"type": m.group(1), "key": m.group(2), **fields})
    return entries


def test_kinds():
    assert kind_of("https://arxiv.org/pdf/2403.01234v3") == ("arxiv", "2403.01234")
    assert kind_of("https://doi.org/10.1145/3639476.3639777") == ("doi", "10.1145/3639476.3639777")
    assert kind_of("https://www.nature.com/doi/10.1038/s41586-024-0001-1") == (
        "doi",
        "10.1038/s41586-024-0001-1",
    )
    assert kind_of("https://blog.example.com/10.1/x") == ("web", None)


def test_bibtex_is_well_formed_and_escaped():
    entries = _bib_entries(to_bibtex(ROWS))
    assert [e["type"] for e in entries] == ["misc", "article", "misc", "misc"]
    arxiv, doi, web, web2 = entries
    assert arxiv["eprint"] == "2403.01234" and arxiv["archivePrefix"] == "arXiv"
    assert arxiv["author"] == "Ada Lovelace and Alan Turing" and arxiv["year"] == "2025"
    assert arxiv["key"] == "lovelace2025scaling"  # first author's surname
    assert doi["doi"] == "10.1145/3639476.3639777"
    assert web["title"] == r"{Costs \& benefits: 100\% \{weird\} title\_with \$pecial \#chars}"
    assert web["abstract"] == r"50\% faster \~{} really"
    assert web["howpublished"] == "blog.example.com" and web["urldate"] == "2026-10-01"
    assert web["keywords"] == "to-read"
    assert len({e["key"] for e in entries}) == 4  # unique keys, even for same source/year


def test_ris_is_well_formed():
    records = to_ris(ROWS).strip().split("\n\n")
    assert len(records) == 4
    for record in records:
        lines = record.split("\n")
        assert lines[0].startswith("TY  - ") and lines[-1] == "ER  -"
        assert all(re.match(r"^[A-Z][A-Z0-9]  - ", line) or line == "ER  -" for line in lines)
    assert "TY  - UNPB" in records[0] and "M1  - arXiv:2403.01234" in records[0]
    assert "TY  - JOUR" in records[1] and "DO  - 10.1145/3639476.3639777" in records[1]
    assert (
        "TY  - ELEC" in records[2]
        and "KW  - to-read" in records[2]
        and "Y2  - 2026/10/01" in records[2]
    )


@pytest.mark.asyncio
async def test_endpoints_return_downloadable_files_of_your_saved_items(client, db_session):
    email = f"bib{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    saved = ContentItem(
        url=f"https://arxiv.org/abs/2401.0000{uuid.uuid4().int % 9}", title="A saved paper"
    )
    not_saved = ContentItem(url=f"https://x.example/{uuid.uuid4().hex}", title="Only read")
    db_session.add_all([saved, not_saved])
    await db_session.flush()
    db_session.add_all(
        [
            UserContentInteraction(user_id=user.id, content_item_id=saved.id, saved=True),
            UserContentInteraction(user_id=user.id, content_item_id=not_saved.id, saved=False),
        ]
    )
    await db_session.commit()

    bib = await client.get("/api/v1/integrations/bibtex", headers=headers)
    assert bib.status_code == 200 and "weirling-saved.bib" in bib.headers["content-disposition"]
    assert "A saved paper" in bib.text and "Only read" not in bib.text
    ris = await client.get("/api/v1/integrations/ris", headers=headers)
    assert ris.status_code == 200 and ris.headers["content-type"].startswith(
        "application/x-research-info-systems"
    )
    assert "TI  - A saved paper" in ris.text


def test_cite_key_uses_the_first_authors_surname():
    from app.services.integrations.citations import _first_author_surname

    assert _first_author_surname("Ada Lovelace and Alan Turing") == "Lovelace"
    assert _first_author_surname("Varga, Ines; Lind, Tomasz") == "Varga"
    assert _first_author_surname("Grid Notes") == "Notes"
    assert _first_author_surname(None) == ""
