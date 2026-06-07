export default function Selectors({ models, skills, modelId, skillId, onModelChange, onSkillChange }) {
  return (
    <div className="ura-card">
      <h3>2. Configure run</h3>
      <div className="ura-row">
        <label>
          Model
          <select value={modelId} onChange={(e) => onModelChange(e.target.value)}>
            {models.map((m) => {
              const rec = m.recommended ? " *" : "";
              const status =
                m.provider === "bedrock"
                  ? (m.installed ? "configured" : "not configured")
                  : (m.installed ? "installed" : "not pulled");
              return (
                <option key={m.id} value={m.id}>
                  {m.label}{rec} - {m.id} ({status})
                </option>
              );
            })}
          </select>
        </label>

        <label>
          Skill
          <select value={skillId} onChange={(e) => onSkillChange(e.target.value)}>
            {skills.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
