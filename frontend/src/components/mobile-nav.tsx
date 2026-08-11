"use client";

import { useApolloClient } from "@apollo/client";
import { Bell, LogOut, Menu, Plus, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { clearTokens } from "@/lib/auth";
import { useMe, ROLE_LABEL } from "@/lib/me-context";
import {
  BOTTOM_NAV,
  NAV_SECTIONS,
  QUICK_ACTIONS,
} from "@/lib/nav-config";
import { cn } from "@/lib/utils";

/**
 * Mobile / tablet navigation shell (hidden at lg+, where the sidebar takes
 * over): a sticky top bar with a menu button, a thumb-reachable bottom tab
 * bar with a center quick-create action, a full-nav drawer, and a
 * quick-actions sheet. Renders once in the app layout.
 */
export function MobileNav() {
  const pathname = usePathname();
  const router = useRouter();
  const client = useApolloClient();
  const me = useMe();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Close overlays on route change.
  useEffect(() => {
    setDrawerOpen(false);
    setSheetOpen(false);
  }, [pathname]);

  // Lock body scroll while an overlay is open.
  useEffect(() => {
    const open = drawerOpen || sheetOpen;
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawerOpen, sheetOpen]);

  async function logout() {
    clearTokens();
    await client.clearStore();
    router.replace("/login");
  }

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");
  const initials = (me?.email ?? "?").slice(0, 2).toUpperCase();

  return (
    <>
      {/* Top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/90 px-4 backdrop-blur lg:hidden">
        <button
          type="button"
          aria-label="Open menu"
          onClick={() => setDrawerOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg border bg-background active:bg-accent"
        >
          <Menu className="h-[18px] w-[18px]" />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
            N
          </div>
          <span className="text-sm font-semibold">Nila Psychiatric</span>
        </div>
        <div className="flex-1" />
        <button
          type="button"
          aria-label="Notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-lg border bg-background active:bg-accent"
        >
          <Bell className="h-[17px] w-[17px] text-muted-foreground" />
          <span className="absolute right-2 top-2 h-[7px] w-[7px] rounded-full border-2 border-background bg-red-500" />
        </button>
      </header>

      {/* Bottom tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid h-16 grid-cols-5 items-center border-t bg-background/95 backdrop-blur lg:hidden">
        {BOTTOM_NAV.slice(0, 2).map((item) => (
          <BottomTab key={item.href} item={item} active={isActive(item.href)} />
        ))}
        <div className="flex items-center justify-center">
          <button
            type="button"
            aria-label="Quick actions"
            onClick={() => setSheetOpen(true)}
            className="-mt-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg active:opacity-90"
          >
            <Plus className="h-6 w-6" />
          </button>
        </div>
        {BOTTOM_NAV.slice(2).map((item) => (
          <BottomTab key={item.href} item={item} active={isActive(item.href)} />
        ))}
      </nav>

      {/* Full-nav drawer */}
      {drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/45"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-[82%] max-w-xs flex-col bg-background shadow-xl">
            <div className="flex items-center gap-3 border-b px-4 py-3.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
                N
              </div>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold">
                  Nila Psychiatric
                </div>
                <div className="text-[11.5px] text-muted-foreground">
                  Hospital · Kochi
                </div>
              </div>
              <button
                type="button"
                aria-label="Close menu"
                onClick={() => setDrawerOpen(false)}
                className="ml-auto flex h-8 w-8 items-center justify-center rounded-lg border active:bg-accent"
              >
                <X className="h-[17px] w-[17px]" />
              </button>
            </div>

            <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
              {NAV_SECTIONS.map((section) => (
                <div key={section.title}>
                  <div className="px-2.5 pb-1 pt-3.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    {section.title}
                  </div>
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-sm font-medium",
                          isActive(item.href)
                            ? "bg-accent font-semibold text-accent-foreground"
                            : "text-muted-foreground active:bg-accent/60"
                        )}
                      >
                        <Icon className="h-[18px] w-[18px]" />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              ))}
            </nav>

            <div className="border-t p-3">
              <div className="flex items-center gap-2.5 rounded-lg p-2">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-semibold text-white">
                  {initials}
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
                  type="button"
                  aria-label="Log out"
                  onClick={logout}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border active:bg-accent"
                >
                  <LogOut className="h-[16px] w-[16px]" />
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Quick-actions sheet */}
      {sheetOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/45"
            onClick={() => setSheetOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 space-y-2 rounded-t-2xl border-t bg-background p-4 pb-6 shadow-xl">
            <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-border" />
            <p className="px-1 pb-1 text-sm font-semibold">Quick actions</p>
            {QUICK_ACTIONS.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3.5 text-sm font-medium active:bg-accent"
                >
                  <Icon className="h-5 w-5 text-muted-foreground" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}
    </>
  );
}

function BottomTab({
  item,
  active,
}: {
  item: (typeof BOTTOM_NAV)[number];
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "flex flex-col items-center gap-1 text-[10px] font-medium",
        active ? "text-foreground" : "text-muted-foreground"
      )}
    >
      <Icon className="h-[21px] w-[21px]" />
      {item.label}
    </Link>
  );
}
