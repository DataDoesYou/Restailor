/**
 * Unit tests for apiClient ModelSettings functions.
 * 
 * Tests type safety and API integration (mocked).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { getUserSettings, putUserSettings, type ModelSettings } from "../lib/apiClient";
import * as apiModule from "../lib/api";

// Mock the api module
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

describe("apiClient - ModelSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("getUserSettings", () => {
    it("should fetch and return user settings", async () => {
      const mockSettings: ModelSettings = {
        multi_model_enabled: true,
        fit_models: ["gpt-5"],
        tailor_models: ["claude-4.1-opus"],
        judge_models: [],
        last_single_fit: null,
        last_single_tailor: null,
        last_single_judge: null,
        updated_at: "2025-10-14T12:00:00Z",
        version: 1,
      };

      vi.mocked(apiModule.api.get).mockResolvedValue({
        settings: mockSettings,
      });

      const result = await getUserSettings();

      expect(apiModule.api.get).toHaveBeenCalledWith("/users/me/model-settings");
      expect(result).toEqual(mockSettings);
    });

    it("should return default settings when none exist", async () => {
      const defaultSettings: ModelSettings = {
        multi_model_enabled: false,
        fit_models: [],
        tailor_models: [],
        judge_models: [],
        last_single_fit: null,
        last_single_tailor: null,
        last_single_judge: null,
        updated_at: null,
        version: 1,
      };

      vi.mocked(apiModule.api.get).mockResolvedValue({
        settings: defaultSettings,
      });

      const result = await getUserSettings();

      expect(result.multi_model_enabled).toBe(false);
      expect(result.fit_models).toEqual([]);
    });
  });

  describe("putUserSettings", () => {
    it("should update settings without optimistic lock", async () => {
      const updatedSettings: ModelSettings = {
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus"],
        tailor_models: [],
        judge_models: [],
        last_single_fit: null,
        last_single_tailor: null,
        last_single_judge: null,
        updated_at: "2025-10-14T12:01:00Z",
        version: 1,
      };

      vi.mocked(apiModule.api.put).mockResolvedValue({
        settings: updatedSettings,
        message: "Settings updated successfully",
      });

      const result = await putUserSettings({
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus"],
        tailor_models: [],
        judge_models: [],
        version: 1,
      });

      expect(apiModule.api.put).toHaveBeenCalledWith(
        "/users/me/model-settings",
        expect.objectContaining({
          settings: expect.objectContaining({
            multi_model_enabled: true,
            fit_models: ["gpt-5", "claude-4.1-opus"],
          }),
        })
      );
      expect(result).toEqual(updatedSettings);
    });

    it("should include expectedUpdatedAt for optimistic locking", async () => {
      const updatedSettings: ModelSettings = {
        multi_model_enabled: false,
        fit_models: [],
        tailor_models: ["gemini-3-pro-preview"],
        judge_models: [],
        last_single_fit: null,
        last_single_tailor: null,
        last_single_judge: null,
        updated_at: "2025-10-14T12:02:00Z",
        version: 1,
      };

      vi.mocked(apiModule.api.put).mockResolvedValue({
        settings: updatedSettings,
        message: "Settings updated successfully",
      });

      const oldTimestamp = "2025-10-14T12:00:00Z";
      
      await putUserSettings({
        multi_model_enabled: false,
        fit_models: [],
        tailor_models: ["gemini-3-pro-preview"],
        judge_models: [],
        version: 1,
        expected_updated_at: oldTimestamp,
      });

      expect(apiModule.api.put).toHaveBeenCalledWith(
        "/users/me/model-settings",
        expect.objectContaining({
          expectedUpdatedAt: oldTimestamp,
        })
      );
    });

    it("should handle partial updates", async () => {
      const updatedSettings: ModelSettings = {
        multi_model_enabled: true,
        fit_models: ["gpt-5"],
        tailor_models: [],
        judge_models: [],
        last_single_fit: null,
        last_single_tailor: null,
        last_single_judge: null,
        updated_at: "2025-10-14T12:03:00Z",
        version: 1,
      };

      vi.mocked(apiModule.api.put).mockResolvedValue({
        settings: updatedSettings,
        message: "Settings updated successfully",
      });

      // Partial update with just a few fields
      await putUserSettings({
        multi_model_enabled: true,
        fit_models: ["gpt-5"],
        tailor_models: [],
        judge_models: [],
        version: 1,
      });

      expect(apiModule.api.put).toHaveBeenCalledWith(
        "/users/me/model-settings",
        expect.objectContaining({
          settings: expect.any(Object),
        })
      );
    });
  });

  describe("Type Safety", () => {
    it("ModelSettings type should enforce required fields", () => {
      // This is a compile-time test - if it compiles, types are correct
      const validSettings: ModelSettings = {
        multi_model_enabled: false,
        fit_models: [],
        tailor_models: [],
        judge_models: [],
        version: 1,
        // Optional fields can be omitted
      };

      expect(validSettings.version).toBe(1);
    });

    it("should allow null for optional string fields", () => {
      const settings: ModelSettings = {
        multi_model_enabled: false,
        fit_models: [],
        tailor_models: [],
        judge_models: [],
        last_single_fit: null,
        last_single_tailor: null,
        last_single_judge: null,
        updated_at: null,
        version: 1,
      };

      expect(settings.last_single_fit).toBeNull();
    });
  });
});
