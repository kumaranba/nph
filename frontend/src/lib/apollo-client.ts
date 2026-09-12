import {
  ApolloClient,
  HttpLink,
  InMemoryCache,
  from,
  fromPromise,
} from "@apollo/client";
import { setContext } from "@apollo/client/link/context";
import { onError } from "@apollo/client/link/error";

import {
  ACCESS_TOKEN_KEY,
  clearTokens,
  getRefreshToken,
  setTokens,
} from "@/lib/auth";

export const GRAPHQL_ENDPOINT =
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/";

const httpLink = new HttpLink({ uri: GRAPHQL_ENDPOINT });

/**
 * Attaches the JWT access token (issued by the Django `login` mutation and
 * stored in localStorage) as an Authorization bearer header on every request.
 * On a retry after a silent refresh this re-reads the freshly-stored token.
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

// Access tokens expire after 15 min; refresh tokens last 7 days. Exchange the
// refresh token for a new access token so a live session doesn't die mid-use.
const REFRESH_MUTATION = `
  mutation RefreshToken($refreshToken: String!) {
    refreshToken(refreshToken: $refreshToken) {
      accessToken
      refreshToken
    }
  }
`;

// One refresh in flight at a time — concurrent expired requests share it.
let refreshInFlight: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const resp = await fetch(GRAPHQL_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: REFRESH_MUTATION,
        variables: { refreshToken },
      }),
    });
    const json = await resp.json();
    const tokens = json?.data?.refreshToken;
    if (tokens?.accessToken && tokens?.refreshToken) {
      setTokens(tokens.accessToken, tokens.refreshToken);
      return tokens.accessToken;
    }
  } catch {
    // fall through to failure
  }
  return null;
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

// When the bearer token is missing/expired/invalid the token is discarded to
// AnonymousUser, so a role-guarded resolver raises exactly this.
const AUTH_ERROR = /authentication required/i;

const errorLink = onError(({ graphQLErrors, operation, forward }) => {
  if (!graphQLErrors) return;
  const isAuthError = graphQLErrors.some((e) => AUTH_ERROR.test(e.message));
  if (!isAuthError) return;

  // Never try to refresh the auth mutations themselves, and only retry once.
  const name = operation.operationName;
  if (name === "RefreshToken" || name === "Login") return;
  if (operation.getContext().authRetried) return;

  return fromPromise(refreshAccessToken()).flatMap((newToken) => {
    if (!newToken) {
      // Refresh token gone/expired — end the session cleanly.
      clearTokens();
      if (typeof window !== "undefined") window.location.assign("/login");
      return forward(operation);
    }
    // Mark so a still-failing retry doesn't loop; authLink re-reads the new
    // token from localStorage on the forwarded attempt.
    operation.setContext({ authRetried: true });
    return forward(operation);
  });
});

export function makeApolloClient() {
  return new ApolloClient({
    link: from([errorLink, authLink, httpLink]),
    cache: new InMemoryCache(),
  });
}
