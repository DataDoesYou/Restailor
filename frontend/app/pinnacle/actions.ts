"use server";

export async function echoForm(data: FormData) {
  const out: Record<string, string> = {};
  data.forEach((v, k) => {
    if (typeof v === "string") out[k] = v;
  });
  return { ok: true, submitted: out, ts: new Date().toISOString() };
}

export async function submitEcho(formData: FormData) {
  const res = await echoForm(formData);
  const json = JSON.stringify(res);
  // Encode compactly and safely for URL
  const b64 = Buffer.from(json, "utf8").toString("base64url");
  const params = new URLSearchParams();
  params.set("echo", b64);
  // preserve labels toggle if present in Referer-like hidden field if provided
  const labels = formData.get("labels")?.toString();
  if (labels === "1") params.set("labels", "1");
  return { redirect: `/pinnacle?${params.toString()}` } as any;
}
