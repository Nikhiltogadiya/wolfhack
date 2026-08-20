# Engineering log

Append-only. Per entry: what was done, why, what worked, and **especially what failed and why**.

---

## 2026-08-20 — M0: toolchain spine

**Done.** uv env (py3.12.9), repo skeleton, raw source preserved to `doc/source/`, LangChain
docs+reference MCP servers added, NIM verified end to end.

**Verified live, not from memory.** `GET /v1/models` returns 103 models. Nemotron family
confirmed present: `nvidia/nemotron-3-nano-30b-a3b`, `nvidia/nemotron-3-super-120b-a12b`,
`nvidia/nemotron-3-ultra-550b-a55b`, `nvidia/nemotron-3.5-lightning-30b-a3b`,
`nvidia/llama-3.3-nemotron-super-49b-v1.5`. Embeddings: `nvidia/nv-embedqa-e5-v5`,
`nvidia/nemotron-3-embed-1b`. Vision: `nvidia/nemotron-nano-12b-v2-vl`.

**Failed / gotcha 1 — `/v1/models` is unauthenticated.** It returned HTTP 200 with no key set,
which briefly looked like proof the key worked. It is not. Only a real `/v1/chat/completions`
call proves credentials.

**Failed / gotcha 2 — `source ~/.bashrc` is a no-op in the tool shell.** Non-interactive bash
returns early from the stock Ubuntu `.bashrc` guard, so the key never landed in the env.
Fix used: `eval "$(grep -E '^\s*export\s+NVIDIA_API_KEY=' ~/.bashrc)"` — evals only that one
line and never prints the value.

**Worked.** `ChatOpenAI(model=..., base_url="https://integrate.api.nvidia.com/v1")` +
`.with_structured_output(PydanticModel)` returns validated Pydantic against NIM on the first
try. No JSON-mode fallback needed so far.

**Real finding on the very first extraction.** Given `"Built CI with Jenkins since 2019"`, the
model returned `years=2019.0` — it conflated a calendar year with a duration. It also emitted
`"Led platform team"` as a *skill*. Consequences, both now hard rules in `CLAUDE.md`:
1. **All date/duration arithmetic is deterministic Python**, never the LLM. The LLM may report
   a verbatim span; the rules engine computes the number.
2. Claim extraction needs a typed distinction between `years_claimed` and `since_year`, plus a
   skill-vs-responsibility filter. A raw `years` float invites exactly this error.

This is the concrete justification for the "rules engine decides, LLM extracts" principle —
it failed on call number one.
