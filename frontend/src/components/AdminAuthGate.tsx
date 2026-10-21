import { FormEvent, ReactNode, useEffect, useState } from "react";

type AuthState = "loading" | "anonymous" | "authenticated" | "error";

export function AdminAuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>("loading");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;

    async function checkSession() {
      try {
        const response = await fetch("/api/v1/admin/auth/me", {
          credentials: "same-origin",
          cache: "no-store",
        });

        const body = await response.json();

        if (!active) return;

        if (!response.ok) {
          setError(`Session check failed (HTTP ${response.status})`);
          setState("error");
          return;
        }

        setState(body.authenticated === true ? "authenticated" : "anonymous");
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to check admin session.");
        setState("error");
      }
    }

    void checkSession();

    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const response = await fetch("/api/v1/admin/auth/login", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const body = await response.json().catch(() => ({ detail: "Login failed." }));

      if (!response.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : `Login failed (HTTP ${response.status})`,
        );
      }

      setPassword("");
      setState("authenticated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function logout() {
    try {
      await fetch("/api/v1/admin/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
      });
    } finally {
      setPassword("");
      setState("anonymous");
    }
  }

  if (state === "loading") {
    return (
      <main className="admin-auth-shell">
        <section className="admin-auth-card">
          <div className="admin-auth-kicker">BSS Time Collection</div>
          <h1>Admin access</h1>
          <p>Checking administrator session…</p>
        </section>
      </main>
    );
  }

  if (state === "error") {
    return (
      <main className="admin-auth-shell">
        <section className="admin-auth-card">
          <div className="admin-auth-kicker">BSS Time Collection</div>
          <h1>Admin access error</h1>
          <div className="admin-auth-error">{error || "Unable to initialise authentication."}</div>
          <button type="button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </section>
      </main>
    );
  }

  if (state === "anonymous") {
    return (
      <main className="admin-auth-shell">
        <form className="admin-auth-card" onSubmit={submit}>
          <div className="admin-auth-kicker">BSS Time Collection</div>
          <h1>Admin access</h1>
          <p>Temporary authentication for the administration area.</p>

          <label>
            Username
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              autoFocus
            />
          </label>

          {error ? <div className="admin-auth-error">{error}</div> : null}

          <button type="submit" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <>
      <button
        className="admin-auth-logout"
        type="button"
        onClick={() => void logout()}
      >
        Sign out
      </button>
      {children}
    </>
  );
}
