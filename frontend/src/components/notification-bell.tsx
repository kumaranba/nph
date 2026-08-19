"use client";

import { useQuery } from "@apollo/client";
import { Bell } from "lucide-react";
import Link from "next/link";

import { DUE_FOLLOW_UP_COUNT } from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";
import { cn } from "@/lib/utils";

// Follow-up reminders are a PRM concern: only the PRO and ADMIN see the bell.
function canSeeBell(role: string | undefined): boolean {
  return role === "PRO" || role === "ADMIN";
}

/**
 * Notification bell for due follow-ups. Polls the due count and links to the
 * follow-ups page. Renders nothing for roles without PRM access, so the app
 * shell can drop it in unconditionally.
 */
export function NotificationBell({ className }: { className?: string }) {
  const me = useMe();
  const allowed = canSeeBell(me?.role);

  const { data } = useQuery<{ dueFollowUpCount: number }>(DUE_FOLLOW_UP_COUNT, {
    skip: !allowed,
    pollInterval: 60_000,
    fetchPolicy: "cache-and-network",
  });

  if (!allowed) return null;

  const count = data?.dueFollowUpCount ?? 0;
  const label =
    count > 0 ? `${count} follow-up${count === 1 ? "" : "s"} due` : "Follow-ups";

  return (
    <Link
      href="/follow-ups"
      aria-label={label}
      title={label}
      className={cn(
        "relative flex h-9 w-9 items-center justify-center rounded-lg border bg-background transition-colors hover:bg-accent",
        className
      )}
    >
      <Bell className="h-[17px] w-[17px] text-muted-foreground" />
      {count > 0 ? (
        <span className="absolute -right-1.5 -top-1.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full border-2 border-background bg-red-500 px-1 text-[10px] font-bold leading-none text-white">
          {count > 99 ? "99+" : count}
        </span>
      ) : null}
    </Link>
  );
}
