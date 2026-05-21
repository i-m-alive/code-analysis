import { useMemo } from "react";

import { downloadJSON, downloadMarkdown } from "../utils/download";

/**
 * Skill-agnostic summary dashboard. Densified layout:
 *   Row 1: 4 KPI tiles + download buttons
 *   Row 2: 3 distribution panels (severity / source / category)
 *   Row 3: per-chunk click-to-select + top issue patterns
 *   Row 4: severity × source matrix
 *
 * The component only depends on the shape:
 *   { file_name, chunk_id, start_line, end_line, issues:[{severity,source,category,issue}] }
 * so every future skill (security_review, etc.) gets this dashboard for free.
 */

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const SOURCE_ORDER = ["deterministic", "llm", "slm", "other"];
const CATEGORY_ORDER = [
  "correctness",
  "security",
  "maintainability",
  "performance",
  "style",
  "uncategorized",
];

function computeStats(results) {
  const severityCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  const sourceCounts = { deterministic: 0, llm: 0, slm: 0, other: 0 };
  const categoryCounts = {
    correctness: 0,
    security: 0,
    maintainability: 0,
    performance: 0,
    style: 0,
    uncategorized: 0,
  };
  const sevBySource = {
    deterministic: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    llm: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    slm: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    other: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
  };
  const byFile = {};
  const issueGroups = {};
  const perChunk = [];

  let totalIssues = 0;
  let chunksWithIssues = 0;
  let chunksWithHigh = 0;
  let hasCategory = false;
  let confidenceSum = 0;
  let confidenceCount = 0;

  for (const r of results) {
    let chunkHigh = false;
    if (r.issues.length > 0) chunksWithIssues += 1;

    byFile[r.file_name] = (byFile[r.file_name] || 0) + r.issues.length;

    for (const issue of r.issues) {
      totalIssues += 1;

      const sev = (issue.severity || "info").toLowerCase();
      if (severityCounts[sev] !== undefined) severityCounts[sev] += 1;
      if (sev === "critical" || sev === "high") chunkHigh = true;

      const src = (issue.source || "other").toLowerCase();
      const srcKey = sourceCounts[src] !== undefined ? src : "other";
      sourceCounts[srcKey] += 1;
      if (sevBySource[srcKey][sev] !== undefined) sevBySource[srcKey][sev] += 1;

      const cat = (issue.category || "uncategorized").toLowerCase();
      const catKey = categoryCounts[cat] !== undefined ? cat : "uncategorized";
      categoryCounts[catKey] += 1;
      if (issue.category) hasCategory = true;

      if (typeof issue.confidence === "number") {
        confidenceSum += issue.confidence;
        confidenceCount += 1;
      }

      const key = (issue.issue || "").toLowerCase().slice(0, 60).trim();
      if (key) issueGroups[key] = (issueGroups[key] || 0) + 1;
    }

    if (chunkHigh) chunksWithHigh += 1;

    perChunk.push({
      chunk_id: r.chunk_id,
      label: r.chunk_id.includes("::")
        ? r.chunk_id.split("::").slice(1).join("::")
        : r.chunk_id,
      file_name: r.file_name,
      lines: `${r.start_line}-${r.end_line}`,
      count: r.issues.length,
    });
  }

  perChunk.sort((a, b) => b.count - a.count);
  const topIssues = Object.entries(issueGroups)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const sortedFiles = Object.entries(byFile).sort((a, b) => b[1] - a[1]);

  return {
    totalChunks: results.length,
    totalIssues,
    chunksWithIssues,
    chunksWithHigh,
    chunksClean: results.length - chunksWithIssues,
    avgPerChunk: results.length ? totalIssues / results.length : 0,
    severityCounts,
    sourceCounts,
    categoryCounts,
    sevBySource,
    byFile: sortedFiles,
    topIssues,
    perChunk,
    hasCategory,
    avgConfidence:
      confidenceCount > 0 ? Math.round(confidenceSum / confidenceCount) : null,
    confidenceCount,
  };
}

function StackedBar({ counts, order, classPrefix, total }) {
  if (!total) return <div className="ura-bar-empty">No data</div>;
  return (
    <div className="ura-stacked-bar" role="img">
      {order.map((key) => {
        const v = counts[key] || 0;
        if (!v) return null;
        const pct = (v / total) * 100;
        return (
          <div
            key={key}
            className={`ura-stacked-bar-seg ${classPrefix}-${key}`}
            style={{ width: `${pct}%` }}
            title={`${key}: ${v} (${pct.toFixed(1)}%)`}
          >
            {pct >= 8 ? `${v}` : ""}
          </div>
        );
      })}
    </div>
  );
}

function HBar({ value, max }) {
  const pct = max ? (value / max) * 100 : 0;
  return (
    <div className="ura-hbar-track">
      <div className="ura-hbar-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

function KpiTile({ value, label, tone }) {
  return (
    <div className={`ura-kpi ura-kpi-${tone || "default"}`}>
      <div className="ura-kpi-value">{value}</div>
      <div className="ura-kpi-label">{label}</div>
    </div>
  );
}

export default function Dashboard({
  results,
  scoring,
  skill,
  selectedChunkId,
  onSelectChunk,
}) {
  const stats = useMemo(() => computeStats(results), [results]);
  if (!results.length) return null;

  const maxChunk = stats.perChunk[0]?.count || 1;
  const maxIssueGroup = stats.topIssues[0]?.[1] || 1;
  const sourceHasData = Object.values(stats.sourceCounts).some((v) => v > 0);

  return (
    <div className="ura-card ura-dashboard">
      <div className="ura-dashboard-head">
        <div>
          <h3>Summary dashboard{skill ? ` · ${skill}` : ""}</h3>
          <span className="muted">
            {stats.chunksWithIssues}/{stats.totalChunks} chunks have issues · avg{" "}
            {stats.avgPerChunk.toFixed(1)} per chunk
          </span>
        </div>
        <div className="ura-dashboard-actions">
          <button onClick={() => downloadJSON(results, scoring)} title="Download full results as JSON">
            ⬇ JSON
          </button>
          <button onClick={() => downloadMarkdown(results, scoring)} title="Download human-readable Markdown report">
            ⬇ Markdown
          </button>
        </div>
      </div>

      {/* Row 1 — KPI tiles */}
      <div className="ura-kpi-row">
        <KpiTile value={stats.totalIssues} label="Total issues" />
        <KpiTile
          value={stats.severityCounts.critical + stats.severityCounts.high}
          label="Critical + High"
          tone={stats.severityCounts.critical + stats.severityCounts.high > 0 ? "danger" : "good"}
        />
        <KpiTile
          value={`${stats.chunksClean}/${stats.totalChunks}`}
          label="Clean chunks"
          tone={stats.chunksClean === stats.totalChunks ? "good" : "default"}
        />
        <KpiTile value={stats.avgPerChunk.toFixed(1)} label="Avg / chunk" />
        <KpiTile
          value={stats.chunksWithHigh}
          label="Chunks w/ High+"
          tone={stats.chunksWithHigh > 0 ? "danger" : "good"}
        />
        {stats.avgConfidence !== null && (
          <KpiTile
            value={`${stats.avgConfidence}`}
            label={`Avg model confidence (${stats.confidenceCount})`}
            tone={
              stats.avgConfidence >= 85
                ? "good"
                : stats.avgConfidence < 70
                ? "danger"
                : "default"
            }
          />
        )}
      </div>

      {/* Row 2 — distribution panels */}
      <div className="ura-dashboard-grid ura-grid-3">
        <section className="ura-dashboard-panel">
          <h4>Severity distribution</h4>
          <StackedBar
            counts={stats.severityCounts}
            order={SEVERITY_ORDER}
            classPrefix="ura-bar-sev"
            total={stats.totalIssues}
          />
          <ul className="ura-legend">
            {SEVERITY_ORDER.map((s) => (
              <li key={s}>
                <span className={`sev sev-${s}`}>{s}</span>
                <strong>{stats.severityCounts[s]}</strong>
              </li>
            ))}
          </ul>
        </section>

        <section className="ura-dashboard-panel">
          <h4>Finding source</h4>
          {sourceHasData ? (
            <>
              <StackedBar
                counts={stats.sourceCounts}
                order={SOURCE_ORDER}
                classPrefix="ura-bar-src"
                total={stats.totalIssues}
              />
              <ul className="ura-legend">
                {SOURCE_ORDER.filter((s) => stats.sourceCounts[s] > 0).map((s) => (
                  <li key={s}>
                    <span className={`chip ura-src-chip ura-src-chip-${s}`}>{s}</span>
                    <strong>{stats.sourceCounts[s]}</strong>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">No source data.</p>
          )}
        </section>

        <section className="ura-dashboard-panel">
          <h4>Category breakdown</h4>
          {stats.hasCategory ? (
            <ul className="ura-hbar-list">
              {CATEGORY_ORDER.filter((c) => stats.categoryCounts[c] > 0).map((cat) => {
                const v = stats.categoryCounts[cat];
                const total = stats.totalIssues || 1;
                return (
                  <li key={cat}>
                    <div className="ura-hbar-row">
                      <span className="ura-hbar-label">{cat}</span>
                      <span className="ura-hbar-value">
                        {v} · {((v / total) * 100).toFixed(0)}%
                      </span>
                    </div>
                    <HBar value={v} max={total} />
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted">
              No category data yet. Once chunks are re-analyzed with the updated
              skill, this panel will populate.
            </p>
          )}
        </section>
      </div>

      {/* Row 3 — per-chunk + top patterns */}
      <div className="ura-dashboard-grid ura-grid-2">
        <section className="ura-dashboard-panel">
          <h4>Issues per chunk · click to inspect</h4>
          <ul className="ura-hbar-list ura-clickable">
            {stats.perChunk.slice(0, 8).map((c) => (
              <li
                key={c.chunk_id}
                className={selectedChunkId === c.chunk_id ? "is-selected" : ""}
                onClick={() => onSelectChunk?.(c.chunk_id)}
                title={`${c.file_name} · lines ${c.lines}`}
              >
                <div className="ura-hbar-row">
                  <span className="ura-hbar-label">{c.label}</span>
                  <span className="ura-hbar-value">{c.count}</span>
                </div>
                <HBar value={c.count} max={maxChunk} />
              </li>
            ))}
          </ul>
        </section>

        <section className="ura-dashboard-panel">
          <h4>Most frequent issue patterns</h4>
          {stats.topIssues.length === 0 ? (
            <p className="muted">No issues found.</p>
          ) : (
            <ul className="ura-hbar-list">
              {stats.topIssues.map(([key, count]) => (
                <li key={key}>
                  <div className="ura-hbar-row">
                    <span className="ura-hbar-label" title={key}>
                      {key}…
                    </span>
                    <span className="ura-hbar-value">{count}</span>
                  </div>
                  <HBar value={count} max={maxIssueGroup} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Row 4 — severity × source matrix */}
      <div className="ura-dashboard-grid ura-grid-1">
        <section className="ura-dashboard-panel">
          <h4>Severity × source matrix</h4>
          <table className="ura-matrix">
            <thead>
              <tr>
                <th></th>
                {SEVERITY_ORDER.map((s) => (
                  <th key={s}>
                    <span className={`sev sev-${s}`}>{s}</span>
                  </th>
                ))}
                <th>total</th>
              </tr>
            </thead>
            <tbody>
              {SOURCE_ORDER.filter((src) => stats.sourceCounts[src] > 0).map((src) => {
                const row = stats.sevBySource[src];
                const total = stats.sourceCounts[src];
                return (
                  <tr key={src}>
                    <td>
                      <span className={`chip ura-src-chip ura-src-chip-${src}`}>{src}</span>
                    </td>
                    {SEVERITY_ORDER.map((s) => (
                      <td key={s} className={row[s] ? "" : "muted"}>
                        {row[s] || "·"}
                      </td>
                    ))}
                    <td>
                      <strong>{total}</strong>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
