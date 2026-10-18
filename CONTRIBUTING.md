# Contributing to ReadPrism

Thanks for your interest in contributing! A few things to know before you open
a pull request.

## Developer environment

See the [README](README.md) for the general stack architecture and Quickstart.

### Running Backend Tests

The backend test suite requires **PostgreSQL 16 with pgvector** (database `readprism_test`) and **Redis 7** (for auth sessions, magic links, rate limits, and Celery broker). Host-side tests require Python ≥ 3.11.

You can run the tests in two ways:

1. **Inside Docker (Production-equivalent):**
   ```bash
   docker compose exec backend pytest tests/ -v
   ```

2. **On Host with Test Containers (`docker-compose.test.yml`):**
   ```bash
   # Start test Postgres + Redis containers:
   make test-services
   # or: docker compose -f docker-compose.test.yml up -d

   # Run tests from the backend directory:
   cd backend
   pytest -q

   # Tear down test services when done:
   make test-services-down
   # or: docker compose -f docker-compose.test.yml down -v
   ```

The test runner in `backend/tests/conftest.py` automatically defaults `TEST_DATABASE_URL` to `localhost:5432/readprism_test` and `REDIS_URL` / `CELERY_BROKER_URL` to `redis://127.0.0.1:6379/0` when running outside Docker.

Before submitting a pull request:
- **Backend checks:**
  ```bash
  cd backend
  ruff check . && ruff format --check .
  mypy app --python-version 3.11 --ignore-missing-imports
  pytest -q
  ```
- **Frontend checks:**
  ```bash
  cd frontend
  npm run lint
  npx tsc --noEmit -p .
  npm test
  ```
- Add or update tests for any code change — an item isn't done until it's covered.
- Keep commits focused and reference the relevant area in the message.

## Contributor License / sign-off

> **Note:** The project is licensed under [MIT](LICENSE). Have counsel
> review this section before accepting the first external contribution. It is
> not legal advice.

By submitting a contribution you agree to the **Developer Certificate of Origin**
([DCO 1.1](https://developercertificate.org/)): you certify that you wrote the
contribution (or have the right to submit it) and that it may be distributed
under the project's MIT license. Sign your commits off:

```bash
git commit -s -m "your message"
```

which appends a `Signed-off-by: Your Name <you@example.com>` line.

**Relicensing grant.** So the project can adopt a different OSI-approved license
in the future (e.g. MIT) without chasing down every past contributor, you
also grant the maintainer a perpetual, irrevocable right to relicense your
contribution under any [OSI-approved license](https://opensource.org/licenses).
This is the cheapest to establish now, while the contributor set is small.

## Reporting issues

Use GitHub Issues for bugs and GitHub Discussions for questions and ideas.
For anything security-sensitive, please see [SECURITY.md](SECURITY.md) instead of
opening a public issue.
