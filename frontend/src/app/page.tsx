"use client";

import { gql, useLazyQuery } from "@apollo/client";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { GRAPHQL_ENDPOINT } from "@/lib/apollo-client";

// Root meta-field query: confirms the link to Django works without requiring auth.
const PING = gql`
  query Ping {
    __typename
  }
`;

export default function Home() {
  const [ping, { data, loading, error }] = useLazyQuery(PING, {
    fetchPolicy: "no-cache",
  });

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>NPH Frontend</CardTitle>
          <CardDescription>
            Next.js 14 · Tailwind · shadcn/ui · Apollo Client
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm">
            <span className="text-muted-foreground">GraphQL endpoint</span>
            <p className="break-all font-mono">{GRAPHQL_ENDPOINT}</p>
          </div>

          <div className="flex gap-2">
            <Button onClick={() => ping()} disabled={loading}>
              {loading ? "Testing…" : "Test connection"}
            </Button>
            <Button variant="outline" asChild>
              <Link href="/login">Sign in</Link>
            </Button>
          </div>

          {data ? (
            <p className="text-sm text-green-600">
              Connected ✓ — root type:{" "}
              <span className="font-mono">{data.__typename}</span>
            </p>
          ) : null}
          {error ? (
            <p className="break-all text-sm text-red-600">
              Error: {error.message}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
}
