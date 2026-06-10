import { type Option } from "../../data/filterOptions";

interface RadioFilterProps<T extends string> {
  name: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
}

export default function RadioFilter<T extends string>({
  name,
  options,
  value,
  onChange,
}: RadioFilterProps<T>) {
  return (
    <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
      {options.map((option) => {
        const isSelected = value === option.value;

        return (
          <label
            className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition duration-200 ${
              isSelected
                ? "border-hire-300/35 bg-hire-300/10 text-hire-100 shadow-[0_0_18px_rgba(251,146,60,0.08)]"
                : "border-transparent text-slate-300 hover:border-white/10 hover:bg-white/[0.06] hover:text-white"
            }`}
            key={option.value}
          >
            <input
              checked={isSelected}
              className="h-4 w-4 border-white/20 bg-white/[0.06] accent-hire-300"
              name={name}
              onChange={() => onChange(option.value)}
              type="radio"
            />
            <span className="truncate">{option.label}</span>
          </label>
        );
      })}
    </div>
  );
}
