#!/usr/bin/env python
"""Send the reference digest email to real inboxes for the client check (#217).

Sends the same rendered email the snapshot test checks
(tests/fixtures/email/digest_email.html), through this instance's SMTP
settings, so it can be opened in Gmail, Outlook and Apple Mail, light and
dark. Record what you see in docs/email-clients.md.

    cd backend && python scripts/send_test_digest_email.py you@gmail.com you@outlook.com

All links point at rp.example placeholders; nothing in it is real data.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SNAPSHOT = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "email" / "digest_email.html"
)


async def main(recipients: list[str]) -> int:
    from app.utils.email import send_email

    html = SNAPSHOT.read_text()
    failed = 0
    for to in recipients:
        ok = await send_email(
            to=to,
            subject="Weirling digest: client rendering check",
            html_body=html,
            text_body="Weirling digest rendering check. Open the HTML version.",
        )
        print(f"{'sent' if ok else 'FAILED'}: {to}")
        failed += 0 if ok else 1
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: send_test_digest_email.py ADDRESS [ADDRESS ...]")
    sys.exit(asyncio.run(main(sys.argv[1:])))
