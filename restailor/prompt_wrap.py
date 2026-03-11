import secrets
from pathlib import Path
from typing import Literal

ROLE = Literal["tailor","fit","judge"]
PROMPT_PATHS = {
  "tailor": Path("prompts/tailor.md"),
  "fit":    Path("prompts/fit.md"),
  "judge":  Path("prompts/judge.md"),
}

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def make_end_marker(job_id: str) -> str:
    return f"<<END::{job_id}:{secrets.token_hex(8)}>>"  # ASCII and JSON-safe

def build_user_block(resume_text_normalized: str, jd_text_normalized: str) -> str:
    return (f"<RESUME>\n{resume_text_normalized}\n</RESUME>\n\n"
            f"<JD>\n{jd_text_normalized}\n</JD>")

def build_prompts(cfg: dict, role: ROLE, resume_text_norm: str, jd_text_norm: str, job_id: str):
    end_marker = make_end_marker(job_id)
    max_quotes = str(cfg.get("abuse", {}).get("max_quote_chars", 1000))
    sys = _read(PROMPT_PATHS[role]).replace("{{MAX_QUOTE_CHARS}}", max_quotes) \
                                   .replace("{{END_MARKER}}", end_marker)
    user = build_user_block(resume_text_norm, jd_text_norm)
    return sys, user, end_marker
