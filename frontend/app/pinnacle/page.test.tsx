import { describe, it, expect, vi } from "vitest";
import Page from "./page";
import { render } from "@testing-library/react";

vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "--font-inter" }),
}));

describe("Pinnacle page", () => {
  it("renders sections and buttons", async () => {
    const ui = await Page({ searchParams: {} });
    // Render the server component output into a client testing container
    const { getByRole, getByLabelText } = render(ui as any);
    expect(getByRole("heading", { level: 2, name: "Hero" })).toBeTruthy();
    expect(getByRole("button", { name: /Primary Button|Primary CTA/i })).toBeTruthy();
    expect(getByLabelText("Inputs: Text")).toBeTruthy();
  });
});
