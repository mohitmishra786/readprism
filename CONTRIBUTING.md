# Contributing to ReadPrism

Thanks for your interest in contributing! A few things to know before you open
a pull request.

## Developer environment

See the [README](README.md) for the Docker Compose setup. Before submitting:

- **Backend:** `ruff check .` and `ruff format --check .` must pass, and
  `pytest tests/` must be green (run inside the backend container, as CI does).
- **Frontend:** `npx tsc --noEmit` and `npm run build` must pass.
- Add or update tests for any code change — an item isn't done until it's covered.
- Keep commits focused and reference the relevant area in the message.

## Contributor License / sign-off

> **Note:** The project is licensed under [AGPL-3.0](LICENSE). Have counsel
> review this section before accepting the first external contribution. It is
> not legal advice.

By submitting a contribution you agree to the **Developer Certificate of Origin**
([DCO 1.1](https://developercertificate.org/)): you certify that you wrote the
contribution (or have the right to submit it) and that it may be distributed
under the project's AGPL-3.0 license. Sign your commits off:

```bash
git commit -s -m "your message"
```

which appends a `Signed-off-by: Your Name <you@example.com>` line.

**Relicensing grant.** So the project can adopt a different OSI-approved license
in the future (e.g. AGPL-3.0) without chasing down every past contributor, you
also grant the maintainer a perpetual, irrevocable right to relicense your
contribution under any [OSI-approved license](https://opensource.org/licenses).
This is the cheapest to establish now, while the contributor set is small.

## Reporting issues

Use GitHub Issues for bugs and GitHub Discussions for questions and ideas.
For anything security-sensitive, please see [SECURITY.md](SECURITY.md) instead of
opening a public issue.
