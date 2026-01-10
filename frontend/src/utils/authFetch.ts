import { getAuthToken } from "./auth";

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
  return fetch(input, { ...init, headers });
}
