import { useState } from "react";

export default function FileUploader({ onUploaded, disabled }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);

  function pick(e) {
    setFiles(Array.from(e.target.files || []));
  }

  async function submit() {
    if (!files.length) return;
    setBusy(true);
    try {
      await onUploaded(files);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ura-card">
      <h3>1. Upload source files</h3>
      <input
        type="file"
        multiple
        onChange={pick}
        disabled={disabled || busy}
      />
      {files.length > 0 && (
        <ul className="ura-file-list">
          {files.map((f) => (
            <li key={f.name}>
              {f.name} <span className="muted">({f.size} bytes)</span>
            </li>
          ))}
        </ul>
      )}
      <button
        className="primary"
        onClick={submit}
        disabled={!files.length || busy || disabled}
      >
        {busy ? "Uploading…" : "Upload"}
      </button>
    </div>
  );
}
