import { api } from '@/services/api';

export interface LanguageModel {
  display_name: string;
  model_name: string;
  provider: "Anthropic" | "DeepSeek" | "Google" | "Groq" | "OpenAI" | "Ollama" | "Vercel";
}

// Always-available local model option: lets a user pick "run this agent
// locally with Ollama" even before the model has been downloaded. The
// pre-run readiness check (use-ollama-preflight) prompts to download it.
export const OLLAMA_LOCAL_MODEL: LanguageModel = {
  display_name: 'Qwen3 (4B) - Local (Ollama)',
  model_name: 'qwen3:4b',
  provider: 'Ollama',
};

// Cache for models to avoid repeated API calls
let languageModels: LanguageModel[] | null = null;

/**
 * Get the list of models from the backend API
 * Uses caching to avoid repeated API calls
 */
export const getModels = async (): Promise<LanguageModel[]> => {
  if (languageModels) {
    return languageModels;
  }

  try {
    const models = await api.getLanguageModels();
    const hasLocalOllamaModel = models.some(m => m.model_name === OLLAMA_LOCAL_MODEL.model_name);
    languageModels = hasLocalOllamaModel ? models : [...models, OLLAMA_LOCAL_MODEL];
    return languageModels;
  } catch (error) {
    console.error('Failed to fetch models:', error);
    throw error; // Let the calling component handle the error
  }
};

/**
 * Get the default model (GPT-4.1) from the models list
 */
export const getDefaultModel = async (): Promise<LanguageModel | null> => {
  try {
    const models = await getModels();
    return models.find(model => model.model_name === "gpt-4.1") || models[0] || null;
  } catch (error) {
    console.error('Failed to get default model:', error);
    return null;
  }
};
