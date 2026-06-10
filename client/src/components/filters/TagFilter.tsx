import { type Option } from "../../data/filterOptions";

interface TagFilterProps<T extends string> {
  options: Option<T>[];
  selected: T[];
  onToggle: (value: T) => void;
}

export default function TagFilter<T extends string>({
  options,
  selected,
  onToggle,
}: TagFilterProps<T>) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isSelected = selected.includes(option.value);

        return (
          <button
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition duration-200 active:scale-[0.98] ${
              isSelected
                ? "border-hire-300/55 bg-hire-300/20 text-white shadow-[0_0_0_1px_rgba(251,146,60,0.18),0_0_18px_rgba(251,146,60,0.10)]"
                : "border-white/10 bg-white/[0.045] text-slate-300 hover:border-hire-300/30 hover:bg-hire-300/10 hover:text-hire-100"
            }`}
            key={option.value}
            onClick={() => onToggle(option.value)}
            type="button"
          >
            {option.icon ? <span className="mr-1">{option.icon}</span> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
