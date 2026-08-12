"use client";

import { useQuery } from "@apollo/client";
import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { TAG_SUGGESTIONS } from "@/lib/graphql/operations";

export type TagCategory = "BEHAVIOUR" | "ILLNESS" | "OTHER" | string;

export type Tag = {
  id?: string;
  name?: string;
  label: string;
  category?: TagCategory;
  patientCount?: number;
};

// Subtle, theme-aware color per category.
const CATEGORY_STYLES: Record<string, string> = {
  BEHAVIOUR: "bg-amber-50 text-amber-800 border-amber-200",
  ILLNESS: "bg-sky-50 text-sky-800 border-sky-200",
  OTHER: "bg-muted text-foreground/80 border-border",
};

function categoryStyle(category?: TagCategory) {
  return CATEGORY_STYLES[category ?? "OTHER"] ?? CATEGORY_STYLES.OTHER;
}

/** A single tag chip, with an optional remove button. */
export function TagChip({
  label,
  category,
  onRemove,
}: {
  label: string;
  category?: TagCategory;
  onRemove?: () => void;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        categoryStyle(category)
      )}
    >
      {label}
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          className="rounded-full p-0.5 hover:bg-black/10"
          aria-label={`Remove ${label}`}
        >
          <X className="h-3 w-3" />
        </button>
      ) : null}
    </span>
  );
}

type SuggestResult = { tagSuggestions: Tag[] };

/**
 * A typeahead input for choosing (or creating) a tag. As the user types it
 * suggests existing tags; pressing Enter or clicking a suggestion selects it.
 * A free-typed value that matches no suggestion still selects (creating a new
 * tag server-side on submit).
 */
export function TagInput({
  onSelect,
  exclude = [],
  placeholder = "Add a tag…",
  allowCreate = true,
}: {
  onSelect: (label: string) => void;
  exclude?: string[];
  placeholder?: string;
  allowCreate?: boolean;
}) {
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery<SuggestResult>(TAG_SUGGESTIONS, {
    variables: { query: value || null },
    fetchPolicy: "cache-and-network",
  });

  const excludeSet = new Set(exclude.map((t) => t.toLowerCase()));
  const suggestions = (data?.tagSuggestions ?? []).filter(
    (t) => !excludeSet.has(t.label.toLowerCase())
  );

  // Offer creating the typed value when it isn't already a suggestion/selected.
  const trimmed = value.trim();
  const canCreate =
    allowCreate &&
    trimmed.length > 0 &&
    !excludeSet.has(trimmed.toLowerCase()) &&
    !suggestions.some((t) => t.label.toLowerCase() === trimmed.toLowerCase());

  const options: Array<{ label: string; category?: TagCategory; create?: boolean }> =
    [
      ...suggestions.map((t) => ({ label: t.label, category: t.category })),
      ...(canCreate ? [{ label: trimmed, create: true as const }] : []),
    ];

  useEffect(() => {
    setActive(0);
  }, [value]);

  // Close the dropdown on outside click.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  function choose(label: string) {
    onSelect(label);
    setValue("");
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const opt = options[active];
      if (opt) choose(opt.label);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      />
      {open && options.length > 0 ? (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md">
          {options.map((opt, i) => (
            <li key={`${opt.label}-${i}`}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(opt.label);
                }}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm",
                  i === active ? "bg-accent" : "hover:bg-accent/60"
                )}
              >
                <span className="flex items-center gap-2">
                  {opt.create ? (
                    <>
                      <span className="text-muted-foreground">Create</span>
                      <TagChip label={opt.label} />
                    </>
                  ) : (
                    <TagChip label={opt.label} category={opt.category} />
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
