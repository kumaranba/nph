import {
  Activity,
  Banknote,
  Building2,
  HeartPulse,
  History,
  LayoutDashboard,
  Receipt,
  UserMinus,
  Search,
  Settings,
  ShieldCheck,
  UserPlus,
  Wallet,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
};
export type NavSection = { title: string; items: NavItem[] };

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
      { label: "Search", href: "/search", icon: Search },
      { label: "New admission", href: "/admissions/new", icon: UserPlus },
      { label: "Discharged", href: "/discharged", icon: UserMinus },
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
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users & roles", href: "/users", icon: ShieldCheck },
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
