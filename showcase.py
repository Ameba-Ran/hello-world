"""showcase.py — exercise EVERY ameba-sdk feature end-to-end and print the output.

A single script that walks the whole SDK surface so you can confirm each feature
works and see exactly what it returns. Every feature is isolated in try/except,
so one failure never stops the rest — you get a ✓/✗ line per feature.

Run it (point at any gateway with a key you issued):

    AMEBA_BASE_URL=http://127.0.0.1:8080 \\
    AMEBA_API_KEY=bsa_xxxxxxxx \\
    uv run python showcase.py

Optional: AMEBA_LLM_MODEL (default google/gemma-4-E4B-it).
"""
from __future__ import annotations

import os
import traceback

from ameba_sdk import AmebaAI, AmebaError

MODEL = os.environ.get("AMEBA_LLM_MODEL", "google/gemma-4-E4B-it")


def section(title: str) -> None:
    print(f"\n{'━' * 66}\n▌ {title}\n{'━' * 66}")


def show(label: str, fn):
    """Run fn(), print '✓ label → <result>' or '✗ label → <error>'. Returns the
    result (or None on failure) so later steps can chain off it."""
    try:
        out = fn()
        preview = repr(out)
        if len(preview) > 240:
            preview = preview[:240] + " …"
        print(f"  ✓ {label}\n      → {preview}")
        return out
    except Exception as exc:  # noqa: BLE001 — a demo: surface, don't crash
        msg = f"{type(exc).__name__}: {exc}"
        print(f"  ✗ {label}\n      → {msg}")
        if os.environ.get("SHOWCASE_TRACE"):
            traceback.print_exc()
        return None


def main() -> None:
    ai = AmebaAI.from_env()
    print(f"connected: base_url={ai.config.base_url}  model={MODEL}")

    # ── Catalog: what this key can see ────────────────────────────────────
    section("Catalog — services this key can use")
    show("ai.services()   full cluster catalog",
         lambda: [f"{s.name}[{s.kind}]" for s in ai.services()])
    show("ai.available()  usable-now services",
         lambda: [f"{s.name}[{s.kind}]" for s in ai.available()])

    # ── Models ────────────────────────────────────────────────────────────
    section("Models")
    show("ai.llm.models()", lambda: ai.llm.models())
    show("ai.embeddings.models()", lambda: ai.embeddings.models())

    # ── LLM: every generation flavour ─────────────────────────────────────
    section("LLM — generate")
    show("llm.complete(prompt) → str",
         lambda: ai.llm.complete("用一句話介紹台灣", model=MODEL, max_tokens=64))
    show("llm.chat(prompt) → Reply",
         lambda: str(ai.llm.chat("把這句翻成英文：今天天氣很好", model=MODEL)))
    show("llm.chat_json(messages, schema) → dict",
         lambda: ai.llm.chat_json(
             "列出台灣三個城市",
             schema={"type": "object",
                     "properties": {"cities": {"type": "array",
                                               "items": {"type": "string"}}}},
             model=MODEL))

    def stream_demo():
        parts = list(ai.llm.chat("寫一句關於海的短詩", model=MODEL, stream=True))
        return "".join(parts)
    show("llm.chat(stream=True) → iterator of deltas", stream_demo)

    # ── Multi-turn: the native conversation store (client mints the id) ────
    section("Multi-turn — ChatSession (gateway server-side conversation store)")

    def multi_turn():
        chat = ai.pipelines.chat_session(model=MODEL)
        r1 = chat.send("我叫小明，請記住我的名字，只要回覆『好』。")
        # turn 2 sends ONLY this message — the gateway prepends turn 1
        r2 = chat.send("我剛剛說我叫什麼名字？")
        return {"conversation_id": chat.conversation_id,
                "turn1": str(r1)[:20], "turn2": str(r2)[:20],
                "recalled_名字": "小明" in str(r2)}
    show("chat_session: turn2 recalls the name set in turn1", multi_turn)

    # ── Embeddings ────────────────────────────────────────────────────────
    section("Embeddings")
    print("  note: the direct /v1/embeddings endpoint needs the gateway's embed-upstream")
    print("        key configured (GATEWAY_RAG_EMBED_*); RAG uses embeddings internally either way.")
    vecs = show("embeddings.embed([...]) → list[list[float]]",
                lambda: ai.embeddings.embed(["語音辨識", "語音合成"], model="bge-m3"))
    if vecs:
        print(f"      (2 inputs → {len(vecs)} vectors, dim={len(vecs[0])})")
    show("embeddings.embed_one(text) → list[float]",
         lambda: f"dim={len(ai.embeddings.embed_one('單一句子', model='bge-m3'))}")

    # ── Knowledge base: full lifecycle ────────────────────────────────────
    section("Knowledge base — create → upload → retrieve → status → delete")
    kb = show("kb.create(name)",
              lambda: ai.kb.create("showcase-醫療術語", description="中越對照詞庫"))
    kb_id = getattr(kb, "id", None)
    if kb_id:
        doc = show("kb.upload(kb_id, file)",
                   lambda: ai.kb.upload(
                       kb_id,
                       "高血壓 = cao huyết áp\n糖尿病 = bệnh tiểu đường\n".encode(),
                       filename="glossary.txt",
                   ))
        show("kb.list()", lambda: [k.name for k in ai.kb.list()])
        show("kb.get(kb_id)", lambda: ai.kb.get(kb_id).name)
        show("kb.documents(kb_id) → indexing status",
             lambda: [(d.name, d.status) for d in ai.kb.documents(kb_id)])
        doc_id = getattr(doc, "id", None)
        if doc_id:
            show("kb.document(kb_id, doc_id)",
                 lambda: ai.kb.document(kb_id, doc_id).status)
        show("kb.retrieve(query) → references (no LLM)",
             lambda: [(r.document_name, round(r.score, 3))
                      for r in ai.kb.retrieve("高血壓的越南文", dataset_ids=[kb_id]).references])
        show("llm.chat(use_rag=True) → RAG-grounded answer",
             lambda: str(ai.llm.chat("高血壓的越南文是什麼？", model=MODEL,
                                     use_rag=True, knowledge_bases=[kb_id]))[:60])
        show("kb.reindex(kb_id)", lambda: ai.kb.reindex(kb_id))
        show("kb.delete(kb_id)  (cleanup)", lambda: ai.kb.delete(kb_id) or "deleted")

    # ── TTS + ASR round-trip (no external audio file needed) ──────────────
    section("TTS + ASR — synthesize speech, then transcribe it back")
    show("tts.voices()", lambda: ai.tts.voices())
    audio = show("tts.speak(text) → audio bytes",
                 lambda: ai.tts.speak("今天天氣很好，適合出門散步。", response_format="wav"))
    if audio:
        print(f"      ({len(audio)} bytes of audio)")
        print("  note: Whisper transcribes REAL speech well; on synthetic TTS audio it")
        print("        tends to hallucinate — this round-trip only proves the bytes flow.")
        show("asr.transcribe(audio) → text  (round-trip)",
             lambda: ai.asr.transcribe(audio, filename="tts.wav", language="zh").text)
        section("Pipeline — speech_translate (ASR → translate → TTS in one call)")
        show("pipelines.speech_translate(audio, target)",
             lambda: {
                 "source_text": (st := ai.pipelines.speech_translate(
                     audio, target="en", model=MODEL, synthesize=False)).source_text,
                 "translated_text": st.translated_text,
             })

    # ── Account lifecycle (shown, NOT executed — they mutate credentials) ──
    section("Account lifecycle (code shown — not run, they change your key)")
    print("  • AmebaAI.register(base_url, customer_id=..., display_name=...,")
    print("        contact_email=..., purpose=...)  → self-issues a key, saves it")
    print("  • ai.rotate_key()                       → mints a replacement key")
    print("  • ai.rotate_user('end-user-id')         → switch end-user identity")

    ai.close()
    print(f"\n{'━' * 66}\ndone — every feature above ran against the live gateway.\n{'━' * 66}")


if __name__ == "__main__":
    try:
        main()
    except AmebaError as exc:
        print(f"fatal: {type(exc).__name__}: {exc}")
        raise
