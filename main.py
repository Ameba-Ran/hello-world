"""hello-world — a tiny app-server built on ameba-sdk.

The shape of a third-party MEC app: a browser / phone calls THIS server's HTTP
API, and this server calls the cluster's AI services through the SDK. One
``AmebaAI`` client is built at startup from the ``AMEBA_*`` environment
variables (the key you issued in the Console) and shared by every request.

    export AMEBA_LLM_BASE_URL=http://<Console address>/porin/<site slug>   # the site's porin via the Console host
    export AMEBA_API_KEY=bsa_...                          # = a porin customer
    uv run python run.py          # or: uvicorn main:app --reload

Endpoints (open http://localhost:8000 for a live demo page):

    GET  /            browser demo page (type text, hear/read the result)
    GET  /healthz     liveness
    GET  /services    which AI services this key can see
    GET  /models      LLM models available to this key
    POST /chat        {"prompt","model"?}              -> {"reply"}
    POST /transcribe  multipart: file, engine?, language?  -> {"text"}
    POST /speak       {"text"}                         -> audio/wav
    POST /embed       {"texts": ["...", "..."]}        -> {"dims","vectors"}
    POST /kb/setup    {"name","text","chunking"?}       -> {"kb_id","chunks","embedded"}
    POST /kb/upload   multipart: kb_id, file             -> {"doc_id","chunk_count","embedded","status"}
    POST /ask         {"question","kb_id","mode"?}      -> {"answer","references"}
    POST /kb/retrieve {"query","kb_id","top_k"?}        -> {"mode_used","references"}
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from ameba_sdk import AmebaAI, AmebaError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hello-world")

# The gateway serves several models; pick one (override with AMEBA_LLM_MODEL).
MODEL = os.environ.get("AMEBA_LLM_MODEL", "google/gemma-4-E4B-it")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the client once from AMEBA_BASE_URL / AMEBA_API_KEY (or the
    # ~/.ameba/credentials.json a previous register() wrote). Reused by all
    # requests; closed on shutdown.
    app.state.ai = AmebaAI.from_env()
    try:
        names = ", ".join(f"{f.name}[{f.kind}]" for f in app.state.ai.available())
        logger.info("connected — services: %s", names or "none")
    except AmebaError as exc:
        logger.warning("could not list services at startup: %s", exc)
    yield
    app.state.ai.close()


app = FastAPI(title="hello-world (ameba-sdk)", lifespan=lifespan)


class ChatIn(BaseModel):
    prompt: str
    model: str | None = None


class EmbedIn(BaseModel):
    texts: list[str]


class KbSetupIn(BaseModel):
    name: str = "demo-kb"
    text: str
    chunking: dict | None = None    # {"strategy","max_chars","overlap_chars"}


class AskIn(BaseModel):
    question: str
    kb_id: str
    mode: str | None = None         # hybrid(預設) | bm25 | dense


class RetrieveIn(BaseModel):
    query: str
    kb_id: str
    top_k: int = 3


def _ai(app: FastAPI) -> AmebaAI:
    return app.state.ai


# --- liveness / discovery -----------------------------------------------------

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/services")
async def services() -> dict:
    return {"services": [
        {"name": f.name, "kind": f.kind} for f in _ai(app).available()
    ]}


@app.get("/models")
async def models() -> dict:
    return {"models": _ai(app).llm.models()}


# --- the four AI legs ---------------------------------------------------------

@app.post("/chat")
async def chat(body: ChatIn) -> dict:
    try:
        reply = _ai(app).llm.chat(body.prompt, model=body.model or MODEL)
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"reply": str(reply)}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    engine: str = Form("whisper"),          # "whisper" (multilingual) | "taigi"
    language: str | None = Form(None),      # e.g. "zh" / "en" / "vi"
) -> dict:
    audio = await file.read()
    try:
        tr = _ai(app).asr.transcribe(audio, engine=engine, language=language)
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"text": tr.text}


@app.post("/speak")
async def speak(body: ChatIn) -> Response:
    try:
        wav = _ai(app).tts.speak(body.prompt)
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return Response(content=wav, media_type="audio/wav")


@app.post("/embed")
async def embed(body: EmbedIn) -> dict:
    try:
        vectors = _ai(app).embeddings.embed(body.texts, model="bge-m3")
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"count": len(vectors), "dims": len(vectors[0]) if vectors else 0,
            "vectors": vectors}


# --- RAG knowledge base demo ----------------------------------------------------

@app.post("/kb/setup")
async def kb_setup(body: KbSetupIn) -> dict:
    """One call for demos: create a KB (with optional chunking config) and
    index the given text. Returns the kb_id to /ask against."""
    try:
        kw = {"chunking": body.chunking} if body.chunking else {}
        kb = _ai(app).kb.create(body.name, **kw)
        doc = _ai(app).kb.upload(kb.id, body.text.encode("utf-8"),
                                 filename="demo.txt")
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"kb_id": kb.id, "chunks": doc.chunk_count, "embedded": doc.embedded}


@app.post("/kb/upload")
async def kb_upload(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Upload a REAL file into an existing KB — unlike /kb/setup (inline
    text over JSON), this takes actual file bytes off the wire. ``ai.kb.upload()``
    doesn't care about the format: txt/md go through the flat chunker
    unchanged, but pdf/docx/pptx/xlsx/csv/json/xml are detected by content
    (magic bytes, not the filename extension) and routed through the
    layout-aware parent/child ingestion pipeline server-side — tables stay
    atomic, and a matched chunk's surrounding section comes back on
    ``RetrievedReference.parent_text`` from /kb/retrieve (see below).

        curl -X POST localhost:8000/kb/upload \\
             -F kb_id=<kb id from /kb/setup or ai.kb.create()> \\
             -F file=@handbook.pdf     # or .docx/.pptx/.xlsx/.csv/.json/.xml

    Poll ``ai.kb.document(kb_id, doc_id)`` (not exposed here — see
    docs/USAGE.md §8) if ``embedded`` comes back False: that means the
    embedder was unavailable at upload time (the doc still indexed
    lexically/BM25), not that indexing is still running — call
    ``ai.kb.reindex(kb_id)`` once the embedder is back to backfill vectors.
    """
    payload = await file.read()
    try:
        doc = _ai(app).kb.upload(kb_id, payload, filename=file.filename)
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"doc_id": doc.id, "name": doc.name, "chunk_count": doc.chunk_count,
            "embedded": doc.embedded, "status": doc.status}


@app.post("/ask")
async def ask(body: AskIn) -> dict:
    """RAG Q&A: retrieve from the KB (hybrid BM25+vector by default),
    answer with citations. ``mode`` shows off per-request retrieval:
    try the same paraphrased question with "bm25" vs "hybrid"."""
    kw = {}
    if body.mode:
        kw["retrieval"] = {"mode": body.mode}
    try:
        reply = _ai(app).llm.chat(
            body.question, model=MODEL,
            use_rag=True, knowledge_bases=[body.kb_id], **kw,
        )
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"answer": str(reply),
            "references": [r.get("content") for r in reply.references]}


@app.post("/kb/retrieve")
async def kb_retrieve(body: RetrieveIn) -> dict:
    """Same KB as /ask, but no LLM call — just the raw hits. Use this when
    you want to build your own prompt (or a "search this KB" UI).

    ``parent_text`` (only populated for documents ingested through the
    layout-aware pipeline — see /kb/upload) is the full section/table the
    matched ``content`` chunk belongs to: broader context than the chunk
    that actually matched, handy when a short child chunk alone reads as
    ambiguous out of context. ``None`` for plain txt/md uploads, which have
    no such structural parent."""
    try:
        result = _ai(app).kb.retrieve(body.query, dataset_ids=[body.kb_id],
                                      top_k=body.top_k)
    except AmebaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"mode_used": result.mode_used,
            "references": [{"content": r.content, "score": r.score,
                            "parent_text": r.parent_text} for r in result.references]}


# --- browser demo page --------------------------------------------------------

_PAGE = """<!doctype html><meta charset="utf-8">
<title>hello-world · ameba-sdk</title>
<style>
 body{font:16px/1.6 system-ui,"Noto Sans TC",sans-serif;max-width:640px;margin:60px auto;padding:0 20px;color:#2b3440}
 h1{font-size:22px} input,select,button{font:inherit;padding:8px 10px;border:1px solid #cdd7e1;border-radius:8px}
 button{background:#00a2e8;color:#fff;border:0;cursor:pointer} .row{display:flex;gap:8px;margin:12px 0}
 #out,#ans{background:#f6f9fc;border:1px solid #e3e9f0;border-radius:10px;padding:14px;min-height:28px;white-space:pre-wrap}
 a{color:#0087c4}
</style>
<h1>hello-world · ameba-sdk</h1>
<p>這台 app-server 用 <code>AmebaAI.from_env()</code> 連到 gateway。</p>

<h1 style="margin-top:36px">RAG 知識庫問答</h1>
<p>貼一段知識(例:術語表、SOP),建立知識庫後用<b>同義改寫</b>的問題測試 hybrid 檢索:</p>
<textarea id="kbtext" rows="4" style="width:100%;font:inherit;padding:8px;border:1px solid #cdd7e1;border-radius:8px">若出現胸悶、心悸、盜汗等症狀,請立即前往急診。
外籍勞工的居留證(ARC)遺失時,應向移民署申請補發。</textarea>
<div class="row"><button onclick="setupKb()">建立知識庫</button><span id="kbinfo" style="color:#7c8794;align-self:center"></span></div>
<div class="row">
 <input id="q" value="我的證件不見了要找誰" style="flex:1">
 <select id="mode"><option value="hybrid">hybrid</option><option value="bm25">bm25</option><option value="dense">dense</option></select>
 <button onclick="ask()">問</button>
</div>
<div id="ans">—</div>
<p style="color:#7c8794;font-size:14px">API:<code>/chat /transcribe /speak /embed /kb/setup /ask /models</code></p>
<script>
let KB=null;
async function setupKb(){
  const i=document.getElementById('kbinfo'); i.textContent='建立中…';
  const r=await fetch('/kb/setup',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:'demo-kb',text:document.getElementById('kbtext').value})});
  const d=await r.json();
  if(r.ok){KB=d.kb_id;i.textContent=`✓ ${d.chunks} chunks,向量化:${d.embedded}`;}
  else i.textContent='錯誤: '+(d.detail||r.status);
}
async function ask(){
  const a=document.getElementById('ans');
  if(!KB){a.textContent='先建立知識庫';return;}
  a.textContent='…';
  const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({question:document.getElementById('q').value,kb_id:KB,
      mode:document.getElementById('mode').value})});
  const d=await r.json();
  if(!r.ok){a.textContent='錯誤: '+(d.detail||r.status);return;}
  a.innerHTML='<b>回答:</b>'+d.answer.replace(/</g,'&lt;')+
    '<br><br><b>引用:</b>'+(d.references.length?d.references.map(x=>'「'+x.replace(/</g,'&lt;')+'」').join('<br>'):'<i>無(bm25 模式下同義詞查不到是正常的)</i>');
}
</script>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _PAGE
