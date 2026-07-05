"use client";

import { useQuery, useApolloClient } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { MeProvider, type Me } from "@/lib/me-context";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { ME } from "@/lib/graphql/operations";

type MeResult = { me: Me };

/**
 * Shell for every authenticated page. Guards the route, loads the current
 * user once, and provides it (via MeProvider) to the sidebar, topbar and all
 * dashboard widgets. Put the authenticated route folders inside this (app)
 * group — see README.md.
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const client = useApolloClient();

  const hasToken = getAccessToken() !== null;
  const { data, loading, error } = useQuery<MeResult>(ME, { skip: !hasToken });

  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  useEffect(() => {
    if (error) {
      clearTokens();
      client.clearStore();
      router.replace("/login");
    }
  }, [error, client, router]);

  if (!hasToken || loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <MeProvider value={data?.me ?? null}>
      <div className="flex min-h-screen w-full bg-background">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col bg-muted/40">{children}</div>
      </div>
    </MeProvider>
  );
}
