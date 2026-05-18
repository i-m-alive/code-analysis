import axios from "axios";

// During `vite dev` requests to /api/* are proxied to FastAPI on :8000.
// In production builds you can point this directly at the backend URL.
// SLM calls on CPU can be very slow when reviewing many chunks. Disable
// the axios timeout entirely (0 = no timeout) so the client waits as long
// as the backend needs. The user can always reload the tab to cancel.
const client = axios.create({
  baseURL: "/api",
  timeout: 0,
});

export async function getOllamaHealth() {
  const { data } = await client.get("/ollama/health");
  return data;
}

export async function getModels() {
  const { data } = await client.get("/models");
  return data;
}

export async function getChunkingStrategies() {
  const { data } = await client.get("/chunking-strategies");
  return data;
}

export async function getSkills() {
  const { data } = await client.get("/skills");
  return data;
}

export async function uploadFiles(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const { data } = await client.post("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function analyze({ file_ids, model_id, chunking_strategy, skill }) {
  const { data } = await client.post("/analyze", {
    file_ids,
    model_id,
    chunking_strategy,
    skill,
  });
  return data;
}

export default client;
