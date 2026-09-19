"use strict";

// Derive examples from the deployed origin so the same site works on another VM.
const endpoint = `${window.location.origin}/mcp`;
document.getElementById("endpoint").textContent = endpoint;
document.getElementById("claude-command").textContent =
  `claude mcp add --scope user --transport http \\\n  tt-knowledge ${endpoint} \\\n  --header "Authorization: Bearer <your-token>"`;

if (navigator.clipboard && window.isSecureContext) {
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.hidden = false;
    const label = button.textContent;
    let resetLabel;
    button.addEventListener("click", async () => {
      const text = document
        .getElementById(button.dataset.copy)
        .textContent.trim();
      const status = document.getElementById("copy-status");
      try {
        await navigator.clipboard.writeText(text);
        clearTimeout(resetLabel);
        button.textContent = "Copied ✓";
        status.textContent = "Copied to clipboard.";
        resetLabel = setTimeout(() => {
          button.textContent = label;
        }, 2000);
      } catch {
        status.textContent =
          "Copy was unavailable. Select the text and copy it manually.";
      }
    });
  });
}

async function checkHealth() {
  const status = document.getElementById("service-status");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  status.textContent = "Checking service…";
  try {
    const response = await fetch("/healthz", {
      signal: controller.signal,
      cache: "no-store",
      credentials: "omit",
    });
    if (!response.ok || (await response.text()).trim() !== "ok")
      throw new Error("Unhealthy");
    status.textContent = "Service reachable";
    document.getElementById("status-dot").classList.add("online");
  } catch {
    status.textContent = "Service check unavailable";
  } finally {
    clearTimeout(timeout);
  }
}
checkHealth();
