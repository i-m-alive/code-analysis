export default function Selectors({
  models,
  strategies,
  skills,
  modelId,
  strategyId,
  skillId,
  onModelChange,
  onStrategyChange,
  onSkillChange,
}) {
  return (
    <div className="ura-card">
      <h3>2. Configure run</h3>
      <div className="ura-row">
        <label>
          Model
          <select
            value={modelId}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {models.map((m) => {
              const rec = m.recommended ? " ★" : "";
              const status = m.installed ? "✓ installed" : "(not pulled)";
              return (
                <option key={m.id} value={m.id}>
                  {m.label}{rec} — {m.id} {status}
                </option>
              );
            })}
          </select>
        </label>

        <label>
          Chunking strategy
          <select
            value={strategyId}
            onChange={(e) => onStrategyChange(e.target.value)}
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Skill
          <select
            value={skillId}
            onChange={(e) => onSkillChange(e.target.value)}
          >
            {skills.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
