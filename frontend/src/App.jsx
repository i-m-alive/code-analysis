import { useEffect, useState } from "react";

import {
  analyze,
  getChunkingStrategies,
  getModels,
  getOllamaHealth,
  getSkills,
  uploadFiles,
} from "./api/client";
import ChunkPicker from "./components/ChunkPicker";
import Dashboard from "./components/Dashboard";
import FileUploader from "./components/FileUploader";
import FindingsTable from "./components/FindingsTable";
import HealthBanner from "./components/HealthBanner";
import Header from "./components/Header";
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
  const [strategies, setStrategies] = useState([]);
  const [skills, setSkills] = useState([]);
  const [modelId, setModelId] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [skillId, setSkillId] = useState("");
  const [uploaded, setUploaded] = useState([]);
  const [results, setResults] = useState([]);
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
        const [m, s, sk] = await Promise.all([
          getModels(),
          getChunkingStrategies(),
          getSkills(),
        ]);
        setModels(m.models);
        setModelId(m.active);
        setStrategies(s.strategies);
        setStrategyId(s.active);
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
        chunking_strategy: strategyId,
        skill: skillId,
      });
      const list = res.results || [];
      setResults(list);
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
      <Header
        activeModel={modelId}
        activeStrategy={strategyId}
        activeSkill={skillId}
      />

      <HealthBanner health={health} activeModel={modelId} />

      {error && <div className="ura-error">{error}</div>}

      <FileUploader onUploaded={handleUploaded} disabled={running} />

      {uploaded.length > 0 && (
        <div className="ura-card">
          <h3>Uploaded files</h3>
          <ul className="ura-file-list">
            {uploaded.map((f) => (
              <li key={f.file_id}>
                {f.file_name}{" "}
                <span className="muted">
                  · {f.language} · {f.size_bytes} bytes
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Selectors
        models={models}
        strategies={strategies}
        skills={skills}
        modelId={modelId}
        strategyId={strategyId}
        skillId={skillId}
        onModelChange={setModelId}
        onStrategyChange={setStrategyId}
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
          selectedChunkId={selectedChunkId}
          onSelect={setSelectedChunkId}
        />
      )}
    </div>
  );
}

function ResultsSection({ results, selectedChunkId, onSelect }) {
  const selected = results.find((r) => r.chunk_id === selectedChunkId) || results[0];

  return (
    <section>
      <h2>Review results</h2>

      <Dashboard
        results={results}
        skill={results[0]?.skill}
        selectedChunkId={selectedChunkId}
        onSelectChunk={onSelect}
      />

      <div className="ura-card">
        <ChunkPicker
          results={results}
          value={selectedChunkId}
          onChange={onSelect}
        />
      </div>

      {selected && <FindingsTable result={selected} />}
    </section>
  );
}
