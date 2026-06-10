import { type Option } from "../../data/filterOptions";

interface CheckboxFilterProps<T extends string> {
  options: Option<T>[];
  selected: T[];
  onToggle: (value: T) => void;
}

export default function CheckboxFilter<T extends string>({
  options,
  selected,
  onToggle,
}: CheckboxFilterProps<T>) {
  return (
    <div className="space-y-2">
      {options.map((option) => (
        <label
          className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm text-slate-300 transition hover:bg-white/[0.06] hover:text-white"
          key={option.value}
        >
          <input
            checked={selected.includes(option.value)}
            className="h-4 w-4 rounded border-white/20 bg-white/[0.06] accent-hire-300"
            onChange={() => onToggle(option.value)}
            type="checkbox"
          />
          <span className="truncate">{option.label}</span>
        </label>
      ))}
    </div>
  );
}
