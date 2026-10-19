/** What the final onboarding step saves (#201). */
export interface DigestChoice {
  frequency: "daily" | "twice_daily" | "weekly";
  emailOn: boolean;
  /** "HH:MM" from <input type="time"> */
  time: string;
  timezone: string;
}

export function detectedTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * Preferences payload. An explicit time locks the send time (the backend sets
 * send_time_locked when digest_time_morning is saved), so the learned
 * send-time job won't move it. Email off is the existing "in_app_only"
 * frequency: digests are still built daily and readable in the app.
 */
export function digestPreferencesPayload(choice: DigestChoice) {
  const [h = "07", m = "00"] = choice.time.split(":");
  return {
    digest_frequency: choice.emailOn ? choice.frequency : "in_app_only",
    digest_time_morning: `${h.padStart(2, "0")}:${m.padStart(2, "0")}:00`,
    timezone: choice.timezone,
  };
}
