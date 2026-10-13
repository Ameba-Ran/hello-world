# hello-world — app-server on ameba-ai-sdk

The smallest realistic shape of a third-party app on the Amebaran MEC:

```
browser / phone  ──HTTP──▶  this app-server  ──ameba-sdk──▶  gateway ──▶ cluster AI
```

Your app never talks to the models directly — it holds one `AmebaAI` client
(built from your API key) and exposes its own small API.

A step-by-step walkthrough of this example lives on the Amebaran doc-hub
(Docs → Examples → Hello world walkthrough).

## 0. Get the SDK wheel

`ameba-ai-sdk` is not on PyPI. Download the wheel from your Amebaran doc-hub
**Downloads** page and drop it into this repo's [`wheels/`](wheels/)
folder — `pyproject.toml` resolves the SDK from that exact path (bump the
filename there when you grab a newer wheel).

## 1. Get a key

Every key is a **porin customer**: the gateway meters each request against the
key's `customer_id`, so an app that holds its own key shows up as its own line
in Revenue Insight. Self-register one:

```python
from ameba_sdk import AmebaAI
AmebaAI.register("http://<Console address>/porin/<site slug>", "hello-world-app", "Hello World App")
```

…or `curl -X POST http://<Console address>/porin/<site slug>/v1/register -H 'Content-Type: application/json' \
     -d '{"customer_id":"hello-world-app","display_name":"Hello World App"}'`.
The key comes back **once** — store it. (`<Console address>` is the address
you open the Console with; `<site slug>` is the site's code — `k8s-ran` in the
lab. A bare `/porin` without the site answers `404`.)

## 2. Point the app at the gateway

Copy `.env.example` to `.env` (auto-loaded). One URL is enough — porin serves
llm / asr / tts / embeddings, and `AMEBA_BASE_URL` back-fills every per-kind
URL that is left unset:

```
AMEBA_BASE_URL=http://<Console address>/porin/<site slug>     # the site's porin, from a dev box
AMEBA_API_KEY=bsa_...
AMEBA_LLM_MODEL=Qwen/Qwen2.5-Omni-7B           # example — verify against /v1/models first
```

**Pick the model first**: the lineup changes over time, so list what your
cluster actually serves (entries with `"type": "llm"`) and fill that in:

```bash
curl http://<Console address>/porin/<site slug>/v1/models -H "Authorization: Bearer <your bsa_ key>"
```

In-cluster (the Studio card, below) the gateway is
`http://porin-ai-gateway-svc.default.svc.cluster.local:8080` instead.

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

The full per-service SDK reference lives on the Amebaran doc-hub
(Docs → Python SDK).

## Container / Studio card

The app resolves the SDK from this repo's `wheels/` folder (the wheel must be
in the build context):

```bash
# from the repo root, on an arm64 host (the cluster is arm64)
docker build -t ameba-hello-world:v1 .
docker run --rm -p 8000:8000 \
  -e AMEBA_BASE_URL=http://<Console address>/porin/<site slug> \
  -e AMEBA_API_KEY=bsa_... \
  -e AMEBA_LLM_MODEL=Qwen/Qwen2.5-Omni-7B \
  ameba-hello-world:v1
```

To run it on the cluster, import the image into k3s and create a
`workload_templates` card with `section: "studio"` (it then appears on the
Console's **Ameba AI Studio** page):

```bash
docker save ameba-hello-world:v1 | sudo k3s ctr images import -
```

The card's env points at the in-cluster gateway
(`http://porin-ai-gateway-svc.default.svc.cluster.local:8080`) and carries the
app's own `bsa_` key, which is what makes its LLM usage bill to
`customer_id=hello-world-app`. `service_port` is 8000; the deployed service is
reachable on the node's NodePort as `hello-world-svc`.

## 4. showcase.py — run every SDK feature at once

`main.py` is the "third-party app-server" shape; `showcase.py` is a standalone
script that **exercises every feature of the SDK and prints each output**, to
confirm end-to-end operation:

    AMEBA_BASE_URL=http://<Console address>/porin/<site slug> \
    AMEBA_API_KEY=bsa_xxxxxxxx \
    uv run python showcase.py

Each feature is isolated (try/except → a ✓/✗ line each, one failure never stops
the rest). It walks: catalog (`services`/`available`), `models`, LLM
(`complete`/`chat`/`chat_json`/`chat(stream=True)`),
**multi-turn `chat_session`** (turn 2 recalls a name set in turn 1 — the gateway
holds the history), embeddings, the full KB lifecycle
(`create→upload→documents→retrieve→reindex→delete`) + RAG-grounded `chat`,
a TTS→ASR round-trip, and a compose-it-yourself speech translation
(ASR → chat → TTS). Account-lifecycle
calls (`register`/`rotate_key`/`rotate_user`) are shown but not executed.

Known env caveats (not SDK bugs): direct `/v1/embeddings` needs the gateway's
`GATEWAY_RAG_EMBED_*` upstream key (RAG embeddings work regardless); Whisper
hallucinates on synthetic TTS audio (real speech transcribes fine).
