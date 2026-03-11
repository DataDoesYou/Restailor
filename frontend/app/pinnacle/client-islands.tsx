"use client";
import { echoForm } from "./actions";
import React from "react";

export function OpenDialogButton({ idAttr, label }: { idAttr: string; label: string }) {
  return (
    <button
      id={idAttr}
      data-testid={idAttr}
      data-label={`Overlays: ${label}`}
      aria-label={`Overlays: ${label}`}
  className="p-btn p-btn--secondary"
      onClick={() => {
        const dlg = document.querySelector<HTMLDialogElement>("#ovl-dialog");
        dlg?.showModal();
      }}
    >
      {label}
    </button>
  );
}

export function CloseDialogButton({ idAttr, label }: { idAttr: string; label: string }) {
  return (
    <button
      id={idAttr}
      data-testid={idAttr}
      data-label={`Overlays: ${label}`}
      aria-label={`Overlays: ${label}`}
  className="p-btn p-btn--secondary"
      onClick={() => {
        const dlg = document.querySelector<HTMLDialogElement>("#ovl-dialog");
        dlg?.close();
      }}
    >
      {label}
    </button>
  );
}

export function SubmitClient() {
  const [res, setRes] = React.useState<any>(null);
  return (
  <div className="grid gap-3">
      <button
        id="form-submit"
        data-testid="form-submit"
        data-label="Form: Submit"
        aria-label="Form: Submit"
  className="p-btn p-btn--primary"
        formAction={async (fd) => setRes(await echoForm(fd))}
      >
        Submit
      </button>
      {res && (
  <pre className="text-xs break-all whitespace-pre-wrap p-card p-3" aria-live="polite">{JSON.stringify(res, null, 2)}</pre>
      )}
    </div>
  );
}

export function CopyButton({ json }: { json: string }) {
  return (
    <button
      id="copy-ui-map"
      data-testid="copy-ui-map"
      data-label="Footer: Copy UI Map"
      aria-label="Footer: Copy UI Map"
  className="p-btn p-btn--secondary"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(json);
        } catch {
          const ta = document.createElement("textarea");
          ta.value = json;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
        }
      }}
    >
      Copy UI Map
    </button>
  );
}
