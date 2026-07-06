import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, Link } from "react-router-dom";
import { AlertIcon, ArrowLeftIcon, BrandMark } from "../components/icons";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { token, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (token) {
    return <Navigate to="/admin/content" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate("/admin/content", { replace: true });
    } catch {
      setError("Invalid username or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="gate">
      <div style={{ position: "fixed", top: 16, right: 16 }}>
        <ThemeToggle />
      </div>
      <div className="gate__panel">
        <div className="gate__head">
          <span className="brand__mark">
            <BrandMark />
          </span>
          <span>
            <span className="brand__name">Admin Console</span>
            <br />
            <span className="brand__kicker">Restricted Access</span>
          </span>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button type="submit" className="btn btn--primary" disabled={busy} style={{ marginTop: "0.3rem" }}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {error && (
            <p className="form__error">
              <AlertIcon style={{ width: 16, height: 16 }} />
              {error}
            </p>
          )}
        </form>

        <Link to="/" className="gate__back">
          <ArrowLeftIcon />
          Back to customer chat
        </Link>
      </div>
    </main>
  );
}
