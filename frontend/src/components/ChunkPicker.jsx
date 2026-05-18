/**
 * Dropdown that lets the user select a single chunk to inspect.
 *
 * Chunks are grouped by file via <optgroup> so the picker stays readable
 * when many files have been analyzed in one run.
 */
export default function ChunkPicker({ results, value, onChange }) {
  if (!results.length) return null;

  // Stable grouping by file_name preserving original chunk order.
  const groups = results.reduce((acc, r) => {
    (acc[r.file_name] ||= []).push(r);
    return acc;
  }, {});

  function chunkLabel(r) {
    // chunk_id looks like "auth.py::login#12" — take the part after "::".
    const tail = r.chunk_id.includes("::")
      ? r.chunk_id.split("::").slice(1).join("::")
      : r.chunk_id;
    const issueCount = r.issues.length;
    const noun = issueCount === 1 ? "issue" : "issues";
    return `${tail} (lines ${r.start_line}-${r.end_line}) — ${issueCount} ${noun}`;
  }

  return (
    <label className="ura-chunk-picker">
      Select chunk to inspect
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {Object.entries(groups).map(([file, chunks]) => (
          <optgroup key={file} label={file}>
            {chunks.map((c) => (
              <option key={c.chunk_id} value={c.chunk_id}>
                {chunkLabel(c)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}
