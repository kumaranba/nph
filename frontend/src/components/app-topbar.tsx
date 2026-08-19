"use client";

import { Search as SearchIcon } from "lucide-react";

import { NotificationBell } from "@/components/notification-bell";
import { Input } from "@/components/ui/input";
import { useMe, ROLE_LABEL } from "@/lib/me-context";

/** Sticky top bar. Title is per-page; role comes from the authenticated user. */
export function AppTopbar({ title }: { title: string }) {
  const me = useMe();

  return (
    <header className="sticky top-0 z-20 hidden h-[61px] shrink-0 items-center gap-4 border-b bg-background/80 px-6 backdrop-blur lg:flex">
      <div className="text-sm font-semibold">{title}</div>

      <div className="relative ml-2 hidden md:block">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search patients, rooms, invoices…"
          className="h-9 w-[300px] pl-9"
        />
      </div>

      <div className="flex-1" />

      {me?.role ? (
        <span className="rounded-full border bg-muted px-2.5 py-1 text-[11px] font-semibold text-muted-foreground">
          {ROLE_LABEL[me.role] ?? me.role}
        </span>
      ) : null}

      <NotificationBell />
    </header>
  );
}
