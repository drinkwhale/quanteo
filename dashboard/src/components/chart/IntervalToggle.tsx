interface IntervalToggleProps {
  value: "1m" | "1d";
  onChange: (interval: "1m" | "1d") => void;
}

export function IntervalToggle({ value, onChange }: IntervalToggleProps) {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onChange("1m")}
        className={`px-3 py-2 rounded text-sm font-medium transition-colors ${
          value === "1m"
            ? "bg-signal-blue text-white"
            : "bg-structural-line text-muted hover:text-white"
        }`}
      >
        1분봉
      </button>
      <button
        onClick={() => onChange("1d")}
        className={`px-3 py-2 rounded text-sm font-medium transition-colors ${
          value === "1d"
            ? "bg-signal-blue text-white"
            : "bg-structural-line text-muted hover:text-white"
        }`}
      >
        일봉
      </button>
    </div>
  );
}
