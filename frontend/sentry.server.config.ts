// Server-side Sentry init (audit 07-1). Opt-in via SENTRY_DSN.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_APP_ENV || "development",
    tracesSampleRate: 0,
    // sendDefaultPii stays false — the SDK default; the key was removed from
    // the options type in @sentry/nextjs 11 and false was already the value.
  });
}
