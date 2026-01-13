import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getAuthToken, refreshAuthToken, setAuthToken } from "../utils/auth";

const PASSWORD_REQUIREMENTS = [
  "At least 10 characters",
  "Includes a letter",
  "Includes a number",
  "Includes a special character",
];

function validatePassword(password: string): string | null {
  if (password.length < 10) {
    return PASSWORD_REQUIREMENTS[0];
  }
  if (!/[A-Za-z]/.test(password)) {
    return PASSWORD_REQUIREMENTS[1];
  }
  if (!/[0-9]/.test(password)) {
    return PASSWORD_REQUIREMENTS[2];
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    return PASSWORD_REQUIREMENTS[3];
  }
  return null;
}

export function Signup() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || "/";

  useEffect(() => {
    let active = true;
    const ensureSession = async () => {
      let token = getAuthToken();
      if (!token) {
        token = await refreshAuthToken();
      }
      if (token && active) {
        navigate(from, { replace: true });
      }
    };
    ensureSession();
    return () => {
      active = false;
    };
  }, [from, navigate]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const normalized = username.trim();
      if (!normalized) {
        setError("Username is required");
        return;
      }
      const passwordError = validatePassword(password);
      if (passwordError) {
        setError(passwordError);
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match");
        return;
      }
      const response = await fetch("/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: normalized,
          password,
          password_confirm: confirm,
        }),
        credentials: "include",
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Signup failed");
      }
      const data = (await response.json()) as { access_token: string };
      setAuthToken(data.access_token);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-lg font-semibold text-slate-900">
          Create your account
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Sign up with an ID and a strong password.
        </p>
        <label className="mt-5 block text-sm font-medium text-slate-700">
          Username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            placeholder="e.g. demo-user"
            autoComplete="username"
            required
          />
        </label>
        <label className="mt-4 block text-sm font-medium text-slate-700">
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            placeholder="Create a password"
            autoComplete="new-password"
            required
          />
        </label>
        <label className="mt-4 block text-sm font-medium text-slate-700">
          Confirm password
          <input
            type="password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            placeholder="Re-enter password"
            autoComplete="new-password"
            required
          />
        </label>
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
          <p className="font-medium text-slate-700">Password must include:</p>
          <ul className="mt-2 space-y-1">
            {PASSWORD_REQUIREMENTS.map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="mt-5 w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Creating account..." : "Create account"}
        </button>
        <p className="mt-4 text-center text-sm text-slate-600">
          Already have an account?{" "}
          <Link
            className="font-medium text-indigo-600 hover:text-indigo-500"
            to="/login"
          >
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
