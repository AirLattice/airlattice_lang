const AUTH_TOKEN_KEY = "opengpts_jwt";

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export async function refreshAuthToken(): Promise<string | null> {
  try {
    const response = await fetch("/refresh", {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      return null;
    }
    const data = (await response.json()) as { access_token: string };
    setAuthToken(data.access_token);
    return data.access_token;
  } catch {
    return null;
  }
}

export async function logoutSession(): Promise<void> {
  try {
    await fetch("/logout", { method: "POST", credentials: "include" });
  } catch {
    // Best-effort logout.
  } finally {
    clearAuthToken();
  }
}
