"use client";

import { useApolloClient, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LinesSkeleton } from "@/components/query-states";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { ME } from "@/lib/graphql/operations";

type MeResult = {
  me: { id: string; email: string; role: string };
};

export default function DashboardPage() {
  const router = useRouter();
  const client = useApolloClient();

  // Skip the query entirely if there is no token, then redirect.
  const hasToken = getAccessToken() !== null;
  const { data, loading, error } = useQuery<MeResult>(ME, { skip: !hasToken });

  useEffect(() => {
    if (!hasToken) {
      router.replace("/login");
    }
  }, [hasToken, router]);

  // An auth error (expired/invalid token) also bounces to login.
  useEffect(() => {
    if (error) {
      clearTokens();
      router.replace("/login");
    }
  }, [error, router]);

  async function handleLogout() {
    clearTokens();
    await client.clearStore();
    router.replace("/login");
  }

  if (!hasToken || loading) {
    return (
      <main className="mx-auto min-h-screen w-full max-w-md p-8">
        <LinesSkeleton lines={4} />
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Dashboard</CardTitle>
          <CardDescription>Authenticated via the Django `me` query</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {data ? (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Email</dt>
                <dd className="font-mono">{data.me.email}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Role</dt>
                <dd className="font-mono">{data.me.role}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">User ID</dt>
                <dd className="font-mono">{data.me.id}</dd>
              </div>
            </dl>
          ) : null}

          <Button variant="outline" className="w-full" onClick={handleLogout}>
            Log out
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
