// Canonical structured model definitions (single source of truth).
// provider: machine key used by backend; provider_display: human readable; description: short marketing / capability tag.
export type ModelOption = {
  alias: string;              // Short name shown in UI radios/checkboxes
  provider: string;           // Backend provider key
  provider_display: string;   // Proper-cased provider name for UI
  model_id: string;           // Provider model id (used for judge + pricing)
  description: string;        // Short descriptor (tooltip details)
  legacy_aliases?: string[];  // List of previous aliases for this slot (for seamless upgrades)
  legacy_model_ids?: string[]; // List of previous model IDs for this slot (for backend trial compatibility)
};

export const MODEL_OPTIONS: ModelOption[] = [
  { alias: "Claude Sonnet 4.6", provider: "anthropic", provider_display: "Anthropic", model_id: "claude-sonnet-4-6", description: "best agents", legacy_aliases: ["Claude Sonnet 4.5"], legacy_model_ids: ["claude-sonnet-4-5-20250929"] },
  { alias: "Claude Opus 4.7", provider: "anthropic", provider_display: "Anthropic", model_id: "claude-opus-4-7", description: "reasoning", legacy_aliases: ["Claude Opus 4.6", "Claude Opus 4.5"], legacy_model_ids: ["claude-opus-4-6", "claude-opus-4-5-20251101"] },
  { alias: "Gemini 3 Flash", provider: "gemini", provider_display: "Google", model_id: "gemini-3-flash-preview", description: "fast/cheap", legacy_aliases: ["Gemini 2.5 Flash"], legacy_model_ids: ["gemini-2.5-flash"] },
  { alias: "Gemini 3.1 Pro", provider: "gemini", provider_display: "Google", model_id: "gemini-3.1-pro-preview", description: "best quality", legacy_aliases: ["Gemini 3 Pro"], legacy_model_ids: ["gemini-3-pro-preview"] },
  { alias: "GPT-5.5 Instant", provider: "openai", provider_display: "OpenAI", model_id: "chat-latest", description: "instant", legacy_aliases: ["GPT-5.4 Mini", "GPT-5.3 Chat", "GPT-5.2 Instant"], legacy_model_ids: ["gpt-5.4-mini", "gpt-5.3-chat-latest", "gpt-5.1-instant", "gpt-5.2-chat-latest"] },
  { alias: "GPT-5.5", provider: "openai", provider_display: "OpenAI", model_id: "gpt-5.5", description: "deep reasoning", legacy_aliases: ["GPT-5.4", "GPT-5.2 Thinking"], legacy_model_ids: ["gpt-5.4", "gpt-5.1-thinking", "gpt-5.2"] },
  { alias: "Grok 4.3", provider: "xai", provider_display: "xAI", model_id: "grok-4.3", description: "latest", legacy_aliases: ["Grok 4.1 Fast Reasoning", "Grok 4 Fast", "Grok 4"], legacy_model_ids: ["grok-4-1-fast-reasoning", "grok-4-fast", "grok-4-0709", "grok-4"] },
];

// Backwards compatibility: replicate legacy DISPLAY_OPTIONS / JUDGE_OPTIONS shape so existing components keep working.
export type DisplayOption = { label: string; alias: string };

// Legacy display label (alias + em dash + provider + descriptor parenthetical) used only for:
//  - older localStorage values
//  - FULL_LABEL_BY_ALIAS mapping for tooltips
function buildLegacyDisplayLabel(m: ModelOption): string {
  return `${m.alias} — ${m.provider_display} (${m.description})`;
}

// Legacy judge label (alias + em dash + provider) — previously no descriptor parentheses.
function buildLegacyJudgeLabel(m: ModelOption): string {
  return `${m.alias} — ${m.provider_display}`;
}

export const DISPLAY_OPTIONS: DisplayOption[] = MODEL_OPTIONS.map(m => ({ alias: m.alias, label: buildLegacyDisplayLabel(m) }));

// Alias-based registry (backward compatibility - assumes unique aliases)
export const MODEL_REGISTRY: Record<string, { provider: string; model: string }> = {
  ...MODEL_OPTIONS.reduce((acc, m) => {
    acc[m.alias] = { provider: m.provider, model: m.model_id };
    // Also register legacy aliases so they resolve correctly in backend/logic
    m.legacy_aliases?.forEach(legacy => {
      acc[legacy] = { provider: m.provider, model: m.model_id };
    });
    return acc;
  }, {} as Record<string, { provider: string; model: string }>),
};

// Model ID registry for quick lookup
export const MODEL_REGISTRY_BY_ID: Record<string, ModelOption> = MODEL_OPTIONS.reduce((acc, m) => {
  acc[m.model_id] = m;
  m.legacy_model_ids?.forEach((legacyId) => {
    acc[legacyId] = m;
  });
  return acc;
}, {} as Record<string, ModelOption>);

// Helper to find model by model_id
export function findModelByModelId(modelId: string): ModelOption | null {
  return MODEL_REGISTRY_BY_ID[modelId] || null;
}

export const JUDGE_OPTIONS: { label: string; provider: string; model_id: string }[] = MODEL_OPTIONS.map(m => ({ label: buildLegacyJudgeLabel(m), provider: m.provider, model_id: m.model_id }));


// Derive alias + tooltip (rest of label after alias) from either DISPLAY_OPTIONS label or JUDGE_OPTIONS label.
export function deriveAliasAndTooltip(labelOrAlias: string, providedAlias?: string): { alias: string; tooltip: string; rest: string } {
  // Prefer explicit alias param, else attempt lookup.
  let alias = providedAlias || labelOrAlias;
  // Normalize if a legacy label was passed in (stored in localStorage before refactor).
  if (alias.includes(" — ")) {
    alias = alias.split(" — ")[0];
  }

  // Handle renamed aliases (seamless upgrade via legacy_aliases)
  // This allows "Grok 4 Fast" to become "Grok 5 Fast" seamlessly if defined in legacy_aliases.
  let meta = MODEL_OPTIONS.find(m => m.alias === alias);
  
  if (!meta) {
    // Try to find a model that claims this alias as a legacy alias
    meta = MODEL_OPTIONS.find(m => m.legacy_aliases?.includes(alias));
    if (meta) {
      alias = meta.alias; // Upgrade the alias to the new one
    }
  }

  if (!meta) {
    return { alias, tooltip: labelOrAlias, rest: labelOrAlias }; // fallback: unknown alias
  }
  const rest = `${meta.provider_display} (${meta.description})`;
  const tooltip = rest;
  return { alias: meta.alias, tooltip, rest };
}

// Storage keys (per-phase selections)
export const FIT_MODEL_STORAGE_KEY = "__rt_fit_model_label";
export const TAILOR_MODEL_STORAGE_KEY = "__rt_tailor_model_label";
export const JUDGE_STORAGE_KEY = "__rt_judge_label";
export const SHOW_JUDGE_STORAGE_KEY = "__rt_show_judge";
// Persist timing stats (Total / Fit / Tailor / Judge) for Resume Tailor page
export const RESUME_STATS_KEY = "__rt_resume_stats";
export const RESUME_STATS_TS_KEY = "__rt_resume_stats_ts";
