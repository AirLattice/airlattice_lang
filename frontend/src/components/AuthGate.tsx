import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearAuthToken, getAuthToken, refreshAuthToken } from "../utils/auth";
import { authFetch } from "../utils/authFetch";

export function AuthGate() {
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const redirectPath = `${location.pathname}${location.search}`;
    let active = true;
    const ensureSession = async () => {
      let token = getAuthToken();
      if (!token) {
        token = await refreshAuthToken();
      }
      if (!token) {
        if (active) {
          navigate("/login", {
            replace: true,
            state: { from: redirectPath },
          });
        }
        return;
      }
      try {
        const response = await authFetch("/me", {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(response.statusText);
        }
        if (active) {
          setReady(true);
        }
      } catch {
        clearAuthToken();
        if (active) {
          navigate("/login", {
            replace: true,
            state: { from: redirectPath },
          });
        }
      }
    };

    ensureSession();

    return () => {
      active = false;
    };
  }, [navigate, location.pathname, location.search]);

  if (!ready) {
    return <div className="p-6 text-sm text-gray-500">Checking session...</div>;
  }

  return <Outlet />;
}
