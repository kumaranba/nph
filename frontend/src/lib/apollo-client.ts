import { ApolloClient, HttpLink, InMemoryCache, from } from "@apollo/client";
import { setContext } from "@apollo/client/link/context";

import { ACCESS_TOKEN_KEY } from "@/lib/auth";

export const GRAPHQL_ENDPOINT =
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/";

const httpLink = new HttpLink({ uri: GRAPHQL_ENDPOINT });

/**
 * Attaches the JWT access token (issued by the Django `login` mutation and
 * stored in localStorage) as an Authorization bearer header on every request.
 */
const authLink = setContext((_operation, { headers }) => {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem(ACCESS_TOKEN_KEY)
      : null;
  return {
    headers: {
      ...headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
});

export function makeApolloClient() {
  return new ApolloClient({
    link: from([authLink, httpLink]),
    cache: new InMemoryCache(),
  });
}
