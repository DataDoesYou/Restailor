/**
 * Tests for useModelSettings hook.
 * 
 * Database-only storage - no localStorage or cookie caching.
 * Tests fetching, saving, optimistic locking, and error handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useModelSettings } from "../hooks/useModelSettings";
import * as apiClient from "../lib/apiClient";
import type { ModelSettings } from "../lib/apiClient";

// Mock the API client
vi.mock("../lib/apiClient", () => ({
  getUserSettings: vi.fn(),
  putUserSettings: vi.fn(),
}));

describe("useModelSettings", () => {
  const mockSettings: ModelSettings = {
    multi_model_enabled: false,
    fit_models: [],
    tailor_models: [],
    judge_models: [],
    last_single_fit: "gpt-5",
    last_single_tailor: null,
    last_single_judge: null,
    updated_at: "2025-10-14T12:00:00Z",
    version: 1,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  describe("Initial Fetch", () => {
    it("should fetch settings on mount", async () => {
      vi.mocked(apiClient.getUserSettings).mockResolvedValue(mockSettings);

      const { result } = renderHook(() => useModelSettings());

      expect(result.current.isLoading).toBe(true);
      expect(result.current.settings).toBeUndefined();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiClient.getUserSettings).toHaveBeenCalledTimes(1);
      expect(result.current.settings).toEqual(mockSettings);
      expect(result.current.error).toBeNull();
    });

    it("should handle fetch errors gracefully", async () => {
      const mockError = new Error("Network error");
      vi.mocked(apiClient.getUserSettings).mockRejectedValue(mockError);

      const { result } = renderHook(() => useModelSettings());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.settings).toBeUndefined();
    });
  });

  describe("Save Mutation", () => {
    it("should save partial settings with optimistic locking", async () => {
      vi.mocked(apiClient.getUserSettings).mockResolvedValue(mockSettings);
      
      const updatedSettings: ModelSettings = {
        ...mockSettings,
        multi_model_enabled: true,
        updated_at: "2025-10-14T12:01:00Z",
      };
      vi.mocked(apiClient.putUserSettings).mockResolvedValue(updatedSettings);

      const { result } = renderHook(() => useModelSettings());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let savedResult: ModelSettings | undefined;
      await act(async () => {
        savedResult = await result.current.save({ multi_model_enabled: true });
      });

      expect(apiClient.putUserSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          multi_model_enabled: true,
          expected_updated_at: mockSettings.updated_at,
        })
      );

      expect(result.current.settings).toEqual(updatedSettings);
      expect(savedResult).toEqual(updatedSettings);
    });

    it("should set isSaving flag during save", async () => {
      vi.mocked(apiClient.getUserSettings).mockResolvedValue(mockSettings);
      vi.mocked(apiClient.putUserSettings).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockSettings), 100))
      );

      const { result } = renderHook(() => useModelSettings());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isSaving).toBe(false);

      act(() => {
        result.current.save({ multi_model_enabled: true });
      });

      expect(result.current.isSaving).toBe(true);

      await waitFor(() => {
        expect(result.current.isSaving).toBe(false);
      });
    });

    it("should handle save errors", async () => {
      vi.mocked(apiClient.getUserSettings).mockResolvedValue(mockSettings);
      
      const mockError = new Error("Save failed");
      vi.mocked(apiClient.putUserSettings).mockRejectedValue(mockError);

      const { result } = renderHook(() => useModelSettings());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.save({ multi_model_enabled: true });
        } catch (err) {
          expect(err).toEqual(mockError);
        }
      });

      expect(result.current.error).toEqual(mockError);
    });

    it("should throw error if save called before settings loaded", async () => {
      vi.mocked(apiClient.getUserSettings).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      const { result } = renderHook(() => useModelSettings());

      await act(async () => {
        try {
          await result.current.save({ multi_model_enabled: true });
          expect.fail("Should have thrown error");
        } catch (err) {
          expect(err).toBeInstanceOf(Error);
          expect((err as Error).message).toContain("Cannot save before settings are loaded");
        }
      });
    });

  });

  describe("Refetch", () => {
    it("should force refetch from server", async () => {
      const initialSettings = mockSettings;
      const updatedSettings = { ...mockSettings, multi_model_enabled: true };

      vi.mocked(apiClient.getUserSettings)
        .mockResolvedValueOnce(initialSettings)
        .mockResolvedValueOnce(updatedSettings);

      const { result } = renderHook(() => useModelSettings());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.settings?.multi_model_enabled).toBe(false);

      await act(async () => {
        await result.current.refetch();
      });

      expect(result.current.settings?.multi_model_enabled).toBe(true);
      expect(apiClient.getUserSettings).toHaveBeenCalledTimes(2);
    });
  });

  describe("Cleanup", () => {
    it("should not update state after unmount", async () => {
      vi.mocked(apiClient.getUserSettings).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockSettings), 100))
      );

      const { result, unmount } = renderHook(() => useModelSettings());

      expect(result.current.isLoading).toBe(true);

      unmount();

      // Wait for the async operation to complete
      await new Promise((resolve) => setTimeout(resolve, 150));

      // No errors should be thrown from setState after unmount
    });
  });
});
