import { useEffect, useMemo, useState } from "react";

import {
  analyze,
  getModels,
  getOllamaHealth,
  getSkills,
  uploadFiles,
} from "./api/client";
import Dashboard from "./components/Dashboard";
import FileUploader from "./components/FileUploader";
import FolderTreeView from "./components/FolderTreeView";
import HealthBanner from "./components/HealthBanner";
import Header from "./components/Header";
import ScoreCard from "./components/ScoreCard";
import Selectors from "./components/Selectors";

function extractError(e) {
  if (!e) return "Unknown error";
  if (e.code === "ECONNABORTED") return "Request timed out.";
  return (
    e?.response?.data?.detail ||
    e?.response?.statusText ||
    e?.message ||
    "Unknown error"
  );
}

export default function App() {
  const [models, setModels] = useState([]);
  const [skills, setSkills] = useState([]);
  const [modelId, setModelId] = useState("");
  const [skillId, setSkillId] = useState("");
  const [uploaded, setUploaded] = useState([]);
  const [results, setResults] = useState([]);
  const [scoring, setScoring] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [health, setHealth] = useState(null);
  const [selectedChunkId, setSelectedChunkId] = useState("");

  async function refreshHealth() {
    try {
      const h = await getOllamaHealth();
      setHealth(h);
    } catch (e) {
      setHealth({
        reachable: false,
        installed_models: [],
        active_model: "",
        active_model_pulled: false,
      });
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const [m, sk] = await Promise.all([getModels(), getSkills()]);
        setModels(m.models);
        setModelId(m.active);
        setSkills(sk.skills);
        setSkillId(sk.default);
        await refreshHealth();
      } catch (e) {
        setError(
          "Cannot reach backend on http://localhost:8000. Is uvicorn running?"
        );
      }
    })();
  }, []);

  async function handleUploaded(files) {
    setError("");
    try {
      const res = await uploadFiles(files);
      setUploaded((prev) => [...prev, ...res.files]);
    } catch (e) {
      setError(`Upload failed: ${extractError(e)}`);
    }
  }

  async function runAnalysis() {
    if (!uploaded.length) {
      setError("Upload at least one file before running.");
      return;
    }
    setRunning(true);
    setResults([]);
    setError("");
    try {
      const res = await analyze({
        file_ids: uploaded.map((u) => u.file_id),
        model_id: modelId,
        chunking_strategy: "comprehensive",
        skill: skillId,
      });
      const list = res.results || [];
      setResults(list);
      setScoring(res.scoring || null);
      setSelectedChunkId(list[0]?.chunk_id || "");
      if (list.length === 0) {
        setError(
          "Analysis returned 0 chunks. The chunker may not support the uploaded language."
        );
      }
    } catch (e) {
      const msg = extractError(e);
      console.error("Analyze failed:", e);
      setError(`Analyze failed: ${msg}`);
    } finally {
      setRunning(false);
      refreshHealth();
    }
  }

  return (
    <div className="ura-shell">
      <Header activeModel={modelId} activeSkill={skillId} />

      <HealthBanner health={health} activeModel={modelId} />

      {error && <div className="ura-error">{error}</div>}

      <FileUploader onUploaded={handleUploaded} disabled={running} />

      {uploaded.length > 0 && <UploadedFilesCard uploaded={uploaded} />}

      <Selectors
        models={models}
        skills={skills}
        modelId={modelId}
        skillId={skillId}
        onModelChange={setModelId}
        onSkillChange={setSkillId}
      />

      <div className="ura-card">
        <h3>3. Run review</h3>
        <button
          className="primary"
          disabled={!uploaded.length || running}
          onClick={runAnalysis}
        >
          {running ? "Reviewing… this can take a minute" : "Run Universal Review Agent"}
        </button>
        {!uploaded.length && (
          <p className="muted" style={{ marginTop: 8 }}>
            Upload at least one file to enable this button.
          </p>
        )}
      </div>

      {results.length > 0 && (
        <ResultsSection
          results={results}
          scoring={scoring}
          selectedChunkId={selectedChunkId}
          onSelect={setSelectedChunkId}
        />
      )}
    </div>
  );
}

function groupUploaded(uploaded) {
  const folders = {};   // { folderName: [{ file_id, filePath, language, size_bytes }] }
  const looseFiles = [];
  for (const f of uploaded) {
    const slash = f.file_name.indexOf("/");
    if (slash === -1) {
      looseFiles.push(f);
    } else {
      const folder = f.file_name.slice(0, slash);
      const filePath = f.file_name.slice(slash + 1);
      if (!folders[folder]) folders[folder] = [];
      folders[folder].push({ ...f, filePath });
    }
  }
  return { folders, looseFiles };
}

function UploadedFilesCard({ uploaded }) {
  const { folders, looseFiles } = useMemo(() => groupUploaded(uploaded), [uploaded]);
  const [openFolders, setOpenFolders] = useState(new Set());

  // Open all folders whenever the uploaded list changes.
  useEffect(() => {
    setOpenFolders(new Set(Object.keys(groupUploaded(uploaded).folders)));
  }, [uploaded]);

  function toggle(folder) {
    setOpenFolders((prev) => {
      const next = new Set(prev);
      next.has(folder) ? next.delete(folder) : next.add(folder);
      return next;
    });
  }

  return (
    <div className="ura-card">
      <h3>Uploaded files</h3>

      {/* Folder groups — interactive accordion */}
      {Object.entries(folders).map(([folder, files]) => (
        <div key={folder} className="ura-folder-section" style={{ marginBottom: 8 }}>
          <div
            className="ura-folder-header"
            style={{ cursor: "pointer" }}
            onClick={() => toggle(folder)}
          >
            <span className="ura-folder-icon">📁</span>
            <span className="ura-folder-name">{folder}/</span>
            <span className="ura-folder-meta muted">
              {files.length} file{files.length !== 1 ? "s" : ""}
            </span>
            <span className="ura-file-chevron">
              {openFolders.has(folder) ? "▲" : "▼"}
            </span>
          </div>
          {openFolders.has(folder) && (
            <div className="ura-folder-body">
              {files.map((f) => (
                <div key={f.file_id} className="ura-file-header" style={{ cursor: "default" }}>
                  <span className="ura-file-icon">📄</span>
                  <span className="ura-file-path">{f.filePath}</span>
                  <span className="ura-file-meta muted">
                    {f.language} · {f.size_bytes} bytes
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Loose files — flat list */}
      {looseFiles.length > 0 && (
        <ul className="ura-file-list" style={{ marginTop: Object.keys(folders).length ? 8 : 0 }}>
          {looseFiles.map((f) => (
            <li key={f.file_id}>
              {f.file_name}{" "}
              <span className="muted">· {f.language} · {f.size_bytes} bytes</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CategoryIssuesPanel({ category, issues, onClose }) {
  return (
    <div className="ura-card ura-cat-panel">
      <div className="ura-cat-panel-head">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className={`ura-cat-badge ura-cat-${category}`}>{category}</span>
          <span className="ura-cat-panel-title">
            {issues.length} issue{issues.length !== 1 ? "s" : ""}
          </span>
        </div>
        <button className="ura-cat-close" onClick={onClose}>✕ Close</button>
      </div>
      {issues.length === 0 ? (
        <p className="muted">No issues found for this category.</p>
      ) : (
        <div className="ura-cat-table-wrap">
          <table className="ura-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>File / Chunk</th>
                <th>Line</th>
                <th>Issue</th>
                <th>Recommendation</th>
                <th>Source</th>
                <th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((i, idx) => (
                <tr key={idx}>
                  <td>
                    <span className={`sev sev-${(i.severity || "info").toLowerCase()}`}>
                      {i.severity}
                    </span>
                  </td>
                  <td className="muted" title={`${i.file_name} · lines ${i.start_line}-${i.end_line}`}>
                    {i.chunk_id.includes("::") ? i.chunk_id.split("::").slice(1).join("::") : i.chunk_id}
                  </td>
                  <td>{i.line}</td>
                  <td>{i.issue}</td>
                  <td>{i.recommendation}</td>
                  <td className="muted">{i.source || "—"}</td>
                  <td className="muted">{typeof i.confidence === "number" ? i.confidence : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ResultsSection({ results, scoring, selectedChunkId, onSelect }) {
  const [selectedCategory, setSelectedCategory] = useState(null);

  const categoryIssues = useMemo(() => {
    if (!selectedCategory) return [];
    return results.flatMap((r) =>
      r.issues
        .filter((i) => (i.category || "uncategorized").toLowerCase() === selectedCategory.toLowerCase())
        .map((i) => ({ ...i, file_name: r.file_name, chunk_id: r.chunk_id, start_line: r.start_line, end_line: r.end_line }))
    );
  }, [selectedCategory, results]);

  function handleSelectCategory(cat) {
    setSelectedCategory((prev) => (prev === cat ? null : cat));
  }

  return (
    <section>
      <h2>Review results</h2>

      <ScoreCard
        scoring={scoring}
        selectedCategory={selectedCategory}
        onSelectCategory={handleSelectCategory}
      />

      {selectedCategory && (
        <CategoryIssuesPanel
          category={selectedCategory}
          issues={categoryIssues}
          onClose={() => setSelectedCategory(null)}
        />
      )}

      <Dashboard
        results={results}
        scoring={scoring}
        skill={results[0]?.skill}
        selectedChunkId={selectedChunkId}
        onSelectChunk={onSelect}
      />

      <FolderTreeView results={results} selectedChunkId={selectedChunkId} />
    </section>
  );
}
