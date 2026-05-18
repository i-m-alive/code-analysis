export default function Header({ activeModel, activeStrategy, activeSkill }) {
  return (
    <header className="ura-header">
      <div>
        <h1>Universal Review Agent</h1>
        <p className="ura-subtitle">
          Local SLM-powered, skill-based static code review.
        </p>
      </div>
      <div className="ura-active-meta">
        <span className="chip">Model: {activeModel || "—"}</span>
        <span className="chip">Chunking: {activeStrategy || "—"}</span>
        <span className="chip">Skill: {activeSkill || "—"}</span>
      </div>
    </header>
  );
}
