import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { createEvidenceApi } from "./api";
import { resolveBackendBaseUrl } from "./runtime";
import "./styles.css";

async function renderApp() {
  const baseUrl = await resolveBackendBaseUrl();
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App client={createEvidenceApi({ baseUrl })} />
    </StrictMode>,
  );
}

void renderApp();
