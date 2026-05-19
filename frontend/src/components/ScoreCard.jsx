/**
 * ScoreCard
 * =========
 * Renders the aggregate scoring produced by a skill's `scoring.py`. Designed
 * to be skill-agnostic — it just iterates `scoring.aspects` and renders one
 * card per aspect, plus the overall headline.
 *
 * The component is null-safe: if the run didn't produce scoring (skill has
 * no scorer, or it crashed), nothing renders.
 */

function gradeClass(grade) {
  // Map "A+", "A-", "B+" etc. to a CSS-safe suffix.
  const safe = (grade || "").replace("+", "-plus").replace("-", "-minus");
  return `ura-grade ura-grade-${safe.toLowerCase() || "unknown"}`;
}

function ScoreBar({ value, max = 100 }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const toneClass =
    value >= 85 ? "good" : value >= 70 ? "okay" : value >= 50 ? "warn" : "bad";
  return (
    <div className="ura-score-bar">
      <div className={`ura-score-bar-fill ura-score-bar-${toneClass}`}
           style={{ width: `${pct}%` }} />
    </div>
  );
}

function severitySummary(sev) {
  // Compact inline "crit:0 high:2 med:5 low:1 info:0"
  const order = ["critical", "high", "medium", "low", "info"];
  const labels = { critical: "crit", high: "high", medium: "med", low: "low", info: "info" };
  return order
    .filter((k) => (sev?.[k] || 0) > 0)
    .map((k) => `${labels[k]}:${sev[k]}`)
    .join(" · ") || "none";
}

export default function ScoreCard({ scoring }) {
  if (!scoring || !scoring.overall) return null;

  const { overall, aspects = [], metadata = {} } = scoring;

  return (
    <div className="ura-card ura-scorecard">
      <div className="ura-scorecard-head">
        <div className="ura-overall">
          <div className={gradeClass(overall.grade)}>{overall.grade}</div>
          <div className="ura-overall-meta">
            <div className="ura-overall-score">
              {overall.score.toFixed(1)}
              <span className="ura-overall-max">/100</span>
            </div>
            <div className="muted">Overall code quality score</div>
          </div>
        </div>
        <p className="ura-overall-annotation">{overall.annotation}</p>
      </div>

      <div className="ura-aspect-grid">
        {aspects.map((a) => (
          <div key={a.name} className="ura-aspect-card">
            <div className="ura-aspect-header">
              <h4>{a.name}</h4>
              <span className={gradeClass(a.grade) + " ura-grade-mini"}>
                {a.grade}
              </span>
            </div>

            <div className="ura-aspect-score-row">
              <span className="ura-aspect-score">{a.score.toFixed(1)}</span>
              <span className="muted"> / 100 · weight {(a.weight * 100).toFixed(0)}%</span>
            </div>

            <ScoreBar value={a.score} />

            <p className="ura-aspect-annotation">{a.annotation}</p>

            <div className="ura-aspect-meta">
              <span>{a.issue_count} issues</span>
              <span className="muted"> · {severitySummary(a.severity_breakdown)}</span>
            </div>

            {a.top_issues && a.top_issues.length > 0 && (
              <details className="ura-aspect-top">
                <summary>Top issues</summary>
                <ul>
                  {a.top_issues.map((ti, idx) => (
                    <li key={idx}>
                      <span className="ura-aspect-top-count">{ti.count}×</span>{" "}
                      {ti.issue}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>

      <div className="ura-scorecard-meta muted">
        Computed across {metadata.total_chunks} chunks · {metadata.total_issues}{" "}
        issues · {metadata.effective_lines} effective lines
      </div>
    </div>
  );
}
