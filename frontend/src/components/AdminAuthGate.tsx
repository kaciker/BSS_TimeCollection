import { FormEvent, ReactNode, useEffect, useState } from "react";

type AuthState = "loading" | "anonymous" | "authenticated";

export function AdminAuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>("loading");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function refreshSession() {
    const response = await fetch("/api/v1/admin/auth/me", { credentials: "same-origin" });
    const body = await response.json().catch(() => ({ authenticated: false }));
    setState(response.ok && body.authenticated ? "authenticated" : "anonymous");
  }

  useEffect(() => {
    void refreshSession().catch(() => setState("anonymous"));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/v1/admin/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await response.json().catch(() => ({ detail: "Login failed." }));
      if (!response.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : "Login failed.");
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
    await fetch("/api/v1/admin/auth/logout", { method: "POST", credentials: "same-origin" });
    setPassword("");
    setState("anonymous");
  }

  if (state === "loading") {
    return <div className="admin-auth-shell"><div className="admin-auth-card">Checking admin session…</div></div>;
  }

  if (state === "anonymous") {
    return (
      <div className="admin-auth-shell">
        <form className="admin-auth-card" onSubmit={submit}>
          <div className="admin-auth-kicker">BSS Time Collection</div>
          <h1>Admin access</h1>
          <p>Temporary authentication for the administration area.</p>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required autoFocus />
          </label>
          {error ? <div className="admin-auth-error">{error}</div> : null}
          <button type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}</button>
        </form>
      </div>
    );
  }

  return (
    <>
      <button className="admin-auth-logout" type="button" onClick={() => void logout()}>Sign out</button>
      {children}
    </>
  );
}
