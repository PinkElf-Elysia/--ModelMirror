import { useEffect, useState } from "react";
import { type RangeValue } from "../../data/filterOptions";

interface RangeQuickOption {
  label: string;
  value: RangeValue;
}

interface RangeSliderProps {
  min: number;
  max: number;
  step: number;
  value: RangeValue;
  onChange: (value: RangeValue) => void;
  formatValue: (value: number) => string;
  quickOptions?: RangeQuickOption[];
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export default function RangeSlider({
  min,
  max,
  step,
  value,
  onChange,
  formatValue,
  quickOptions = [],
}: RangeSliderProps) {
  const [draft, setDraft] = useState<RangeValue>(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (draft.min !== value.min || draft.max !== value.max) {
        onChange(draft);
      }
    }, 120);

    return () => window.clearTimeout(timeoutId);
  }, [draft, onChange, value.max, value.min]);

  function updateMin(nextMin: number) {
    const normalizedMin = clamp(nextMin, min, draft.max);
    setDraft({ min: normalizedMin, max: draft.max });
  }

  function updateMax(nextMax: number) {
    const normalizedMax = clamp(nextMax, draft.min, max);
    setDraft({ min: draft.min, max: normalizedMax });
  }

  function updateRange(next: RangeValue) {
    setDraft({
      min: clamp(Math.min(next.min, next.max), min, max),
      max: clamp(Math.max(next.min, next.max), min, max),
    });
  }

  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-100">
        {formatValue(draft.min)} - {draft.max >= max ? `${formatValue(max)}+` : formatValue(draft.max)}
      </p>

      <div className="space-y-2">
        <label className="block text-xs text-slate-400">
          最小值滑块
          <input
            aria-label="最小值"
            className="mt-2 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-hire-300"
            max={max}
            min={min}
            onChange={(event) => updateMin(Number(event.target.value))}
            step={step}
            type="range"
            value={draft.min}
          />
        </label>
        <label className="block text-xs text-slate-400">
          最大值滑块
          <input
            aria-label="最大值"
            className="mt-2 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-accent-300"
            max={max}
            min={min}
            onChange={(event) => updateMax(Number(event.target.value))}
            step={step}
            type="range"
            value={draft.max}
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-slate-400">
          最小值
          <input
            className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-white/[0.06] px-2 text-sm text-white outline-none transition focus:border-hire-300/50 focus:ring-2 focus:ring-hire-300/10"
            max={draft.max}
            min={min}
            onChange={(event) => updateMin(Number(event.target.value))}
            step={step}
            type="number"
            value={draft.min}
          />
        </label>
        <label className="text-xs text-slate-400">
          最大值
          <input
            className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-white/[0.06] px-2 text-sm text-white outline-none transition focus:border-hire-300/50 focus:ring-2 focus:ring-hire-300/10"
            max={max}
            min={draft.min}
            onChange={(event) => updateMax(Number(event.target.value))}
            step={step}
            type="number"
            value={draft.max}
          />
        </label>
      </div>

      {quickOptions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {quickOptions.map((option) => (
            <button
              className="rounded-full border border-white/10 bg-white/[0.045] px-2.5 py-1 text-xs text-slate-300 transition hover:border-hire-300/30 hover:bg-hire-300/10 hover:text-hire-100"
              key={option.label}
              onClick={() => updateRange(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
