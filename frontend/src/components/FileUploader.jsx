import { useEffect, useRef, useState } from "react";

function groupForPreview(files) {
  const folderGroups = {};
  const looseFiles = [];
  const zipFiles = [];
  for (const f of files) {
    if (f.name.toLowerCase().endsWith(".zip")) {
      zipFiles.push(f);
    } else if (f.webkitRelativePath && f.webkitRelativePath.includes("/")) {
      const folder = f.webkitRelativePath.split("/")[0];
      if (!folderGroups[folder]) folderGroups[folder] = [];
      folderGroups[folder].push(f);
    } else {
      looseFiles.push(f);
    }
  }
  return { folderGroups, looseFiles, zipFiles };
}

export default function FileUploader({ onUploaded, disabled }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [showMenu, setShowMenu] = useState(false);

  const fileInputRef   = useRef(null);
  const folderInputRef = useRef(null);
  const zipInputRef    = useRef(null);
  const dropdownRef    = useRef(null);

  // webkitdirectory must be set imperatively — JSX attribute support varies.
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute("webkitdirectory", "");
      folderInputRef.current.setAttribute("directory", "");
    }
  }, []);

  // Close dropdown on outside click.
  useEffect(() => {
    function handle(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowMenu(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function addFiles(incoming) {
    const arr = Array.from(incoming || []);
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.webkitRelativePath || f.name));
      return [...prev, ...arr.filter((f) => !existing.has(f.webkitRelativePath || f.name))];
    });
  }

  function trigger(ref) {
    ref.current?.click();
    setShowMenu(false);
  }

  async function submit() {
    if (!files.length) return;
    setBusy(true);
    try {
      await onUploaded(files);
      setFiles([]);
    } finally {
      setBusy(false);
    }
  }

  const { folderGroups, looseFiles, zipFiles } = groupForPreview(files);
  const totalCount = files.length;

  return (
    <div className="ura-card">
      <h3>1. Upload source files, folders, or a ZIP</h3>

      <div className="ura-upload-btns">
        {/* Single "Add ▾" button with dropdown */}
        <div className="ura-add-dropdown" ref={dropdownRef}>
          <button
            onClick={() => setShowMenu((m) => !m)}
            disabled={disabled || busy}
          >
            + Add ▾
          </button>
          {showMenu && (
            <div className="ura-add-menu">
              <button onClick={() => trigger(fileInputRef)}>📄 Files</button>
              <button onClick={() => trigger(folderInputRef)}>📁 Folder</button>
              <button onClick={() => trigger(zipInputRef)}>🗜 ZIP</button>
            </div>
          )}
        </div>

        {files.length > 0 && (
          <button
            className="ura-upload-clear"
            onClick={() => setFiles([])}
            disabled={busy}
          >
            Clear
          </button>
        )}
      </div>

      {/* Hidden inputs */}
      <input ref={fileInputRef}   type="file" multiple style={{ display: "none" }}
        onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        disabled={disabled || busy} />
      <input ref={folderInputRef} type="file" multiple style={{ display: "none" }}
        onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        disabled={disabled || busy} />
      <input ref={zipInputRef}    type="file" accept=".zip" style={{ display: "none" }}
        onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        disabled={disabled || busy} />

      {/* Preview */}
      {files.length > 0 && (
        <div className="ura-upload-preview">
          {/* ZIP files — just show filename */}
          {zipFiles.length > 0 && (
            <ul className="ura-file-list">
              {zipFiles.map((f) => (
                <li key={f.name}>
                  🗜 {f.name}{" "}
                  <span className="muted">· zip · {f.size} bytes</span>
                </li>
              ))}
            </ul>
          )}

          {/* Folder groups */}
          {Object.entries(folderGroups).map(([folder, fFiles]) => (
            <div key={folder} className="ura-upload-folder">
              <div className="ura-upload-folder-name">
                📁 {folder}/
                <span className="muted"> ({fFiles.length} file{fFiles.length !== 1 ? "s" : ""})</span>
              </div>
              <ul className="ura-file-list ura-upload-file-list">
                {fFiles.map((f) => (
                  <li key={f.webkitRelativePath}>
                    {f.webkitRelativePath.slice(folder.length + 1)}{" "}
                    <span className="muted">({f.size} bytes)</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Loose files */}
          {looseFiles.length > 0 && (
            <ul className="ura-file-list"
              style={{ marginTop: (zipFiles.length || Object.keys(folderGroups).length) ? 8 : 0 }}>
              {looseFiles.map((f) => (
                <li key={f.name}>
                  {f.name} <span className="muted">({f.size} bytes)</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <button
        className="primary"
        onClick={submit}
        disabled={!totalCount || busy || disabled}
        style={{ marginTop: 12 }}
      >
        {busy
          ? "Uploading…"
          : totalCount
          ? `Upload (${totalCount} file${totalCount !== 1 ? "s" : ""})`
          : "Upload"}
      </button>
    </div>
  );
}
