import {
  Activity,
  Banknote,
  Building2,
  CalendarCheck,
  CalendarClock,
  ChefHat,
  HeartPulse,
  History,
  LayoutDashboard,
  MessageSquarePlus,
  Receipt,
  UserMinus,
  Search,
  Settings,
  ShieldCheck,
  UserPlus,
  Users,
  UtensilsCrossed,
  Wallet,
} from "lucide-react";

import type { Role } from "@/lib/me-context";

export type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
  // Roles allowed to see this item. Omitted = the three operational roles
  // (Admin, Finance, Nurse) — i.e. everything the app had before PRM. PRO is
  // scoped, so PRO only sees items that name it explicitly.
  roles?: Role[];
};
export type NavSection = { title: string; items: NavItem[] };

// Default audience for an item with no explicit `roles`: preserves the
// pre-PRM behaviour (all three operational roles see it, PRO does not).
export const DEFAULT_ROLES: Role[] = ["ADMIN", "FINANCE", "NURSE"];

/** Whether `role` may see this nav item. */
export function itemVisibleTo(item: NavItem, role: string | undefined): boolean {
  const allowed = item.roles ?? DEFAULT_ROLES;
  return allowed.includes(role as Role);
}

/** Sections with their items filtered for `role`; empty sections dropped. */
export function navSectionsFor(role: string | undefined): NavSection[] {
  return NAV_SECTIONS.map((s) => ({
    ...s,
    items: s.items.filter((i) => itemVisibleTo(i, role)),
  })).filter((s) => s.items.length > 0);
}

// Single source of truth for the sidebar and the mobile nav drawer.
// Routes mirror the app/ file tree.
export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Overview",
    items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    title: "Patients",
    items: [
      // Search is shared with PRO (they look patients up to convert inquiries
      // and schedule follow-ups).
      {
        label: "Search",
        href: "/search",
        icon: Search,
        roles: ["ADMIN", "FINANCE", "NURSE", "PRO"],
      },
      { label: "New admission", href: "/admissions/new", icon: UserPlus },
      // PRO sees Discharged too — they work follow-ups off this list.
      {
        label: "Discharged",
        href: "/discharged",
        icon: UserMinus,
        roles: ["ADMIN", "FINANCE", "PRO"],
      },
    ],
  },
  {
    title: "Patient Relations",
    items: [
      {
        label: "Inquiries",
        href: "/inquiries",
        icon: MessageSquarePlus,
        roles: ["PRO", "ADMIN"],
      },
      {
        label: "Follow-ups",
        href: "/follow-ups",
        icon: CalendarClock,
        roles: ["PRO", "ADMIN"],
      },
    ],
  },
  {
    title: "Clinical",
    items: [
      { label: "Record vitals", href: "/vitals/new", icon: HeartPulse },
      { label: "Vitals history", href: "/vitals/history", icon: Activity },
    ],
  },
  {
    title: "Billing",
    items: [
      { label: "Fees due", href: "/fees-due", icon: Wallet },
      { label: "Record payment", href: "/payments/new", icon: Banknote },
      { label: "Payments history", href: "/payments/history", icon: History },
      { label: "Change fee", href: "/fees/change", icon: Receipt },
      {
        label: "Food vendor",
        href: "/food-vendor",
        icon: UtensilsCrossed,
        roles: ["ADMIN", "FINANCE"],
      },
      {
        label: "Canteen",
        href: "/canteen",
        icon: ChefHat,
        roles: ["ADMIN", "FINANCE"],
      },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users & roles", href: "/users", icon: ShieldCheck },
      { label: "Staff", href: "/staff", icon: Users, roles: ["ADMIN"] },
      {
        label: "Attendance",
        href: "/attendance",
        icon: CalendarCheck,
        roles: ["ADMIN"],
      },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

// The four thumb-reachable destinations on the mobile bottom bar (the fifth
// slot is the center "+" quick-create action).
export const BOTTOM_NAV: NavItem[] = [
  { label: "Home", href: "/dashboard", icon: LayoutDashboard },
  { label: "Search", href: "/search", icon: Search },
  { label: "Vitals", href: "/vitals/new", icon: HeartPulse },
  { label: "Fees", href: "/fees-due", icon: Wallet },
];

// Quick-create actions on the bottom bar's center button.
export const QUICK_ACTIONS: NavItem[] = [
  { label: "New admission", href: "/admissions/new", icon: UserPlus },
  { label: "Record vitals", href: "/vitals/new", icon: HeartPulse },
  { label: "Record payment", href: "/payments/new", icon: Banknote },
];

export { Building2 };
