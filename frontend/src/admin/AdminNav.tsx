import { Link } from "react-router-dom";
import { BrandMark, ChartIcon, FolderIcon, LogoutIcon } from "../components/icons";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../context/AuthContext";

export default function AdminNav({ active }: { active: "content" | "analytics" }) {
  const { logout } = useAuth();
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <Link to="/admin/content" className="brand" aria-label="Admin home">
          <span className="brand__mark">
            <BrandMark />
          </span>
          <span>
            <span className="brand__name">Tractor Assistant</span>
            <br />
            <span className="brand__kicker">Admin Console</span>
          </span>
        </Link>

        <nav className="tabs" aria-label="Admin sections">
          <Link
            to="/admin/content"
            className={`tab${active === "content" ? " tab--active" : ""}`}
            aria-current={active === "content" ? "page" : undefined}
          >
            <FolderIcon />
            Content
          </Link>
          <Link
            to="/admin/analytics"
            className={`tab${active === "analytics" ? " tab--active" : ""}`}
            aria-current={active === "analytics" ? "page" : undefined}
          >
            <ChartIcon />
            Analytics
          </Link>
        </nav>

        <div className="topbar__spacer" />
        <ThemeToggle />
        <button type="button" className="btn btn--ghost" onClick={logout}>
          <LogoutIcon style={{ width: 16, height: 16 }} />
          Log out
        </button>
      </div>
    </header>
  );
}
