function severityClass(sev) {
  return `sev sev-${(sev || "info").toLowerCase()}`;
}

export default function FindingsTable({ result, compact = false }) {
  return (
    <div className={compact ? "ura-findings-compact" : "ura-card"}>
      {!compact && (
        <>
          <div className="ura-chunk-head">
            <div>
              <strong>{result.file_name}</strong>{" "}
              <span className="muted">
                · {result.chunk_id} · lines {result.start_line}-{result.end_line}
              </span>
            </div>
            <div className="ura-chunk-meta">
              <span className="chip">{result.language}</span>
              <span className="chip">{result.chunk_type}</span>
            </div>
          </div>
          <details>
            <summary>View chunk source</summary>
            <pre className="ura-code">{result.code}</pre>
          </details>
        </>
      )}

      {compact && (
        <details className="ura-findings-source">
          <summary>View chunk source</summary>
          <pre className="ura-code">{result.code}</pre>
        </details>
      )}

      {result.issues.length === 0 ? (
        <p className="muted">No issues found.</p>
      ) : (
        <div className="ura-cat-table-wrap">
          <table className="ura-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Line</th>
                <th>Issue</th>
                <th>Recommendation</th>
                <th>Category</th>
                <th>Source</th>
                <th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {result.issues.map((i, idx) => (
                <tr key={idx}>
                  <td>
                    <span className={severityClass(i.severity)}>
                      {i.severity}
                    </span>
                  </td>
                  <td>{i.line}</td>
                  <td>{i.issue}</td>
                  <td>{i.recommendation}</td>
                  <td className="muted">{i.category || "—"}</td>
                  <td className="muted">{i.source || "—"}</td>
                  <td className="muted">
                    {typeof i.confidence === "number" ? `${i.confidence}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
