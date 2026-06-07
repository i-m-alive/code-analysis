import { useEffect, useMemo, useRef, useState } from "react";
import FindingsTable from "./FindingsTable";

function chunkTail(chunkId) {
  return chunkId.includes("::") ? chunkId.split("::").slice(1).join("::") : chunkId;
}

function groupResults(results) {
  const folders = {};   // { folderName: { filePath: [ChunkReview] } }
  const looseFiles = {}; // { fileName: [ChunkReview] }

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

export default function FolderTreeView({ results, selectedChunkId }) {
  const { folders, looseFiles } = useMemo(() => groupResults(results), [results]);

  // Set of file keys that are expanded: "FolderName/filePath" or "loose:fileName"
  const [openFiles, setOpenFiles] = useState(new Set());
  // Set of chunk_ids whose FindingsTable is visible
  const [openChunks, setOpenChunks] = useState(new Set());

  const chunkRefs = useRef({});

  // Reset open state whenever results change (new analysis run)
  useEffect(() => {
    const open = new Set();
    // First file of each folder open by default
    for (const [folder, files] of Object.entries(folders)) {
      const first = Object.keys(files)[0];
      if (first) open.add(`${folder}/${first}`);
    }
    // All loose files open by default
    for (const name of Object.keys(looseFiles)) {
      open.add(`loose:${name}`);
    }
    setOpenFiles(open);
    setOpenChunks(new Set());
  }, [results]); // eslint-disable-line react-hooks/exhaustive-deps

  // When Dashboard chunk-click fires, expand that chunk and scroll to it
  useEffect(() => {
    if (!selectedChunkId) return;
    const r = results.find((c) => c.chunk_id === selectedChunkId);
    if (!r) return;

    const slash = r.file_name.indexOf("/");
    const fileKey =
      slash === -1 ? `loose:${r.file_name}` : r.file_name;

    setOpenFiles((prev) => new Set([...prev, fileKey]));
    setOpenChunks((prev) => new Set([...prev, selectedChunkId]));

    // Scroll after state settles
    setTimeout(() => {
      chunkRefs.current[selectedChunkId]?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 80);
  }, [selectedChunkId]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleFile(key) {
    setOpenFiles((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  function toggleChunk(chunkId) {
    setOpenChunks((prev) => {
      const next = new Set(prev);
      next.has(chunkId) ? next.delete(chunkId) : next.add(chunkId);
      return next;
    });
  }

  const hasFolders = Object.keys(folders).length > 0;
  const hasLoose = Object.keys(looseFiles).length > 0;
  if (!hasFolders && !hasLoose) return null;

  return (
    <div className="ura-tree">
      <h2 className="ura-tree-heading">Detailed Analysis</h2>

      {/* Folder sections */}
      {Object.entries(folders).map(([folder, files]) => {
        const totalIssues = Object.values(files).reduce(
          (sum, chunks) => sum + chunks.reduce((s, c) => s + c.issues.length, 0),
          0
        );
        return (
          <div key={folder} className="ura-folder-section">
            <div className="ura-folder-header">
              <span className="ura-folder-icon">📁</span>
              <span className="ura-folder-name">{folder}/</span>
              <span className="ura-folder-meta muted">
                {Object.keys(files).length} file{Object.keys(files).length !== 1 ? "s" : ""} · {totalIssues} issue{totalIssues !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="ura-folder-body">
              {Object.entries(files).map(([filePath, chunks]) => {
                const fileKey = `${folder}/${filePath}`;
                const fileIssues = chunks.reduce((s, c) => s + c.issues.length, 0);
                return (
                  <FileAccordion
                    key={filePath}
                    filePath={filePath}
                    fileKey={fileKey}
                    chunks={chunks}
                    totalIssues={fileIssues}
                    isOpen={openFiles.has(fileKey)}
                    onToggle={() => toggleFile(fileKey)}
                    openChunks={openChunks}
                    onToggleChunk={toggleChunk}
                    chunkRefs={chunkRefs}
                  />
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Loose files */}
      {hasLoose && (
        <div className="ura-folder-section">
          {hasFolders && (
            <div className="ura-folder-header">
              <span className="ura-folder-icon">📄</span>
              <span className="ura-folder-name">Individual files</span>
            </div>
          )}
          <div className="ura-folder-body">
            {Object.entries(looseFiles).map(([fileName, chunks]) => {
              const fileKey = `loose:${fileName}`;
              const fileIssues = chunks.reduce((s, c) => s + c.issues.length, 0);
              return (
                <FileAccordion
                  key={fileName}
                  filePath={fileName}
                  fileKey={fileKey}
                  chunks={chunks}
                  totalIssues={fileIssues}
                  isOpen={openFiles.has(fileKey)}
                  onToggle={() => toggleFile(fileKey)}
                  openChunks={openChunks}
                  onToggleChunk={toggleChunk}
                  chunkRefs={chunkRefs}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function FileAccordion({ filePath, chunks, totalIssues, isOpen, onToggle, openChunks, onToggleChunk, chunkRefs }) {
  return (
    <div className="ura-file-accordion">
      <div
        className={`ura-file-header${isOpen ? " is-open" : ""}`}
        onClick={onToggle}
      >
        <span className="ura-file-icon">📄</span>
        <span className="ura-file-path">{filePath}</span>
        <span className="ura-file-meta muted">
          {chunks.length} chunk{chunks.length !== 1 ? "s" : ""} · {totalIssues} issue{totalIssues !== 1 ? "s" : ""}
        </span>
        <span className="ura-file-chevron">{isOpen ? "▲" : "▼"}</span>
      </div>

      {isOpen && (
        <div className="ura-chunk-list">
          {chunks.map((chunk) => {
            const isChunkOpen = openChunks.has(chunk.chunk_id);
            return (
              <div
                key={chunk.chunk_id}
                className="ura-chunk-item"
                ref={(el) => { chunkRefs.current[chunk.chunk_id] = el; }}
              >
                <div
                  className={`ura-chunk-row${isChunkOpen ? " is-open" : ""}`}
                  onClick={() => onToggleChunk(chunk.chunk_id)}
                >
                  <span className="ura-chunk-name">{chunkTail(chunk.chunk_id)}</span>
                  <span className="muted ura-chunk-lines">
                    lines {chunk.start_line}–{chunk.end_line}
                  </span>
                  <span className={`ura-chunk-badge${chunk.issues.length > 0 ? " has-issues" : ""}`}>
                    {chunk.issues.length} issue{chunk.issues.length !== 1 ? "s" : ""}
                  </span>
                  <span className="ura-chunk-chevron">{isChunkOpen ? "▲" : "▼"}</span>
                </div>
                {isChunkOpen && (
                  <div className="ura-chunk-detail">
                    <FindingsTable result={chunk} compact />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
