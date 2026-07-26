import { invoke } from "@tauri-apps/api/core";

const browserDefaultBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "/api";

export async function resolveBackendBaseUrl(): Promise<string> {
  try {
    const desktopBaseUrl = stripTrailingSlash(await invoke<string>("backend_base_url"));
    if (desktopBaseUrl) {
      return desktopBaseUrl;
    }
  } catch {
    // Browser development falls back to the Vite /api proxy.
  }
  return stripTrailingSlash(browserDefaultBaseUrl);
}

function stripTrailingSlash(value: string): string {
  return value.trim().replace(/\/+$/, "");
}
