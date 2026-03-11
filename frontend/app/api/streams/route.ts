import { NextRequest } from "next/server";

type Provider = "openai" | "anthropic" | "gemini" | "xai";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function meaningfulText(s: string): string | null {
  try {
    for (const ch of ["\u200B", "\u200C", "\u200D", "\u2060", "\uFEFF"]) {
      s = s.replace(new RegExp(ch, "g"), "");
    }
    const s2 = s.trim();
    return s2 ? s2 : null;
  } catch {
    return null;
  }
}

async function resolveKeyForProvider(p: Provider): Promise<{ key: string | null; envNames: string[] }> {
  // 1) Environment
  const fromEnv = (names: string[]): string | null => {
    for (const n of names) {
      const v = (process.env as any)[n];
      if (v && String(v).trim()) return String(v);
    }
    return null;
  };
  const envNames = p === "openai" ? ["OPENAI_API_KEY"]
    : p === "anthropic" ? ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY"]
    : p === "gemini" ? ["GEMINI_API_KEY"]
    : /* xai */ ["GROK_API_KEY", "XAI_API_KEY"]; 
  const vEnv = fromEnv(envNames);
  if (vEnv) return { key: vEnv, envNames };

  // 2) OS keyring via keytar (Windows Credential Manager, macOS Keychain, Secret Service)
  try {
    // Lazy import; if unavailable, skip silently
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const keytar = (await import("keytar").catch(() => null)) as any;
    if (keytar && (typeof keytar.getPassword === "function")) {
      const services = [
        "restailor",
        "restailor-app",
        "restailor",
        "ResumeTailor",
      ];
      for (const svc of services) {
        for (const name of envNames) {
          try {
            const val = await keytar.getPassword(svc, name);
            if (val && String(val).trim()) return { key: String(val), envNames };
          } catch {
            // continue
          }
          // Also try reversed tuple in case of platform-specific mapping
          try {
            const val2 = await keytar.getPassword(name, svc);
            if (val2 && String(val2).trim()) return { key: String(val2), envNames };
          } catch {
            // continue
          }
        }
        // Fallback: enumerate credentials for this service and match by account
        try {
          if (typeof keytar.findCredentials === "function") {
            const creds = await keytar.findCredentials(svc);
            if (Array.isArray(creds)) {
              for (const rec of creds) {
                const acc = String(rec?.account || "");
                if (envNames.includes(acc) && rec?.password) {
                  return { key: String(rec.password), envNames };
                }
              }
            }
          }
        } catch {
          // ignore
        }
      }
    }
  } catch {
    // ignore keytar errors and fall back to null
  }
  return { key: null, envNames };
}

export async function POST(req: NextRequest) {
  const { provider, model, system, prompt, timeout } = await req.json();
  const p = String(provider || "").toLowerCase() as Provider;
  const { key, envNames } = await resolveKeyForProvider(p);
  if (!key) {
    // Fallback: proxy to Python API which already knows how to read OS keyring.
    const apiBase = String(
      (typeof window === "undefined" ? process.env.INTERNAL_API_BASE_URL : undefined)
      || process.env.NEXT_PUBLIC_API_BASE_URL
      || "http://localhost:8000"
    ).replace(/\/$/, "");
    try {
      const upstream = await fetch(`${apiBase}/streams/test`, {
        method: "POST",
        // Forward auth cookies so FastAPI can auth you
        headers: {
          "content-type": "application/json",
          "cookie": req.headers.get("cookie") || "",
        },
        body: JSON.stringify({ provider: p, model, system, prompt, timeout }),
      });
      if (!upstream.ok || !upstream.body) {
        // Provide non-secret debug context
        const searched = {
          envTried: envNames,
          servicesTried: ["restailor","restailor-app","restailor","ResumeTailor"],
          upstreamStatus: upstream.status,
        };
        return new Response(
          JSON.stringify({ error: `Missing API key for provider '${p}'`, debug: searched }),
          { status: 400, headers: { "content-type": "application/json" } }
        );
      }
      // Pipe upstream NDJSON through to client
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "application/x-ndjson",
          "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
      });
    } catch {
      const searched = {
        envTried: envNames,
        servicesTried: ["restailor","restailor-app","restailor","ResumeTailor"],
        upstream: "connect_failed",
      };
      return new Response(
        JSON.stringify({ error: `Missing API key for provider '${p}'`, debug: searched }),
        { status: 400, headers: { "content-type": "application/json" } }
      );
    }
  }

  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), Math.max(5, Math.min(600, Number(timeout) || 120)) * 1000);

  // Stream back NDJSON lines
  const stream = new ReadableStream<Uint8Array>({
    async start(controllerOut) {
      const encoder = new TextEncoder();
      const write = (obj: any) => controllerOut.enqueue(encoder.encode(JSON.stringify(obj) + "\n"));
      const close = () => { try { controllerOut.close(); } catch {} };
      const fail = (e: any) => { try { controllerOut.error(e); } catch {} };

      const done = (elapsed_s?: number, request_id?: string) => write({ type: "done", elapsed_s, request_id });
      const event = (evt: string) => write({ type: "event", evt });
      const delta = (text: string) => write({ type: "delta", text });
      const error = (message: string) => write({ type: "error", message });

      const startedAt = Date.now();

      try {
        if (p === "openai") {
          const base = "https://api.openai.com/v1";
          // GPT-5 uses Responses API streaming
          if (String(model || "").toLowerCase().startsWith("gpt-5")) {
            // Use Server-Sent Events style stream
            const resp = await fetch(`${base}/responses`, {
              method: "POST",
              headers: {
                "Authorization": `Bearer ${key}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                model,
                instructions: system || undefined,
                input: prompt,
                reasoning: { effort: "high" },
                stream: true,
              }),
              signal: controller.signal,
            });
            if (!resp.ok || !resp.body) {
              error(`OpenAI Responses error HTTP ${resp.status}`);
              close();
              return;
            }
            // Responses API returns SSE text/event-stream
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buf = "";
            const process = () => {
              const lines = buf.split("\n");
              buf = lines.pop() || "";
              for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                if (trimmed.startsWith("data:")) {
                  const jsonStr = trimmed.slice(5).trim();
                  if (jsonStr === "[DONE]") continue;
                  try {
                    const obj = JSON.parse(jsonStr);
                    const t = obj?.type;
                    event(String(t || "evt"));
                    // Common delta shapes
                    const piece = obj?.delta || obj?.text || obj?.output_text;
                    if (typeof piece === "string") {
                      const mt = meaningfulText(piece);
                      if (mt) delta(mt);
                    }
                  } catch {}
                }
              }
            };
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buf += dec.decode(value, { stream: true });
              process();
            }
            buf += dec.decode();
            process();
          } else {
            // Chat Completions streaming
            const resp = await fetch(`${base}/chat/completions`, {
              method: "POST",
              headers: {
                "Authorization": `Bearer ${key}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                model,
                messages: [
                  { role: "system", content: String(system || "") },
                  { role: "user", content: String(prompt || "") },
                ],
                temperature: 0.6,
                stream: true,
              }),
              signal: controller.signal,
            });
            if (!resp.ok || !resp.body) {
              error(`OpenAI Chat error HTTP ${resp.status}`);
              close();
              return;
            }
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buf = "";
            const process = () => {
              const lines = buf.split("\n");
              buf = lines.pop() || "";
              for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                if (trimmed.startsWith("data:")) {
                  const jsonStr = trimmed.slice(5).trim();
                  if (jsonStr === "[DONE]") continue;
                  try {
                    const obj = JSON.parse(jsonStr);
                    event("chunk");
                    const choice = obj?.choices?.[0];
                    const text = choice?.delta?.content;
                    if (typeof text === "string") {
                      const mt = meaningfulText(text);
                      if (mt) delta(mt);
                    }
                  } catch {}
                }
              }
            };
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buf += dec.decode(value, { stream: true });
              process();
            }
            buf += dec.decode();
            process();
          }
        } else if (p === "anthropic") {
          const resp = await fetch("https://api.anthropic.com/v1/messages", {
            method: "POST",
            headers: {
              "x-api-key": key,
              "anthropic-version": "2023-06-01",
              "content-type": "application/json",
            },
            body: JSON.stringify({
              model,
              system,
              messages: [
                { role: "user", content: [{ type: "text", text: String(prompt ?? "") }] },
              ],
              stream: true,
              max_tokens: 4096,
              temperature: 0.6,
            }),
            signal: controller.signal,
          });
          if (!resp.ok || !resp.body) {
            try {
              const txt = await resp.text();
              error(`Anthropic error HTTP ${resp.status}${txt ? ": " + txt : ""}`);
            } catch {
              error(`Anthropic error HTTP ${resp.status}`);
            }
            close();
            return;
          }
          const reader = resp.body.getReader();
          const dec = new TextDecoder();
          let buf = "";
          const process = () => {
            const lines = buf.split("\n");
            buf = lines.pop() || "";
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) continue;
              if (trimmed.startsWith("data:")) {
                const jsonStr = trimmed.slice(5).trim();
                if (jsonStr === "[DONE]") continue;
                try {
                  const obj = JSON.parse(jsonStr);
                  event(String(obj?.type || "event"));
                  if (obj?.type === "content_block_delta") {
                    const text = obj?.delta?.text;
                    if (typeof text === "string") {
                      const mt = meaningfulText(text);
                      if (mt) delta(mt);
                    }
                  }
                } catch {}
              }
            }
          };
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            process();
          }
          buf += dec.decode();
          process();
  } else if (p === "gemini") {
          // Google GenAI streaming via REST beta (text/event-stream). As fallback, use non-SSE JSON with candidates.
          const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:streamGenerateContent?key=${encodeURIComponent(key)}`;
          const cfg: any = {
            systemInstruction: system ? { role: "system", parts: [{ text: String(system) }] } : undefined,
            contents: [{ role: "user", parts: [{ text: String(prompt || "") }] }],
            generationConfig: { temperature: 0.6 },
          };
          const resp = await fetch(url, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(cfg),
            signal: controller.signal,
          });
          if (!resp.ok || !resp.body) {
            try {
              const txt = await resp.text();
              error(`Gemini error HTTP ${resp.status}${txt ? ": " + txt : ""}`);
            } catch {
              error(`Gemini error HTTP ${resp.status}`);
            }
            close();
            return;
          }
          const reader = resp.body.getReader();
          const dec = new TextDecoder();
          let buf = "";
          const process = () => {
            const lines = buf.split("\n");
            buf = lines.pop() || "";
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) continue;
              // Some SDKs send plain JSON lines; handle both
              let obj: any = null;
              if (trimmed.startsWith("data:")) {
                try { obj = JSON.parse(trimmed.slice(5).trim()); } catch { obj = null; }
              } else {
                try { obj = JSON.parse(trimmed); } catch { obj = null; }
              }
              if (!obj) continue;
              event("delta");
              const texts: string[] = [];
              // Prefer top-level text
              if (typeof obj.text === "string") texts.push(obj.text);
              // candidates -> content.parts[].text
              try {
                const cands = obj.candidates || [];
                for (const c of cands) {
                  const content = c.content || {};
                  const parts = content.parts || [];
                  for (const part of parts) {
                    const tx = typeof part.text === "string" ? part.text : null;
                    if (tx) texts.push(tx);
                  }
                }
              } catch {}
              for (const piece of texts) {
                const mt = meaningfulText(piece);
                if (mt) delta(mt);
              }
            }
          };
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            process();
          }
          buf += dec.decode();
          process();
  } else if (p === "xai") {
          // xAI is OpenAI-compatible API at https://api.x.ai/v1
          const resp = await fetch("https://api.x.ai/v1/chat/completions", {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${key}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              model,
              messages: [
                { role: "system", content: String(system || "") },
                { role: "user", content: String(prompt || "") },
              ],
              temperature: 0.6,
              stream: true,
            }),
            signal: controller.signal,
          });
          if (!resp.ok || !resp.body) {
            try {
              const txt = await resp.text();
              error(`xAI error HTTP ${resp.status}${txt ? ": " + txt : ""}`);
            } catch {
              error(`xAI error HTTP ${resp.status}`);
            }
            close();
            return;
          }
          const reader = resp.body.getReader();
          const dec = new TextDecoder();
          let buf = "";
          const process = () => {
            const lines = buf.split("\n");
            buf = lines.pop() || "";
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) continue;
              if (trimmed.startsWith("data:")) {
                const jsonStr = trimmed.slice(5).trim();
                if (jsonStr === "[DONE]") continue;
                try {
                  const obj = JSON.parse(jsonStr);
                  event("chunk");
                  const choice = obj?.choices?.[0];
                  const text = choice?.delta?.content;
                  if (typeof text === "string") {
                    const mt = meaningfulText(text);
                    if (mt) delta(mt);
                  }
                } catch {}
              }
            }
          };
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            process();
          }
          buf += dec.decode();
          process();
        } else {
          error(`Unknown provider: ${p}`);
        }
        const elapsed = (Date.now() - startedAt) / 1000;
        done(Number(elapsed.toFixed(2)));
        close();
      } catch (e: any) {
        if (e?.name === "AbortError") {
          error("Client timeout/abort");
          close();
          return;
        }
        error(String(e?.message || e));
        fail(e);
      } finally {
        clearTimeout(t);
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson",
      "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
    },
  });
}
