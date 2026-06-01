"use client";

import { ApolloProvider } from "@apollo/client";
import { useMemo } from "react";

import { makeApolloClient } from "@/lib/apollo-client";

export function ApolloWrapper({ children }: { children: React.ReactNode }) {
  // One client instance per browser session.
  const client = useMemo(() => makeApolloClient(), []);
  return <ApolloProvider client={client}>{children}</ApolloProvider>;
}
