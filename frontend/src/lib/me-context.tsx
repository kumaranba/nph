"use client";

import { createContext, useContext } from "react";

export type Role = "ADMIN" | "FINANCE" | "NURSE" | "PRO";

export type Me = {
  id: string;
  email: string;
  role: Role | string;
};

const MeContext = createContext<Me | null>(null);

/** Provides the authenticated user to the app shell + dashboard widgets. */
export function MeProvider({
  value,
  children,
}: {
  value: Me | null;
  children: React.ReactNode;
}) {
  return <MeContext.Provider value={value}>{children}</MeContext.Provider>;
}

export function useMe(): Me | null {
  return useContext(MeContext);
}

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Administrator",
  FINANCE: "Finance",
  NURSE: "Nursing",
  PRO: "Patient Relations",
};
