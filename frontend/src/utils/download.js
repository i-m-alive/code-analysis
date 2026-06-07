/**
 * Client-side report generators for the Universal Review Agent.
 *
 * Results are grouped by folder → file → chunk in both JSON and Markdown.
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
  return chunkId.includes("::") ? chunkId.split("::").slice(1).join("::") : chunkId;
}

// Group ChunkReview[] → { folders: {name: {filePath: [chunk]}}, looseFiles: {name: [chunk]} }
function groupResults(results) {
  const folders = {};
  const looseFiles = {};
  for (const r of results) {
    const slash = r.file_name.indexOf("/");
    if (slash === -1) {
      if (!looseFiles[r.file_name]) looseFiles[r.file_name] = [];
      looseFiles[r.file_name].push(r);
    } else {
      const folder = r.file_name.slice(0, slash);
      const filePath = r.file_name.slice(slash + 1);
      if (!folders[folder]) folders[folder] = {};
      if (!folders[folder][filePath]) folders[folder][filePath] = [];
      folders[folder][filePath].push(r);
    }
  }
  return { folders, looseFiles };
}

export function downloadJSON(results, scoring) {
  const meta = results[0] || {};
  const { counts, totalIssues } = summarize(results);
  const { folders, looseFiles } = groupResults(results);

  // Build grouped structure for JSON
  const grouped = {};
  for (const [folder, files] of Object.entries(folders)) {
    grouped[folder] = {};
    for (const [filePath, chunks] of Object.entries(files)) {
      grouped[folder][filePath] = chunks.map((c) => ({
        chunk_id: c.chunk_id,
        chunk_type: c.chunk_type,
        start_line: c.start_line,
        end_line: c.end_line,
        issues: c.issues,
      }));
    }
  }
  for (const [fileName, chunks] of Object.entries(looseFiles)) {
    grouped[fileName] = chunks.map((c) => ({
      chunk_id: c.chunk_id,
      chunk_type: c.chunk_type,
      start_line: c.start_line,
      end_line: c.end_line,
      issues: c.issues,
    }));
  }

  const payload = {
    generated_at: new Date().toISOString(),
    model: meta.model,
    chunking_strategy: meta.chunking_strategy,
    skill: meta.skill,
    chunk_count: results.length,
    issue_count: totalIssues,
    severity_breakdown: counts,
    scoring: scoring || null,
    grouped_results: grouped,
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
  const { folders, looseFiles } = groupResults(results);
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

  // Overall scores
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

  lines.push("## Severity Breakdown");
  for (const sev of SEVERITY_ORDER) {
    lines.push(`- **${sev}:** ${counts[sev]}`);
  }
  lines.push("");

  const escape = (s) =>
    String(s ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ");

  function writeChunk(r) {
    lines.push(
      `##### ${chunkTail(r.chunk_id)} (lines ${r.start_line}-${r.end_line})`
    );
    lines.push(`*${r.language} · ${r.chunk_type}*`);
    lines.push("");
    if (!r.issues.length) {
      lines.push("_No issues found._");
    } else {
      lines.push("| Severity | Line | Issue | Recommendation | Category | Source |");
      lines.push("|---|---|---|---|---|---|");
      for (const issue of r.issues) {
        lines.push(
          `| ${escape(issue.severity)} | ${escape(issue.line)} | ` +
            `${escape(issue.issue)} | ${escape(issue.recommendation)} | ` +
            `${escape(issue.category || "")} | ${escape(issue.source || "")} |`
        );
      }
    }
    lines.push("");
  }

  lines.push("## Findings");
  lines.push("");

  // Folder sections
  for (const [folder, files] of Object.entries(folders)) {
    lines.push(`### 📁 ${folder}/`);
    lines.push("");
    for (const [filePath, chunks] of Object.entries(files)) {
      const fileIssues = chunks.reduce((s, c) => s + c.issues.length, 0);
      lines.push(`#### 📄 ${filePath} _(${fileIssues} issue${fileIssues !== 1 ? "s" : ""})_`);
      lines.push("");
      for (const chunk of chunks) writeChunk(chunk);
      lines.push("---");
      lines.push("");
    }
  }

  // Loose files
  if (Object.keys(looseFiles).length > 0) {
    if (Object.keys(folders).length > 0) {
      lines.push("### 📄 Individual Files");
      lines.push("");
    }
    for (const [fileName, chunks] of Object.entries(looseFiles)) {
      const fileIssues = chunks.reduce((s, c) => s + c.issues.length, 0);
      lines.push(`#### 📄 ${fileName} _(${fileIssues} issue${fileIssues !== 1 ? "s" : ""})_`);
      lines.push("");
      for (const chunk of chunks) writeChunk(chunk);
      lines.push("---");
      lines.push("");
    }
  }

  triggerDownload(
    `ura-report-${timestamp()}.md`,
    lines.join("\n"),
    "text/markdown;charset=utf-8"
  );
}
