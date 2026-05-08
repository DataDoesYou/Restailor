/**
 * Tests for Model Selection Adapter
 */

import { describe, it, expect } from "vitest";
import {
  enterMulti,
  leaveMulti,
  toggleCheckbox,
  selectRadio,
  selectAll,
  clearAll,
  effectiveSelected,
  isModelSelected,
  getSelectedCount,
  hasSelection,
  type ModelRole,
} from "../lib/modelSelectionAdapter";
import type { ModelSettings } from "../lib/apiClient";

// Test fixture: default settings
const createDefaultSettings = (): ModelSettings => ({
  multi_model_enabled: false,
  fit_models: [],
  tailor_models: [],
  judge_models: [],
  last_single_fit: null,
  last_single_tailor: null,
  last_single_judge: null,
  updated_at: "2025-10-14T12:00:00Z",
  version: 1,
});

describe("modelSelectionAdapter", () => {
  describe("enterMulti", () => {
    it("should enable multi-model mode", () => {
      const settings = createDefaultSettings();
      const result = enterMulti(settings);

      expect(result.multi_model_enabled).toBe(true);
    });

    it("should seed arrays from last_single_* when arrays are empty", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        last_single_fit: "gpt-5",
        last_single_tailor: "claude-4.1-opus",
        last_single_judge: "gemini-3.1-pro-preview",
      };

      const result = enterMulti(settings);

      expect(result.fit_models).toEqual(["gpt-5"]);
      expect(result.tailor_models).toEqual(["claude-4.1-opus"]);
      expect(result.judge_models).toEqual(["gemini-3.1-pro-preview"]);
    });

    it("should preserve existing arrays if not empty", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5", "claude-4.1-opus"],
        tailor_models: ["gemini-3.1-pro-preview"],
        judge_models: [],
        last_single_fit: "grok-4-1-fast-reasoning",
        last_single_tailor: "grok-4-1-fast-reasoning",
        last_single_judge: "grok-4-1-fast-reasoning",
      };

      const result = enterMulti(settings);

      expect(result.fit_models).toEqual(["gpt-5", "claude-4.1-opus"]);
      expect(result.tailor_models).toEqual(["gemini-3.1-pro-preview"]);
      expect(result.judge_models).toEqual(["grok-4-1-fast-reasoning"]); // Seeded from last_single_judge
    });

    it("should leave arrays empty if no last_single_* values", () => {
      const settings = createDefaultSettings();
      const result = enterMulti(settings);

      expect(result.fit_models).toEqual([]);
      expect(result.tailor_models).toEqual([]);
      expect(result.judge_models).toEqual([]);
    });

    it("should not mutate original settings", () => {
      const settings = createDefaultSettings();
      const original = { ...settings };
      enterMulti(settings);

      expect(settings).toEqual(original);
    });
  });

  describe("leaveMulti", () => {
    it("should disable multi-model mode", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
      };

      const result = leaveMulti(settings);

      expect(result.multi_model_enabled).toBe(false);
    });

    it("should capture first selected from each array to last_single_*", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus"],
        tailor_models: ["gemini-3.1-pro-preview", "grok-4-1-fast-reasoning"],
        judge_models: ["gpt-5"],
      };

      const result = leaveMulti(settings);

      expect(result.last_single_fit).toBe("gpt-5");
      expect(result.last_single_tailor).toBe("gemini-3.1-pro-preview");
      expect(result.last_single_judge).toBe("gpt-5");
    });

    it("should keep previous last_single_* if array is empty", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: [],
        tailor_models: [],
        judge_models: [],
        last_single_fit: "gpt-5",
        last_single_tailor: "claude-4.1-opus",
        last_single_judge: "gemini-3.1-pro-preview",
      };

      const result = leaveMulti(settings);

      expect(result.last_single_fit).toBe("gpt-5");
      expect(result.last_single_tailor).toBe("claude-4.1-opus");
      expect(result.last_single_judge).toBe("gemini-3.1-pro-preview");
    });

    it("should not mutate original settings", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
      };
      const original = { ...settings };
      leaveMulti(settings);

      expect(settings).toEqual(original);
    });
  });

  describe("toggleCheckbox", () => {
    it("should add model if not present", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5"],
      };

      const result = toggleCheckbox("fit", "claude-4.1-opus", settings);

      expect(result.fit_models).toEqual(["gpt-5", "claude-4.1-opus"]);
    });

    it("should remove model if already present", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5", "claude-4.1-opus"],
      };

      const result = toggleCheckbox("fit", "gpt-5", settings);

      expect(result.fit_models).toEqual(["claude-4.1-opus"]);
    });

    it("should work for all roles", () => {
      const settings = createDefaultSettings();

      const withFit = toggleCheckbox("fit", "gpt-5", settings);
      expect(withFit.fit_models).toEqual(["gpt-5"]);

      const withTailor = toggleCheckbox("tailor", "claude-4.1-opus", settings);
      expect(withTailor.tailor_models).toEqual(["claude-4.1-opus"]);

      const withJudge = toggleCheckbox("judge", "gemini-3.1-pro-preview", settings);
      expect(withJudge.judge_models).toEqual(["gemini-3.1-pro-preview"]);
    });

    it("should not mutate original settings", () => {
      const settings = createDefaultSettings();
      const original = { ...settings };
      toggleCheckbox("fit", "gpt-5", settings);

      expect(settings).toEqual(original);
    });
  });

  describe("selectRadio", () => {
    it("should set last_single_* field", () => {
      const settings = createDefaultSettings();

      const result = selectRadio("fit", "gpt-5", settings);

      expect(result.last_single_fit).toBe("gpt-5");
    });

    it("should allow setting to null", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        last_single_tailor: "gpt-5",
      };

      const result = selectRadio("tailor", null, settings);

      expect(result.last_single_tailor).toBeNull();
    });

    it("should work for all roles", () => {
      const settings = createDefaultSettings();

      const withFit = selectRadio("fit", "gpt-5", settings);
      expect(withFit.last_single_fit).toBe("gpt-5");

      const withTailor = selectRadio("tailor", "claude-4.1-opus", settings);
      expect(withTailor.last_single_tailor).toBe("claude-4.1-opus");

      const withJudge = selectRadio("judge", "gemini-3.1-pro-preview", settings);
      expect(withJudge.last_single_judge).toBe("gemini-3.1-pro-preview");
    });

    it("should not mutate original settings", () => {
      const settings = createDefaultSettings();
      const original = { ...settings };
      selectRadio("fit", "gpt-5", settings);

      expect(settings).toEqual(original);
    });
  });

  describe("selectAll", () => {
    it("should replace role array with all model IDs", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5"],
      };

      const allModels = ["gpt-5", "claude-4.1-opus", "gemini-3.1-pro-preview", "grok-4-1-fast-reasoning"];
      const result = selectAll("fit", allModels, settings);

      expect(result.fit_models).toEqual(allModels);
    });

    it("should work for all roles", () => {
      const settings = createDefaultSettings();
      const allModels = ["gpt-5", "claude-4.1-opus"];

      const withFit = selectAll("fit", allModels, settings);
      expect(withFit.fit_models).toEqual(allModels);

      const withTailor = selectAll("tailor", allModels, settings);
      expect(withTailor.tailor_models).toEqual(allModels);

      const withJudge = selectAll("judge", allModels, settings);
      expect(withJudge.judge_models).toEqual(allModels);
    });

    it("should not mutate original settings or input array", () => {
      const settings = createDefaultSettings();
      const original = { ...settings };
      const allModels = ["gpt-5", "claude-4.1-opus"];
      const originalModels = [...allModels];

      const result = selectAll("fit", allModels, settings);

      expect(settings).toEqual(original);
      expect(allModels).toEqual(originalModels);
      expect(result.fit_models).not.toBe(allModels); // Should be a copy
    });
  });

  describe("clearAll", () => {
    it("should clear role array", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5", "claude-4.1-opus"],
      };

      const result = clearAll("fit", settings);

      expect(result.fit_models).toEqual([]);
    });

    it("should work for all roles", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5"],
        tailor_models: ["claude-4.1-opus"],
        judge_models: ["gemini-3.1-pro-preview"],
      };

      const withoutFit = clearAll("fit", settings);
      expect(withoutFit.fit_models).toEqual([]);

      const withoutTailor = clearAll("tailor", settings);
      expect(withoutTailor.tailor_models).toEqual([]);

      const withoutJudge = clearAll("judge", settings);
      expect(withoutJudge.judge_models).toEqual([]);
    });

    it("should not mutate original settings", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        fit_models: ["gpt-5"],
      };
      const original = { ...settings, fit_models: [...settings.fit_models] };
      clearAll("fit", settings);

      expect(settings).toEqual(original);
    });
  });

  describe("effectiveSelected", () => {
    it("should return role array when multi-model enabled", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus"],
        last_single_fit: "gemini-3.1-pro-preview", // Should be ignored
      };

      const result = effectiveSelected("fit", settings);

      expect(result).toEqual(["gpt-5", "claude-4.1-opus"]);
    });

    it("should return last_single_* as array when multi-model disabled", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        fit_models: ["claude-4.1-opus"], // Should be ignored
        last_single_fit: "gpt-5",
      };

      const result = effectiveSelected("fit", settings);

      expect(result).toEqual(["gpt-5"]);
    });

    it("should return empty array when multi-model disabled and last_single_* is null", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        fit_models: ["gpt-5"], // Should be ignored
        last_single_fit: null,
      };

      const result = effectiveSelected("fit", settings);

      expect(result).toEqual([]);
    });

    it("should work for all roles", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5"],
        tailor_models: ["claude-4.1-opus", "gemini-3.1-pro-preview"],
        judge_models: [],
      };

      expect(effectiveSelected("fit", settings)).toEqual(["gpt-5"]);
      expect(effectiveSelected("tailor", settings)).toEqual(["claude-4.1-opus", "gemini-3.1-pro-preview"]);
      expect(effectiveSelected("judge", settings)).toEqual([]);
    });
  });

  describe("isModelSelected", () => {
    it("should return true if model is in effective selection", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus"],
      };

      expect(isModelSelected("fit", "gpt-5", settings)).toBe(true);
      expect(isModelSelected("fit", "claude-4.1-opus", settings)).toBe(true);
    });

    it("should return false if model is not in effective selection", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5"],
      };

      expect(isModelSelected("fit", "claude-4.1-opus", settings)).toBe(false);
    });

    it("should work in single-model mode", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        last_single_tailor: "gpt-5",
      };

      expect(isModelSelected("tailor", "gpt-5", settings)).toBe(true);
      expect(isModelSelected("tailor", "claude-4.1-opus", settings)).toBe(false);
    });
  });

  describe("getSelectedCount", () => {
    it("should return count of selected models", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus", "gemini-3.1-pro-preview"],
      };

      expect(getSelectedCount("fit", settings)).toBe(3);
    });

    it("should return 0 for empty selection", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: [],
      };

      expect(getSelectedCount("fit", settings)).toBe(0);
    });

    it("should return 1 in single-model mode with selection", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        last_single_judge: "gpt-5",
      };

      expect(getSelectedCount("judge", settings)).toBe(1);
    });

    it("should return 0 in single-model mode without selection", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        last_single_judge: null,
      };

      expect(getSelectedCount("judge", settings)).toBe(0);
    });
  });

  describe("hasSelection", () => {
    it("should return true if any models selected", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: ["gpt-5"],
      };

      expect(hasSelection("fit", settings)).toBe(true);
    });

    it("should return false if no models selected", () => {
      const settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
        fit_models: [],
      };

      expect(hasSelection("fit", settings)).toBe(false);
    });

    it("should work in single-model mode", () => {
      const withSelection: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        last_single_tailor: "gpt-5",
      };

      const withoutSelection: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: false,
        last_single_tailor: null,
      };

      expect(hasSelection("tailor", withSelection)).toBe(true);
      expect(hasSelection("tailor", withoutSelection)).toBe(false);
    });
  });

  describe("Immutability", () => {
    it("all functions should return new objects", () => {
      const settings = createDefaultSettings();

      const results = [
        enterMulti(settings),
        leaveMulti(settings),
        toggleCheckbox("fit", "gpt-5", settings),
        selectRadio("fit", "gpt-5", settings),
        selectAll("fit", ["gpt-5"], settings),
        clearAll("fit", settings),
      ];

      // All results should be different objects
      results.forEach((result) => {
        expect(result).not.toBe(settings);
      });

      // Original should be unchanged
      expect(settings).toEqual(createDefaultSettings());
    });
  });

  describe("Integration scenarios", () => {
    it("should handle complete multi-model workflow", () => {
      // Start in single-model mode with a selection
      let settings: ModelSettings = {
        ...createDefaultSettings(),
        last_single_fit: "gpt-5",
      };

      // Enter multi-model mode (seeds from single selection)
      settings = enterMulti(settings);
      expect(settings.multi_model_enabled).toBe(true);
      expect(settings.fit_models).toEqual(["gpt-5"]);

      // Add more models
      settings = toggleCheckbox("fit", "claude-4.1-opus", settings);
      settings = toggleCheckbox("fit", "gemini-3.1-pro-preview", settings);
      expect(effectiveSelected("fit", settings)).toEqual([
        "gpt-5",
        "claude-4.1-opus",
        "gemini-3.1-pro-preview",
      ]);

      // Leave multi-model mode (captures first selection)
      settings = leaveMulti(settings);
      expect(settings.multi_model_enabled).toBe(false);
      expect(settings.last_single_fit).toBe("gpt-5");
      expect(effectiveSelected("fit", settings)).toEqual(["gpt-5"]);
    });

    it("should handle select all / clear all workflow", () => {
      let settings: ModelSettings = {
        ...createDefaultSettings(),
        multi_model_enabled: true,
      };

      const allModels = ["gpt-5", "claude-4.1-opus", "gemini-3.1-pro-preview", "grok-4-1-fast-reasoning"];

      // Select all
      settings = selectAll("tailor", allModels, settings);
      expect(getSelectedCount("tailor", settings)).toBe(4);

      // Clear all
      settings = clearAll("tailor", settings);
      expect(getSelectedCount("tailor", settings)).toBe(0);
      expect(hasSelection("tailor", settings)).toBe(false);
    });

    it("should handle radio button selection workflow", () => {
      let settings = createDefaultSettings();

      // Select model A
      settings = selectRadio("judge", "gpt-5", settings);
      expect(effectiveSelected("judge", settings)).toEqual(["gpt-5"]);

      // Switch to model B
      settings = selectRadio("judge", "claude-4.1-opus", settings);
      expect(effectiveSelected("judge", settings)).toEqual(["claude-4.1-opus"]);

      // Clear selection
      settings = selectRadio("judge", null, settings);
      expect(effectiveSelected("judge", settings)).toEqual([]);
    });
  });
});
