# Digest email: client check (#217)

The digest email is checked automatically on every change (snapshot, table
layout and inline styles, dark-mode CSS, and rendering in Chromium and
WebKit at desktop and phone widths, light and dark). Real mail clients
still need a person, because each rewrites HTML its own way (Outlook
desktop renders with Word).

## How to run the check

1. Configure SMTP for this instance (see [Deployment](DEPLOYMENT.md)).
2. Send the reference email to your test inboxes:

       cd backend && python scripts/send_test_digest_email.py you@gmail.com you@outlook.com you@icloud.com

3. Open it in each client below, in light and dark mode, and fill in the table.

## What to look for

- Each card shows its title, meta line, summary with the "AI summary" label, and "Why: …" line.
- The four buttons (Read in ReadPrism, Useful, Not for me, Save) are visible, tappable, and wrap to a second row on a phone, never sideways.
- In dark mode, text is readable, cards are dark (not white boxes), and links are light blue.
- The discovery badge says where the item came from.
- The footer links (fix sources, manage preferences, unsubscribe) work.
- The inbox preview line shows the top story, not template text.

## Results

| Client | Light | Dark | Phone | Checked by / date | Notes |
|---|---|---|---|---|---|
| Gmail (web) | | | | | |
| Gmail (iOS / Android app) | | | | | |
| Outlook (web / new Outlook) | | | | | |
| Outlook (Windows desktop, Word engine) | | | | | |
| Apple Mail (macOS) | | | | | |
| Apple Mail (iOS) | | | | | |
