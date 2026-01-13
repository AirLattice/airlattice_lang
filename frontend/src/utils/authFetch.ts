import { clearAuthToken, getAuthToken, refreshAuthToken } from "./auth";

let redirectingForAuth = false;
let refreshPromise: Promise<string | null> | null = null;

async function getRefreshedToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = refreshAuthToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export function withAuthHeaders(headers: HeadersInit = {}): Headers {
  const authHeaders = new Headers(headers);
  const token = getAuthToken();
  if (token) {
    authHeaders.set("Authorization", `Bearer ${token}`);
  }
  return authHeaders;
}

export async function authFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
) {
  const headers = withAuthHeaders(init.headers);
  const response = await fetch(input, {
    ...init,
    headers,
    credentials: "include",
  });
  if ((response.status === 401 || response.status === 403) && !redirectingForAuth) {
    const url =
      typeof input === "string"
        ? input
        : input instanceof Request
          ? input.url
          : input.toString();
    if (!url.endsWith("/refresh")) {
      const newToken = await getRefreshedToken();
      if (newToken) {
        const retryHeaders = withAuthHeaders(init.headers);
        return fetch(input, {
          ...init,
          headers: retryHeaders,
          credentials: "include",
        });
      }
    }
    redirectingForAuth = true;
    clearAuthToken();
    window.location.assign("/");
  }
  return response;
}
