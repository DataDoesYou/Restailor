/**
 * ModelSettings Component Tests
 * 
 * Basic tests to verify component renders correctly with different states.
 * Full interaction testing is done via the adapter and hook tests.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ModelSettings from "../components/ModelSettings";
import type { ModelSettings as ModelSettingsType } from "../lib/apiClient";

// Mock the useModelSettings hook
vi.mock("../hooks/useModelSettings");

const mockUseModelSettings = vi.mocked(
  (await import("../hooks/useModelSettings")).useModelSettings
);

const createMockSettings = (overrides?: Partial<ModelSettingsType>): ModelSettingsType => ({
  multi_model_enabled: false,
  fit_models: [],
  tailor_models: [],
  judge_models: [],
  last_single_fit: null,
  last_single_tailor: null,
  last_single_judge: null,
  updated_at: "2025-10-14T12:00:00Z",
  version: 1,
  ...overrides,
});

describe("ModelSettings Component", () => {
  const mockSave = vi.fn();
  const mockRefetch = vi.fn();

  it("should show loading state", () => {
    mockUseModelSettings.mockReturnValue({
      settings: undefined,
      isLoading: true,
      isSaving: false,
      error: null,
      save: mockSave,
      refetch: mockRefetch,
    });

    render(<ModelSettings />);
    expect(screen.getByText("Loading model settings...")).toBeDefined();
  });

  it("should show error state", () => {
    mockUseModelSettings.mockReturnValue({
      settings: undefined,
      isLoading: false,
      isSaving: false,
      error: "Network error" as any, // Type assertion for test
      save: mockSave,
      refetch: mockRefetch,
    });

    render(<ModelSettings />);
    expect(screen.getByText(/Error:/)).toBeDefined();
    expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
  });

  it("should render in single-model mode", () => {
    mockUseModelSettings.mockReturnValue({
      settings: createMockSettings({ multi_model_enabled: false }),
      isLoading: false,
      isSaving: false,
      error: null,
      save: mockSave,
      refetch: mockRefetch,
    });

    render(<ModelSettings />);
    
    // Should have radio buttons
    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBeGreaterThan(0);
    
    // Should have all three roles
    expect(screen.getByText("Fit Analysis")).toBeDefined();
    expect(screen.getByText("Resume Tailoring")).toBeDefined();
    expect(screen.getByText("Quality Scoring")).toBeDefined();
  });

  it("should render in multi-model mode", () => {
    mockUseModelSettings.mockReturnValue({
      settings: createMockSettings({ 
        multi_model_enabled: true,
        fit_models: ["gpt-5", "claude-4.1-opus"],
      }),
      isLoading: false,
      isSaving: false,
      error: null,
      save: mockSave,
      refetch: mockRefetch,
    });

    render(<ModelSettings />);
    
    // Should have checkboxes
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThan(1);
    
    // Should have Select All and Clear buttons
    expect(screen.getAllByRole("button", { name: /select all/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /clear/i }).length).toBeGreaterThan(0);
    
    // Should show selection count
    expect(screen.getByText(/2 \/ 4/)).toBeDefined();
  });

  it("should show saving state", () => {
    mockUseModelSettings.mockReturnValue({
      settings: createMockSettings(),
      isLoading: false,
      isSaving: true,
      error: null,
      save: mockSave,
      refetch: mockRefetch,
    });

    render(<ModelSettings />);
    expect(screen.getByText("Saving changes...")).toBeDefined();
  });

  it("should show warning when no models selected", () => {
    mockUseModelSettings.mockReturnValue({
      settings: createMockSettings({
        multi_model_enabled: true,
        fit_models: [],
        tailor_models: [],
        judge_models: [],
      }),
      isLoading: false,
      isSaving: false,
      error: null,
      save: mockSave,
      refetch: mockRefetch,
    });

    render(<ModelSettings />);
    const warnings = screen.getAllByText(/no models selected/i);
    expect(warnings.length).toBeGreaterThan(0); // At least one warning
  });
});
