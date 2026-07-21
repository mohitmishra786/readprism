// Next.js instrumentation hook — loads the server Sentry config and forwards
// nested React Server Component errors to Sentry (audit 07-1).
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
