"use client";

import { Button } from "@relay/ui/components/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@relay/ui/components/command";
import { Popover, PopoverContent, PopoverTrigger } from "@relay/ui/components/popover";
import { cn } from "@relay/ui/lib/utils";
import { Check, ChevronDown, ChevronRight, ListFilter, X } from "lucide-react";
import { useState } from "react";
import { usePreferences } from "../preferences";

export type FilterField = {
  key: string;
  label: string;
  all: string;
  options: { value: string; label: string }[];
  suggestion?: string;
};

const CHIP = cn("relative box-border inline-flex h-8 items-center gap-1.5 rounded-full border-0 px-3 text-sm whitespace-nowrap",
  "transition-[background-color,color,outline-color] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring");

function FilterMenu({ fields, values, onChange, onClose }: {
  fields: FilterField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onClose: () => void;
}) {
  const { t } = usePreferences();
  const [field, setField] = useState<FilterField | null>(null);
  const [query, setQuery] = useState("");
  const matches = (label: string) => label.toLowerCase().includes(query.toLowerCase());
  const options = field ? [{ value: "", label: field.all }, ...field.options].filter((o) => matches(o.label)) : [];
  const shown = field ? [] : fields.filter((f) => matches(f.label));

  function open(next: FilterField | null) {
    setField(next);
    setQuery("");
  }

  return (
    <Command key={field?.key ?? ""} shouldFilter={false} label={t.filters.add}
      onKeyDown={(event) => {
        if (event.key === "Backspace" && field && !query) {
          open(null);
        }
      }}>
      <div className={cn("box-border flex h-11 items-center border-b border-border",
        "**:data-[slot=command-input-wrapper]:h-full **:data-[slot=command-input-wrapper]:flex-1",
        "**:data-[slot=command-input-wrapper]:border-0 [&_[data-slot=command-input-wrapper]>svg]:hidden")}>
        {field && (
          <button type="button" onClick={() => open(null)} className={cn("inline-flex h-full cursor-pointer items-center gap-1",
            "border-0 border-r border-solid border-border bg-transparent px-3 text-sm text-foreground")}>
            {field.label}
            <ChevronDown size={14} />
          </button>
        )}
        <CommandInput autoFocus value={query} onValueChange={setQuery} placeholder={field ? t.filters.to : t.filters.by}
          aria-label={field ? t.filters.to : t.filters.by} className="h-full" />
      </div>
      <CommandList className="max-h-72 p-1">
        <CommandEmpty className="p-3 text-left text-sm text-muted-foreground">{t.filters.none}</CommandEmpty>
        {shown.map((choice) => (
          <CommandItem key={choice.key} value={choice.key} onSelect={() => open(choice)}
            className="h-9 cursor-pointer justify-between pr-2 pl-3">
            {choice.label}
            <ChevronRight />
          </CommandItem>
        ))}
        {field && options.map((choice) => {
          const selected = (values[field.key] ?? "") === choice.value;
          return (
            <CommandItem key={choice.value} value={`option ${choice.value}`} aria-selected={selected}
              className="h-9 cursor-pointer justify-between pr-2 pl-3"
              onSelect={() => { onChange(field.key, choice.value); onClose(); }}>
              {choice.label}
              {selected && <Check />}
            </CommandItem>
          );
        })}
      </CommandList>
    </Command>
  );
}

export function FilterBar({ fields, values, onChange }: {
  fields: FilterField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  const { t } = usePreferences();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-wrap gap-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" className={cn(CHIP, "cursor-pointer bg-background font-medium text-foreground",
            "shadow-[0_0_0_1px_var(--border)]",
            "hover:bg-muted aria-expanded:bg-muted")}>
            <ListFilter size={16} />
            {t.filters.add}
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" sideOffset={8} className="w-80 overflow-hidden border-0 p-0">
          <FilterMenu fields={fields} values={values} onChange={onChange} onClose={() => setOpen(false)} />
        </PopoverContent>
      </Popover>
      {fields.map((field) => {
        const value = values[field.key] ?? "";
        const label = field.options.find((o) => o.value === value)?.label;
        if (value && label) {
          return (
            <span key={field.key} className={cn(CHIP, "bg-background pr-1 text-muted-foreground outline outline-1",
              "-outline-offset-1 outline-border")}>
              <span className="opacity-80">{field.label}</span>
              <span className="font-medium text-foreground">{label}</span>
              <Button type="button" variant="ghost" size="icon-xs" aria-label={t.filters.remove(field.label)}
                className="rounded-full text-muted-foreground hover:text-foreground"
                onClick={() => onChange(field.key, "")}>
                <X className="size-3.5" />
              </Button>
            </span>
          );
        }
        const suggested = field.options.find((o) => o.value === field.suggestion);
        if (!suggested) {
          return null;
        }
        return (
          <button key={field.key} type="button" onClick={() => onChange(field.key, suggested.value)}
            className={cn(CHIP, "group cursor-pointer bg-transparent text-muted-foreground outline outline-1 -outline-offset-1",
              "outline-dashed outline-border-strong/55 hover:bg-muted hover:outline-solid hover:outline-border-strong")}>
            <span className="opacity-80 transition-opacity group-hover:opacity-100">{field.label}</span>
            <span className="font-medium transition-colors group-hover:text-foreground">{suggested.label}</span>
          </button>
        );
      })}
    </div>
  );
}
