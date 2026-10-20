"use client";
import { InterestMap } from "../../../components/InterestMap";

export default function InterestsPage() {
  return (
    <div>
      <header className="mb-6">
        <div className="eyebrow text-prism-700 dark:text-prism-300">Your model</div>
        <h1 className="mt-1 font-playfair text-3xl font-bold tracking-tight">Interests</h1>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
          What Weirling has learned from your reading. Everything here is editable.
        </p>
      </header>
      <InterestMap />
    </div>
  );
}
