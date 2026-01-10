import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearAuthToken, getAuthToken } from "../utils/auth";
import { authFetch } from "../utils/authFetch";

export function AuthGate() {
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const token = getAuthToken();
    const redirectPath = `${location.pathname}${location.search}`;
    if (!token) {
      navigate("/login", {
        replace: true,
        state: { from: redirectPath },
      });
      return;
    }

    let active = true;
    authFetch("/me", { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) {
          return Promise.reject(response.statusText);
        }
        if (active) {
          setReady(true);
        }
      })
      .catch(() => {
        clearAuthToken();
        if (active) {
          navigate("/login", {
            replace: true,
            state: { from: redirectPath },
          });
        }
      });

    return () => {
      active = false;
    };
  }, [navigate, location.pathname, location.search]);

  if (!ready) {
    return <div className="p-6 text-sm text-gray-500">Checking session...</div>;
  }

  return <Outlet />;
}
