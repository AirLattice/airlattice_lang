import { clearAuthToken, getAuthToken } from "./auth";

let redirectingForAuth = false;

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
  const response = await fetch(input, { ...init, headers });
  if ((response.status === 401 || response.status === 403) && !redirectingForAuth) {
    redirectingForAuth = true;
    clearAuthToken();
    window.location.assign("/");
  }
  return response;
}
