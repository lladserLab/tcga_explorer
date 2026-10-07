/* No remote validator or persistence of credentials/patient input. */
(async () => {
  const root = document.getElementById("api-reference");
  const status = document.getElementById("docs-status");
  const complete = () => { status.hidden = true; };
  try {
    const response = await fetch(root.dataset.schema, { credentials: "same-origin" });
    if (!response.ok) throw new Error("Schema unavailable");
    const spec = await response.json();
    if (root.dataset.viewer === "swagger") {
      SwaggerUIBundle({
        spec, dom_id: "#api-reference", deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis], layout: "BaseLayout",
        validatorUrl: null, persistAuthorization: false, onComplete: complete,
      });
    } else {
      Redoc.init(spec, { disableGoogleFont: true, hideDownloadButton: true,
        theme: { typography: { fontFamily: "system-ui, sans-serif",
          headings: { fontFamily: "system-ui, sans-serif" } } },
      }, root, (error) => {
        if (error) status.textContent = "The reference could not load. Open the integration guide above or reload this page.";
        else complete();
      });
    }
  } catch {
    status.textContent = "The reference could not load. Open the integration guide above or reload this page.";
  }
})();
