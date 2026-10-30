// Older builds pre-filled these and saved them to localStorage, where they override the server's
// OPENPRISM_LLM_* settings. With no key of the user's own they are leftovers, not a choice.
const LEGACY_ENDPOINT = 'https://api.openai.com/v1/chat/completions';
const LEGACY_MODEL = 'gpt-4o-mini';

export function dropLegacyLlmDefaults<T extends { llmEndpoint?: string; llmApiKey?: string; llmModel?: string }>(s: T): T {
  if (s.llmApiKey) return s;
  return {
    ...s,
    llmEndpoint: s.llmEndpoint === LEGACY_ENDPOINT ? '' : s.llmEndpoint,
    llmModel: s.llmModel === LEGACY_MODEL ? '' : s.llmModel
  };
}
