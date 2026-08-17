// Client for the backend's local Ollama management endpoints.
// Used both by the Settings > Ollama panel and the pre-run readiness check.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface OllamaStatus {
  installed: boolean;
  running: boolean;
  available_models: string[];
  server_url: string;
  error?: string;
}

export interface OllamaDownloadProgress {
  status: string;
  percentage?: number;
  message?: string;
  error?: string;
}

export async function getOllamaStatus(): Promise<OllamaStatus> {
  const response = await fetch(`${API_BASE_URL}/ollama/status`);
  if (!response.ok) {
    throw new Error(`Failed to get Ollama status (${response.status})`);
  }
  return response.json();
}

export async function startOllamaServer(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/ollama/start`, { method: 'POST' });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(errorData.detail || 'Failed to start Ollama server');
  }
}

/**
 * Downloads a model, reporting progress via onProgress, resolving when the
 * download completes and rejecting on error/cancellation.
 */
export async function downloadOllamaModel(
  modelName: string,
  onProgress?: (progress: OllamaDownloadProgress) => void
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/ollama/models/download/progress`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_name: modelName }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(errorData.detail || `Failed to start download for ${modelName}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response stream available for download progress');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let done = false;

  while (!done) {
    const chunk = await reader.read();
    done = chunk.done;
    if (done) break;
    const value = chunk.value;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const jsonData = line.slice(6).trim();
      if (!jsonData) continue;

      let data: OllamaDownloadProgress;
      try {
        data = JSON.parse(jsonData);
      } catch {
        continue;
      }

      onProgress?.(data);

      if (data.status === 'completed') {
        return;
      }
      if (data.status === 'error' || data.status === 'cancelled') {
        throw new Error(data.error || data.message || `Download of ${modelName} failed`);
      }
    }
  }
}
