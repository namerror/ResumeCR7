import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

import { invoke } from "@tauri-apps/api/core";
import { resolveBackendBaseUrl } from "./runtime";

describe("desktop runtime backend URL resolution", () => {
  beforeEach(() => {
    vi.mocked(invoke).mockReset();
  });

  it("uses the browser API base URL when the Tauri command is unavailable", async () => {
    vi.mocked(invoke).mockRejectedValue(new Error("not running in Tauri"));

    await expect(resolveBackendBaseUrl()).resolves.toBe("/api");
    expect(invoke).toHaveBeenCalledWith("backend_base_url");
  });

  it("resolves the backend URL from the Tauri command", async () => {
    vi.mocked(invoke).mockResolvedValue("http://127.0.0.1:43123/");

    await expect(resolveBackendBaseUrl()).resolves.toBe("http://127.0.0.1:43123");
    expect(invoke).toHaveBeenCalledWith("backend_base_url");
  });

  it("falls back to the browser API base URL when the Tauri command returns blank", async () => {
    vi.mocked(invoke).mockResolvedValue(" ");

    await expect(resolveBackendBaseUrl()).resolves.toBe("/api");
  });
});
