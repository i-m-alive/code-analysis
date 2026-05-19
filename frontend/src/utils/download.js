/**
 * Client-side report generators for the Universal Review Agent.
 *
 * The whole `results` array already lives in React state, so we can build
 * the report in the browser and trigger a download via a transient blob URL.
 * No backend round-trip needed.
 */

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

function triggerDownload(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function timestamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    `-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  );
}

function summarize(results) {
  const counts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  let totalIssues = 0;
  for (const r of results) {
    for (const issue of r.issues) {
      const sev = (issue.severity || "info").toLowerCase();
      if (counts[sev] !== undefined) counts[sev] += 1;
      totalIssues += 1;
    }
  }
  return { counts, totalIssues };
}

function chunkTail(chunkId) {
  return chunkId.includes("::")
    ? chunkId.split("::").slice(1).join("::")
    : chunkId;
}

export function downloadJSON(results, scoring) {
  const meta = results[0] || {};
  const { counts, totalIssues } = summarize(results);
  const payload = {
    generated_at: new Date().toISOString(),
    model: meta.model,
    chunking_strategy: meta.chunking_strategy,
    skill: meta.skill,
    chunk_count: results.length,
    issue_count: totalIssues,
    severity_breakdown: counts,
    scoring: scoring || null,
    results,
  };
  triggerDownload(
    `ura-report-${timestamp()}.json`,
    JSON.stringify(payload, null, 2),
    "application/json"
  );
}

export function downloadMarkdown(results, scoring) {
  const meta = results[0] || {};
  const { counts, totalIssues } = summarize(results);
  const lines = [];

  lines.push("# Universal Review Agent — Analysis Report");
  lines.push("");
  lines.push(`- **Generated:** ${new Date().toISOString()}`);
  lines.push(`- **Model:** \`${meta.model || "—"}\``);
  lines.push(`- **Chunking strategy:** \`${meta.chunking_strategy || "—"}\``);
  lines.push(`- **Skill:** \`${meta.skill || "—"}\``);
  lines.push(`- **Chunks reviewed:** ${results.length}`);
  lines.push(`- **Issues total:** ${totalIssues}`);
  lines.push("");

  if (scoring && scoring.overall) {
    lines.push("## Code Quality Score");
    lines.push("");
    lines.push(
      `### Overall: **${scoring.overall.grade}** (${scoring.overall.score.toFixed(1)}/100)`
    );
    lines.push("");
    lines.push(`> ${scoring.overall.annotation}`);
    lines.push("");
    lines.push("| Aspect | Grade | Score | Weight | Issues | Annotation |");
    lines.push("|---|---|---|---|---|---|");
    for (const a of scoring.aspects || []) {
      const annot = String(a.annotation || "").replace(/\|/g, "\\|");
      lines.push(
        `| ${a.name} | **${a.grade}** | ${a.score.toFixed(1)}/100 | ` +
          `${(a.weight * 100).toFixed(0)}% | ${a.issue_count} | ${annot} |`
      );
    }
    lines.push("");
  }

  lines.push("## Severity breakdown");
  for (const sev of SEVERITY_ORDER) {
    lines.push(`- **${sev}:** ${counts[sev]}`);
  }
  lines.push("");
  lines.push("## Findings");
  lines.push("");

  const escape = (s) =>
    String(s ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ");

  for (const r of results) {
    lines.push(
      `### ${r.file_name} :: ${chunkTail(r.chunk_id)} (lines ${r.start_line}-${r.end_line})`
    );
    lines.push(`*${r.language} · ${r.chunk_type}*`);
    lines.push("");

    if (!r.issues.length) {
      lines.push("_No issues found._");
    } else {
      lines.push("| Severity | Line | Issue | Recommendation | Source |");
      lines.push("|---|---|---|---|---|");
      for (const issue of r.issues) {
        lines.push(
          `| ${escape(issue.severity)} | ${escape(issue.line)} | ` +
            `${escape(issue.issue)} | ${escape(issue.recommendation)} | ` +
            `${escape(issue.source || "")} |`
        );
      }
    }

    lines.push("");
    lines.push("```" + (r.language || ""));
    lines.push(r.code);
    lines.push("```");
    lines.push("");
    lines.push("---");
    lines.push("");
  }

  triggerDownload(
    `ura-report-${timestamp()}.md`,
    lines.join("\n"),
    "text/markdown;charset=utf-8"
  );
}
