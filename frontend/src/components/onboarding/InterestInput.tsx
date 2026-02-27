"use client";

interface InterestInputProps {
  value: string;
  onChange: (v: string) => void;
}

export function InterestInput({ value, onChange }: InterestInputProps) {
  return (
    <div>
      <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>
        Describe what you read and care about
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={5}
        placeholder="I work in ML infrastructure, care about distributed training, follow the Kubernetes ecosystem closely, and read about the economics of AI."
        style={{
          width: "100%",
          padding: "12px",
          border: "1px solid #d1d5db",
          borderRadius: 8,
          fontSize: "0.95rem",
          lineHeight: 1.6,
          resize: "vertical",
        }}
      />
      <p style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
        Be specific. The more detail you provide, the better your first digest will be.
      </p>
    </div>
  );
}
