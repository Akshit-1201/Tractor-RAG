import { useCallback, useEffect, useState } from "react";
import { getAnalytics, type AnalyticsData } from "../api/admin";
import { AlertIcon } from "../components/icons";
import { useAuth } from "../context/AuthContext";
import AdminNav from "./AdminNav";

export default function AnalyticsPage() {
  const { logout } = useAuth();
  const [stats, setStats] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStats(await getAnalytics());
      setError(null);
    } catch (e) {
      if (e instanceof Error && e.message.startsWith("API 401")) {
        logout();
        return;
      }
      setError("Could not load analytics.");
    }
  }, [logout]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000); // live-ish feed
    return () => clearInterval(timer);
  }, [load]);

  const maxTopicCount = Math.max(1, ...(stats?.top_topics.map((t) => t.count) ?? [1]));

  return (
    <div className="shell">
      <AdminNav active="analytics" />
      <main className="shell__main">
        <div className="page-head">
          <h1>Usage analytics</h1>
          <p>What customers ask, and how often the manuals can answer them.</p>
        </div>

        {error && (
          <p className="banner">
            <AlertIcon style={{ width: 18, height: 18, flex: "0 0 auto" }} />
            {error}
          </p>
        )}

        {!stats ? (
          !error && <p className="subtle">Loading…</p>
        ) : (
          <>
            <section className="gauges">
              <div className="gauge">
                <span className="gauge__k">Total questions</span>
                <div className="gauge__v mono">{stats.total_questions}</div>
              </div>
              <div className="gauge">
                <span className="gauge__k">Answered</span>
                <div className="gauge__v mono">{stats.answered}</div>
              </div>
              <div className="gauge">
                <span className="gauge__k">Not in manuals</span>
                <div className="gauge__v mono">{stats.unknown}</div>
              </div>
              <div className="gauge gauge--accent">
                <span className="gauge__k">Answer rate</span>
                <div className="gauge__v mono">
                  {Math.round(stats.answer_rate * 1000) / 10}
                  <span className="gauge__u">%</span>
                </div>
              </div>
            </section>

            <div className="section-title">
              <h2>Most common topics</h2>
            </div>
            {stats.top_topics.length === 0 ? (
              <p className="subtle">No questions logged yet.</p>
            ) : (
              <div className="bars">
                {stats.top_topics.map((topic) => (
                  <div className="bar" key={topic.topic}>
                    <span className="bar__label">{topic.topic}</span>
                    <div className="bar__track">
                      <div
                        className="bar__fill"
                        style={{ width: `${(topic.count / maxTopicCount) * 100}%` }}
                      />
                    </div>
                    <span className="bar__v">{topic.count}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="section-title">
              <h2>Recent questions</h2>
            </div>
            {stats.recent_questions.length === 0 ? (
              <p className="subtle">Nothing yet — ask something in the customer chat.</p>
            ) : (
              <div className="log">
                {stats.recent_questions.map((q, index) => (
                  <div className="log__row" key={index}>
                    <span
                      className={`lamp ${q.is_answered ? "lamp--ok" : "lamp--warn"}`}
                      title={q.is_answered ? "Answered" : "Not in the manuals"}
                    />
                    <span className="log__q">{q.question}</span>
                    <span className="log__t">{new Date(q.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
