"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useApolloClient, useQuery } from "@apollo/client";
import { LogOut } from "lucide-react";

import { cn } from "@/lib/utils";
import { clearTokens } from "@/lib/auth";
import { DUE_FOLLOW_UP_COUNT } from "@/lib/graphql/operations";
import { useMe, ROLE_LABEL } from "@/lib/me-context";
import { navSectionsFor } from "@/lib/nav-config";

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const client = useApolloClient();
  const me = useMe();
  const SECTIONS = navSectionsFor(me?.role);

  // Live due-follow-up count drives the badge on the Follow-ups nav item
  // (PRM roles only). Polls so it stays fresh without a reload.
  const canSeePrm = me?.role === "PRO" || me?.role === "ADMIN";
  const { data: dueData } = useQuery<{ dueFollowUpCount: number }>(
    DUE_FOLLOW_UP_COUNT,
    { skip: !canSeePrm, pollInterval: 60_000, fetchPolicy: "cache-and-network" }
  );
  const dueCount = dueData?.dueFollowUpCount ?? 0;

  async function logout() {
    clearTokens();
    await client.clearStore();
    router.replace("/login");
  }

  const userInitials = (me?.email ?? "?").slice(0, 2).toUpperCase();

  return (
    <aside className="sticky top-0 hidden h-screen w-[252px] shrink-0 flex-col border-r bg-sidebar lg:flex">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b px-[18px] py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-sm font-semibold text-primary-foreground">
          N
        </div>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-sm font-semibold">Nila Psychiatric</div>
          <div className="text-[11.5px] font-medium text-muted-foreground">
            Hospital · Kochi
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <div className="px-2.5 pb-1.5 pt-3.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground/70">
              {section.title}
            </div>
            {section.items.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(item.href + "/");
              const Icon = item.icon;
              // The Follow-ups item carries a live due count (others use the
              // static badge from nav-config, if any).
              const badge =
                item.href === "/follow-ups" && dueCount > 0
                  ? dueCount > 99
                    ? "99+"
                    : String(dueCount)
                  : item.badge;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center justify-between rounded-lg px-2.5 py-2 text-[13.5px] font-medium transition-colors",
                    active
                      ? "bg-accent font-semibold text-accent-foreground"
                      : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                  )}
                >
                  <span className="flex items-center gap-3">
                    <Icon className="h-[18px] w-[18px]" />
                    {item.label}
                  </span>
                  {badge ? (
                    <span className="rounded-full bg-red-50 px-1.5 text-[11px] font-semibold text-red-700">
                      {badge}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* User */}
      <div className="border-t p-3">
        <div className="flex items-center gap-2.5 rounded-lg p-2 hover:bg-accent/60">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-semibold text-white">
            {userInitials}
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-[13px] font-semibold">
              {me?.email ?? "—"}
            </div>
            <div className="text-[11.5px] text-muted-foreground">
              {ROLE_LABEL[me?.role ?? ""] ?? me?.role ?? ""}
            </div>
          </div>
          <button
            onClick={logout}
            title="Log out"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
