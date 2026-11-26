# hello-world — app-server on ameba-ai-sdk

The smallest realistic shape of an app on an Ameba site:

```
browser / phone  ──HTTP──▶  this app-server  ──ameba-ai-sdk──▶  the site's AI
```

Your app never talks to the models directly — it holds one `AmebaAI` client
(built from your API key) and exposes its own small API.

A step-by-step walkthrough of this example is in the Console's docs: open
**Docs › Examples** and pick the `Ameba-Ran/hello-world` card.

## 0. Get the SDK wheel

`ameba-ai-sdk` is not on PyPI. In the Console, open **Docs** from the user
menu, download the wheel from the **Downloads** page and drop it into this
repo's [`wheels/`](wheels/) folder. `pyproject.toml` installs the SDK from
`wheels/ameba_ai_sdk-0.4.3-py3-none-any.whl`; if you download a newer
version, change the filename there to match.

## 1. Get a key, the Base URL and a model

In the Console, open **API & Keys** from the user menu: the **AI API** page
has everything. Pick the site at the top, then the **AI SDK** tab under
**Examples** and a model, and copy the three values it shows. Your personal
key works; for an app you deploy, click **New key** and give it a key of its
own (a new key starts working within about a minute).

## 2. Point the app at the site

Copy `.env.example` to `.env` (`run.py` loads it) and fill in the three
values:

```
AMEBA_BASE_URL=http://<Console address>/heimdall/<site slug>/v1
AMEBA_API_KEY=<your key>
AMEBA_LLM_MODEL=<model>
```

`GET <Base URL>/models` lists the models your key can use on that site.

## 3. Run

```bash
uv run python run.py            # http://localhost:8000
```

Open **http://localhost:8000** for a live demo page, or hit the API:

```bash
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
     -d '{"prompt":"Hello, who are you?"}'
# {"reply":"..."}

curl -X POST localhost:8000/transcribe -F file=@audio.wav -F language=zh
curl -X POST localhost:8000/transcribe -F file=@taigi.wav -F engine=taigi
curl -X POST localhost:8000/speak -H 'Content-Type: application/json' \
     -d '{"prompt":"你好"}' --output out.wav
curl -X POST localhost:8000/embed -H 'Content-Type: application/json' \
     -d '{"texts":["血壓","頭痛"]}'
curl localhost:8000/models

# RAG demo:建知識庫 → 同義改寫問題(hybrid 抓得到、bm25 抓不到)
curl -X POST localhost:8000/kb/setup -H 'Content-Type: application/json' \
     -d '{"name":"demo","text":"外籍勞工的居留證(ARC)遺失時,應向移民署申請補發。"}'
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
     -d '{"question":"我的證件不見了要找誰","kb_id":"<上一步的 kb_id>","mode":"hybrid"}'

# same KB, no LLM call — just the raw hits (ai.kb.retrieve)
curl -X POST localhost:8000/kb/retrieve -H 'Content-Type: application/json' \
     -d '{"query":"我的證件不見了要找誰","kb_id":"<上一步的 kb_id>","top_k":3}'

# multi-format upload: real file bytes instead of inline JSON text.
# No binary fixture ships in this repo — point -F file=@... at any
# pdf/docx/pptx/xlsx/csv/json/xml/txt/md you have lying around.
curl -X POST localhost:8000/kb/upload \
     -F kb_id=<kb id from /kb/setup or ai.kb.create()> \
     -F file=@handbook.pdf
# {"doc_id":"...","name":"handbook.pdf","chunk_count":42,"embedded":true,"status":"indexed"}
```

### Multi-format uploads and `parent_text`

`/kb/setup` only takes inline text (JSON `{"text": "..."}`) — fine for a
one-liner demo KB, but real documents are files. `/kb/upload` (multipart)
shows the actual SDK call for that: `ai.kb.upload(kb_id, file_bytes,
filename=...)` takes raw `bytes` regardless of format — txt/md, or
pdf/docx/pptx/xlsx/csv/json/xml (<= 20 MB), detected server-side by content
(magic bytes), not by trusting the filename extension:

```python
# main.py — /kb/upload (multipart: kb_id, file)
payload = await file.read()                       # raw bytes, any format
doc = ai.kb.upload(kb_id, payload, filename=file.filename)
# doc.chunk_count / doc.embedded / doc.status
```

Binary formats go through a layout-aware parent/child chunking pipeline
server-side (tables stay atomic instead of being shredded row-by-row). The
payoff shows up on the *retrieval* side: `/kb/retrieve`'s response includes
each hit's `parent_text` — the full section/table the matched `content`
chunk belongs to, broader context than the short chunk that actually
matched:

```python
result = ai.kb.retrieve("退休金試算公式", dataset_ids=[kb_id], top_k=3)
for ref in result.references:
    print(ref.content)          # the matched chunk (short, may read ambiguous alone)
    if ref.parent_text:         # None for plain txt/md — no structural parent
        print(ref.parent_text)  # the surrounding section/table for full context
```

If `/kb/upload`'s response comes back `"embedded": false`, that means the
embedder was unavailable *at upload time* — the document still indexed
lexically (BM25-searchable), it is **not** "still indexing" (indexing is
synchronous and already finished by the time the call returns). Poll
`ai.kb.document(kb_id, doc_id)` for `.status` (`"indexed"` /
`"lexical_only"` / `"empty"`), and call `ai.kb.reindex(kb_id)` once the
embedder is back to backfill the missing vectors.

## Endpoints

| Method | Path | SDK call |
|---|---|---|
| GET  | `/` | demo HTML page |
| GET  | `/healthz` | — |
| GET  | `/services` | `ai.available()` |
| GET  | `/models` | `ai.llm.models()` |
| POST | `/chat` | `ai.llm.chat` |
| POST | `/transcribe` | `ai.asr.transcribe` (engine=whisper/taigi) |
| POST | `/speak` | `ai.tts.speak` → audio/wav |
| POST | `/embed` | `ai.embeddings.embed` |
| POST | `/kb/setup` | `ai.kb.create` + `ai.kb.upload`(建 KB + 索引文字) |
| POST | `/kb/upload` | `ai.kb.upload`(真實檔案 bytes;pdf/docx/… 皆可) |
| POST | `/ask` | `ai.llm.chat(use_rag=True, retrieval={mode})` → 回答 + 引用 |
| POST | `/kb/retrieve` | `ai.kb.retrieve()`(不經 LLM,直接拿 references,含 `parent_text`) |

The full SDK reference is in the Console's docs (**Docs › AI SDK**).

## Container

The image installs the SDK from this repo's `wheels/` folder, so the wheel
must be there before you build. The site's AI cluster is arm64:

```bash
docker buildx build --platform linux/arm64 -t ameba-hello-world:v1 --load .
docker run --rm -p 8000:8000 --env-file .env ameba-hello-world:v1
```

`.dockerignore` keeps `.env` out of the image: the three `AMEBA_*` values are
declared empty in the image and filled in where it runs. To run the app on a
site, publish the image as an app card in **AI Apps** and deploy it from the
Console; see **Docs › AI Apps** for the image requirements.

## 4. showcase.py — run every SDK feature at once

`main.py` is the "third-party app-server" shape; `showcase.py` is a standalone
script that **exercises every feature of the SDK and prints each output**, to
confirm end-to-end operation:

    AMEBA_BASE_URL=http://<Console address>/heimdall/<site slug>/v1 \
    AMEBA_API_KEY=<your key> \
    AMEBA_LLM_MODEL=<model> \
    uv run python showcase.py

Each feature is isolated (try/except → a ✓/✗ line each, one failure never stops
the rest). It walks: catalog (`services`/`available`), `models`, LLM
(`complete`/`chat`/`chat_json`/`chat(stream=True)`),
**multi-turn `chat_session`** (turn 2 recalls a name set in turn 1 — the site
holds the history), embeddings, the full KB lifecycle
(`create→upload→documents→retrieve→reindex→delete`) + RAG-grounded `chat`,
a TTS→ASR round-trip, and a compose-it-yourself speech translation
(ASR → chat → TTS). What runs depends on the
services the site has turned on; a missing one shows as a ✗ line.

Speech recognition may mishear the synthetic TTS audio of the round-trip;
real speech transcribes fine.
