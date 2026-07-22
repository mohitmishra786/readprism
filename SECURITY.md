# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately via GitHub's [private vulnerability
reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, or email the maintainer.

Please include:

- a description of the issue and its impact,
- steps to reproduce (a proof-of-concept if possible),
- affected version/commit.

We aim to acknowledge reports within a few days and will keep you updated on
remediation. Responsible disclosure is appreciated — please give us a reasonable
window to ship a fix before any public disclosure.

## Scope

Security-relevant areas include: the newsletter inbound webhook, server-side URL
fetching (SSRF), authentication/session handling, and any path that renders
third-party content. Configuration hardening notes live in
[`.env.example`](.env.example) and the deployment docs.
