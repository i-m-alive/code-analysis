export default function HealthBanner({ health, activeModel }) {
  if (!health) return null;

  if (!health.reachable) {
    return (
      <div className="ura-banner ura-banner-error">
        <strong>Ollama is not running.</strong>{" "}
        Start it in another terminal with <code>ollama serve</code>. The Run
        button will still produce deterministic findings, but no SLM reasoning.
      </div>
    );
  }

  const target = activeModel || health.active_model;
  const pulled = health.installed_models.some(
    (m) => m === target || m.split(":")[0] === target.split(":")[0]
  );
  if (!pulled) {
    return (
      <div className="ura-banner ura-banner-warn">
        <strong>Model <code>{target}</code> is not pulled.</strong>{" "}
        Run <code>ollama pull {target}</code> in a terminal, then refresh.{" "}
        <span className="muted">
          Pulled locally: {health.installed_models.join(", ") || "(none)"}
        </span>
      </div>
    );
  }

  return (
    <div className="ura-banner ura-banner-ok">
      Ollama is running. Active model <code>{target}</code> is pulled and ready.
    </div>
  );
}
