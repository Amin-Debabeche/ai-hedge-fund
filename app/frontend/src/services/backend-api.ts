// Checks whether this app's own backend (not any specific provider like
// Ollama) is reachable at all. Used as the first pre-run gate, since every
// model provider - local or cloud - is proxied through this backend.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function isBackendReachable(): Promise<boolean> {
  try {
    const response = await fetch(API_BASE_URL, { signal: AbortSignal.timeout(4000) });
    return response.ok;
  } catch {
    return false;
  }
}
