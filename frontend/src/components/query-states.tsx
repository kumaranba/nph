"use client";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/** Placeholder rows shown while a table's data is loading. */
export function TableSkeleton({
  rows = 4,
  cols = 4,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Stacked skeleton lines for card/detail content. */
export function LinesSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-5 w-full" />
      ))}
    </div>
  );
}

/** Neutral message for "no data" outcomes. */
export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="rounded-md border border-dashed p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      {description ? (
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

/** Consistent surface for a failed GraphQL query, with optional retry. */
export function QueryError({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-md border border-red-300 bg-red-50 p-4">
      <p className="text-sm font-medium text-red-700">Couldn’t load data</p>
      <p className="mt-1 text-sm text-red-600">
        {message || "Something went wrong. Please try again."}
      </p>
      {onRetry ? (
        <Button
          variant="outline"
          className="mt-3 h-8"
          onClick={() => onRetry()}
        >
          Retry
        </Button>
      ) : null}
    </div>
  );
}
