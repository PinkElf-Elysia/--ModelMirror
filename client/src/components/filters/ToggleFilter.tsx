interface ToggleFilterProps {
  checked: boolean;
  label: string;
  description?: string;
  onChange: (checked: boolean) => void;
}

export default function ToggleFilter({
  checked,
  label,
  description,
  onChange,
}: ToggleFilterProps) {
  return (
    <button
      aria-pressed={checked}
      className="flex w-full items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-left transition hover:border-hire-300/30 hover:bg-hire-300/10"
      onClick={() => onChange(!checked)}
      type="button"
    >
      <span>
        <span className="block text-sm font-medium text-slate-200">{label}</span>
        {description ? (
          <span className="mt-0.5 block text-xs leading-5 text-slate-400">
            {description}
          </span>
        ) : null}
      </span>
      <span
        className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border transition ${
          checked
            ? "border-hire-300/50 bg-hire-300/30 shadow-[0_0_18px_rgba(251,146,60,0.18)]"
            : "border-white/10 bg-white/10"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${
            checked ? "left-5" : "left-0.5"
          }`}
        />
      </span>
    </button>
  );
}
