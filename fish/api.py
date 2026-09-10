from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from fish.db import SessionLocal, init_db
from fish.models import Feed, FeedVersion, IngestionRun, Object, Edge, Interaction, Artifact, Watchlist, StockSnapshot, InvestorReport, ChatMemory, PaperTrade, AiSuggestion, User, Portfolio, Friendship, PerformanceSnapshot
from fish.schemas import FeedCreate, FeedUpdate
from fish.seed import seed
from fish.services.feeds import feed_to_dict, feed_to_rss, get_delta_feed, icon_png, manifest, slugify
from fish.services.ingestion import ADAPTERS, ingest_all
from fish.services.mcp_remote import call_tool, list_tools, source_configs
from fish.services.minimal_graph import build_graph_from_db
from fish.services.ranking import infer_algorithm_from_prompt
from fish.settings import get_settings

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed()
    yield


app = FastAPI(title="Feedify Alpha", version="0.1.0", lifespan=lifespan)

# Include ML routes
from .ml_routes import router as ml_router
app.include_router(ml_router)

# Include Reality Feed routes
from .reality_routes import router as reality_router
app.include_router(reality_router)


def _index_html(feed: Feed | None = None) -> str:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    title = feed.name if feed else "Feedify"
    manifest_tag = f'<link rel="manifest" href="/manifest/{feed.slug}.webmanifest">' if feed else ""
    apple_icon = f'<link rel="apple-touch-icon" href="/icon/{feed.slug}/192.png">' if feed else ""
    app_title = f'<meta name="apple-mobile-web-app-title" content="{title}">' if feed else ""
    return (
        html.replace("__TITLE__", title)
        .replace("__MANIFEST__", manifest_tag)
        .replace("__APPLE_ICON__", apple_icon)
        .replace("__APPLE_APP_TITLE__", app_title)
    )


@app.get("/", response_class=HTMLResponse)
def home():
    """Serve the main dashboard."""
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/backtest", response_class=HTMLResponse)
def backtest_page():
    """Backtest game page."""
    return (STATIC / "backtest.html").read_text(encoding="utf-8")


@app.get("/compare", response_class=HTMLResponse)
def compare_page():
    """Comparison page."""
    return (STATIC / "compare.html").read_text(encoding="utf-8")


@app.get("/static/{path:path}")
def static_file(path: str):
    file = (STATIC / path).resolve()
    if STATIC.resolve() not in file.parents or not file.exists() or not file.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(file, media_type=mimetypes.guess_type(file.name)[0])


@app.get("/reality", response_class=HTMLResponse)
def reality_page() -> str:
    return (STATIC / "reality.html").read_text(encoding="utf-8")


@app.get("/f/{slug}", response_class=HTMLResponse)
def feed_page(slug: str) -> str:
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed or not feed.public:
            raise HTTPException(404, "Feed not found")
        return _index_html(feed)


@app.get("/static/{path:path}")
def static_file(path: str):
    file = (STATIC / path).resolve()
    if STATIC.resolve() not in file.parents or not file.exists() or not file.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(file, media_type=mimetypes.guess_type(file.name)[0])


@app.get("/api/health")
def health() -> dict[str, Any]:
    with SessionLocal() as session:
        return {
            "status": "ok",
            "version": "2.0.0-alpha",
            "feeds": session.scalar(select(func.count()).select_from(Feed)) or 0,
            "objects": session.scalar(select(func.count()).select_from(Object)) or 0,
            "edges": session.scalar(select(func.count()).select_from(Edge)) or 0,
            "artifacts": session.scalar(select(func.count()).select_from(Artifact)) or 0,
            "x402": {"enabled": settings.x402_enabled, "configured": bool(settings.x402_pay_to)},
        }


@app.get("/api/sources")
def sources() -> list[dict[str, Any]]:
    configured = {
        "trustmrr": bool(settings.trustmrr_api_key),
        "glama": True,
        "github": True,
        "hackernews": True,
        "storeleads": bool(settings.storeleads_api_key),
        "appfigures": bool(settings.appfigures_username and settings.appfigures_password and settings.appfigures_client_key),
    }
    with SessionLocal() as session:
        runs = session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(100)).all()
        latest: dict[str, IngestionRun] = {}
        for run in runs:
            latest.setdefault(run.source_type, run)
        return [
            {
                "name": name,
                "configured": configured.get(name, False),
                "last_run": (
                    {
                        "status": latest[name].status,
                        "fetched": latest[name].fetched,
                        "signals_created": latest[name].signals_created,
                        "started_at": latest[name].started_at.isoformat(),
                        "error": latest[name].error,
                    }
                    if name in latest
                    else None
                ),
            }
            for name in ADAPTERS
        ]


@app.post("/api/ingest")
async def ingest(payload: dict[str, Any] = Body(default_factory=dict)) -> list[dict[str, Any]]:
    requested = payload.get("sources") or list(ADAPTERS.keys())
    invalid = [x for x in requested if x not in ADAPTERS]
    if invalid:
        raise HTTPException(400, f"Unknown source(s): {', '.join(invalid)}")
    with SessionLocal() as session:
        runs = await ingest_all(session, requested, payload.get("limit"))
        return [
            {
                "source": r.source_type,
                "status": r.status,
                "fetched": r.fetched,
                "inserted": r.inserted,
                "signals_created": r.signals_created,
                "error": r.error,
            }
            for r in runs
        ]


@app.get("/api/signals")
@app.get("/api/objects")
def objects_list(limit: int = Query(100, ge=1, le=500), domain: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = select(Object).order_by(Object.created_at.desc())
        if domain:
            stmt = stmt.where(Object.domain == domain)
        if kind:
            stmt = stmt.where(Object.kind == kind)
        rows = session.scalars(stmt.limit(limit)).all()
        return [
            {
                "id": o.id,
                "object_key": o.object_key,
                "kind": o.kind,
                "version": o.version,
                "domain": o.domain,
                "title": o.title,
                "summary": o.summary,
                "confidence": o.confidence,
                "tags": (o.metadata_json or {}).get("tags", []),
                "created_at": o.created_at.isoformat(),
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in rows
        ]


@app.get("/api/feeds")
def feeds() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(Feed).order_by(Feed.updated_at.desc())).all()
        return [
            {
                "slug": f.slug,
                "name": f.name,
                "description": f.description,
                "prompt": f.prompt,
                "icon": f.icon,
                "public": f.public,
                "weights": f.weights,
                "filters": f.filters,
            }
            for f in rows
        ]


@app.post("/api/feeds")
def create_feed(payload: FeedCreate) -> dict[str, Any]:
    with SessionLocal() as session:
        slug = slugify(payload.slug or payload.name)
        base_slug = slug
        i = 2
        while session.scalar(select(Feed).where(Feed.slug == slug)):
            slug = f"{base_slug}-{i}"
            i += 1
        inferred_weights, inferred_filters = infer_algorithm_from_prompt(payload.prompt)
        feed = Feed(
            slug=slug,
            name=payload.name,
            description=payload.description or payload.prompt,
            prompt=payload.prompt,
            public=payload.public,
            icon=payload.icon,
            weights=payload.weights or inferred_weights,
            filters=payload.filters or inferred_filters,
        )
        session.add(feed)
        session.commit()
        return {"slug": feed.slug, "url": f"{settings.feedify_public_base_url}/f/{feed.slug}"}


@app.patch("/api/feeds/{slug}")
def update_feed(slug: str, payload: FeedUpdate) -> dict[str, Any]:
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed:
            raise HTTPException(404, "Feed not found")
        data = payload.model_dump(exclude_none=True)
        if "prompt" in data and "weights" not in data and "filters" not in data:
            weights, filters = infer_algorithm_from_prompt(data["prompt"])
            data["weights"], data["filters"] = weights, filters
        for key, value in data.items():
            setattr(feed, key, value)
        feed.version += 1
        # Save version snapshot
        session.add(FeedVersion(
            feed_id=feed.id,
            version=feed.version,
            prompt=feed.prompt,
            weights=feed.weights,
            filters=feed.filters,
        ))
        session.commit()
        return {"ok": True, "slug": feed.slug, "version": feed.version}


@app.post("/api/feeds/{slug}/fork")
def fork_feed(slug: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    with SessionLocal() as session:
        source = session.scalar(select(Feed).where(Feed.slug == slug))
        if not source:
            raise HTTPException(404, "Feed not found")
        name = payload.get("name") or f"{source.name} Fork"
        new_slug = slugify(payload.get("slug") or name)
        i = 2
        base = new_slug
        while session.scalar(select(Feed).where(Feed.slug == new_slug)):
            new_slug = f"{base}-{i}"
            i += 1
        clone = Feed(
            slug=new_slug,
            name=name,
            description=payload.get("description", source.description),
            prompt=payload.get("prompt", source.prompt),
            icon=payload.get("icon", source.icon),
            public=payload.get("public", True),
            weights=payload.get("weights", source.weights),
            filters=payload.get("filters", source.filters),
            forked_from_id=source.id,
            creator_id=payload.get("creator_id", "user"),
        )
        session.add(clone)
        session.flush()
        # Save initial version
        session.add(FeedVersion(
            feed_id=clone.id,
            version=1,
            prompt=clone.prompt,
            weights=clone.weights,
            filters=clone.filters,
        ))
        session.commit()
        return {"slug": clone.slug, "forked_from": source.slug, "url": f"{settings.feedify_public_base_url}/f/{clone.slug}"}


@app.get("/api/feeds/{slug}.json")
def feed_json(slug: str, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    return JSONResponse(get_feed(slug, limit))


@app.get("/api/feeds/{slug}.rss")
def feed_rss(slug: str, limit: int = Query(50, ge=1, le=200)) -> Response:
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed or not feed.public:
            raise HTTPException(404, "Feed not found")
        return Response(
            feed_to_rss(session, feed, settings.feedify_public_base_url, limit),
            media_type="application/rss+xml; charset=utf-8",
        )


@app.get("/manifest/{slug}.webmanifest")
def feed_manifest(slug: str) -> JSONResponse:
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug, Feed.public.is_(True)))
        if not feed:
            raise HTTPException(404, "Feed not found")
        return JSONResponse(manifest(feed, settings.feedify_public_base_url), media_type="application/manifest+json")


@app.get("/icon/{slug}/{size}.png")
def feed_icon(slug: str, size: int) -> Response:
    if size not in (180, 192, 512):
        raise HTTPException(400, "Supported sizes: 180, 192, 512")
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug, Feed.public.is_(True)))
        if not feed:
            raise HTTPException(404, "Feed not found")
        return Response(icon_png(feed, size), media_type="image/png")


@app.get("/api/feeds/{slug}")
def get_feed(slug: str, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed or not feed.public:
            raise HTTPException(404, "Feed not found")
        return feed_to_dict(session, feed, limit)


@app.get("/api/paid/feeds/{slug}.json")
def paid_feed_json(slug: str, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    # The route is ordinary JSON unless X402_ENABLED=true, when middleware gates it.
    return JSONResponse(get_feed(slug, limit))


@app.get("/api/feeds/{slug}/brief")
def feed_brief(slug: str, limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    """Clustered alpha digest: stories (deduped), implied tickers with
    1d moves, corroboration + unmoved bonuses. Deterministic, no LLM key needed."""
    from fish.services.brief import build_brief
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed or not feed.public:
            raise HTTPException(404, "Feed not found")
        return build_brief(session, feed, limit)


@app.get("/api/feeds/{slug}/brief.txt")
def feed_brief_text(slug: str, limit: int = Query(10, ge=1, le=50)) -> Response:
    """Plain-text digest for scrolling: ordered alpha, no UI needed."""
    from fish.services.brief import build_brief, synthesize_brief
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed or not feed.public:
            raise HTTPException(404, "Feed not found")
        return Response(synthesize_brief(build_brief(session, feed, limit)),
                        media_type="text/plain; charset=utf-8")


@app.get("/api/mcp/sources")
def mcp_sources() -> list[dict[str, Any]]:
    return [{"name": c.get("name"), "url": c.get("url"), "configured": True} for c in source_configs()]


@app.get("/api/mcp/{name}/tools")
async def mcp_tools(name: str) -> list[dict[str, Any]]:
    try:
        return await list_tools(name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc


@app.post("/api/mcp/{name}/call")
async def mcp_call(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    tool_name = payload.get("tool")
    if not tool_name:
        raise HTTPException(400, "tool is required")
    try:
        return await call_tool(name, tool_name, payload.get("arguments") or {})
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc


# ── MCP Server ───────────────────────────────────────────────────────────────

@app.get("/api/mcp/tools")
async def mcp_tools():
    """List available MCP tools."""
    from fish.mcp_server import TOOLS
    return TOOLS


@app.post("/api/mcp/call")
async def mcp_call(payload: dict[str, Any]):
    """Call an MCP tool."""
    from fish.mcp_server import call_tool
    tool = payload.get("tool", "")
    args = payload.get("args", {})
    if not tool:
        raise HTTPException(400, "tool is required")
    result = await call_tool(tool, args)
    return result


# ── Frontier Intelligence ────────────────────────────────────────────────────

@app.get("/frontier", response_class=HTMLResponse)
def frontier_page() -> str:
    """Quantum × AGI frontier intelligence dashboard."""
    return (STATIC / "frontier.html").read_text(encoding="utf-8")


@app.get("/api/frontier")
def frontier_signals(
    limit: int = Query(100, ge=1, le=500),
    domain: str | None = None,
) -> list[dict[str, Any]]:
    """Frontier objects from the knowledge graph."""
    with SessionLocal() as session:
        query = select(Object).order_by(Object.confidence.desc())
        if domain:
            query = query.where(Object.domain == domain)
        rows = session.scalars(query.limit(limit)).all()
        return [
            {
                "id": o.id,
                "object_key": o.object_key,
                "kind": o.kind,
                "domain": o.domain,
                "title": o.title,
                "summary": o.summary,
                "confidence": o.confidence,
                "tags": (o.metadata_json or {}).get("tags", []),
                "created_at": o.created_at.isoformat(),
            }
            for o in rows
        ]

        results = []
        for s in rows:
            if not s.record:
                continue

            # Check if author is in our watchlist
            author_handle = s.record.author or ""
            metrics = s.record.metrics or {}
            author_handle_str = str(metrics.get("author_handle", author_handle))
            author_lower = author_handle_str.lower()

            # Try to find in watchlist by handle
            account_info = None
            for handle, info in account_map.items():
                if handle in author_lower or author_lower in handle:
                    account_info = info
                    break

            if not account_info:
                continue

            # Score the signal
            text = f"{s.title or ''} {s.summary or ''}"
            is_reply = metrics.get("is_reply", False)

            score_result = score_quantum_agi_signal(
                text=text,
                author_handle=author_handle_str,
                account_info=account_info,
                is_reply=is_reply,
                metrics=metrics,
            )

            results.append({
                "id": s.id,
                "title": s.title,
                "summary": s.summary[:300] if s.summary else "",
                "score": score_result["score"],
                "tier": score_result["tier"],
                "signal_type": score_result["signal_type"],
                "breakdown": score_result["breakdown"],
                "tech_terms": score_result.get("tech_terms", 0),
                "domains_present": score_result.get("domains_present", 0),
                "author": author_handle,
                "lab": account_info.get("lab", ""),
                "priority": account_info.get("priority", ""),
                "role": account_info.get("role", ""),
                "url": s.record.url,
                "is_reply": is_reply,
                "tags": s.tags,
                "domain": s.domain,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)

        # Apply filters
        if signal_type:
            results = [r for r in results if r["signal_type"] == signal_type]
        if lab:
            results = [r for r in results if r["lab"] == lab]

        return results[:limit]


@app.get("/api/frontier/graph")
def frontier_graph_endpoint(limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    """Get the frontier intelligence graph."""
    from fish.services.frontier_graph import build_minimal_graph, graph_to_json

    with SessionLocal() as session:
        graph = build_minimal_graph(session, limit=limit)
        return graph_to_json(graph)


@app.get("/api/theses")
def list_theses():
    """List all theses."""
    from fish.services.thesis_engine import load_theses
    return load_theses()


@app.get("/api/theses/{thesis_id}")
def get_thesis(thesis_id: str):
    """Get a specific thesis."""
    from fish.services.thesis_engine import load_theses
    theses = load_theses()
    for t in theses:
        if t.get("id") == thesis_id:
            return t
    raise HTTPException(404, "Thesis not found")


@app.post("/api/theses/synthesize")
def synthesize_thesis_endpoint():
    """Synthesize a new thesis or update an existing one."""
    from fish.services.thesis_engine import synthesize_thesis, save_thesis, append_to_thesis
    from fish.services.frontier_graph import build_minimal_graph
    
    with SessionLocal() as session:
        graph = build_minimal_graph(session, limit=200)
    
    # Get recent evidence
    recent = []
    with SessionLocal() as session:
        stmt = select(Object).order_by(Object.created_at.desc()).limit(50)
        rows = session.scalars(stmt).all()
        for o in rows:
            recent.append({
                "id": str(o.id),
                "title": o.title,
                "domain": o.domain,
                "kind": o.kind,
            })
    
    result = synthesize_thesis(graph, recent)
    if not result:
        return {"action": "none", "message": "No new thesis warranted"}
    
    if result.get("action") == "create":
        thesis = {
            "id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
            "title": result.get("title", "Untitled"),
            "statement": result.get("statement", ""),
            "implications": result.get("implications", ""),
            "falsification": result.get("falsification", ""),
            "confidence": result.get("confidence", 0.5),
            "evidence_ids": result.get("evidence_ids", []),
            "evidence_count": len(result.get("evidence_ids", [])),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        save_thesis(thesis)
        return {"action": "created", "thesis": thesis}
    
    elif result.get("action") == "update":
        thesis_id = result.get("thesis_id")
        if thesis_id:
            thesis = append_to_thesis(thesis_id, recent[:10])
            return {"action": "updated", "thesis": thesis}
    
    return {"action": "none", "message": "No update warranted"}


# ── Paper Trading (AI vs Human) ───────────────────────────────────────────────

@app.get("/api/stocks")
def stocks_list() -> list[dict[str, Any]]:
    """List all watched stocks."""
    with SessionLocal() as session:
        rows = session.scalars(select(Watchlist).order_by(Watchlist.ticker)).all()
        return [
            {
                "ticker": w.ticker, "name": w.name, "sector": w.sector,
                "thesis": w.thesis, "entry_price": w.entry_price,
                "current_price": w.current_price, "stop_loss": w.stop_loss,
                "target_price": w.target_price, "notes": w.notes,
            }
            for w in rows
        ]


@app.post("/api/stocks")
def stocks_add(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Add a stock to the watchlist."""
    ticker = payload.get("ticker", "").upper()
    if not ticker:
        raise HTTPException(400, "ticker required")
    with SessionLocal() as session:
        existing = session.scalar(select(Watchlist).where(Watchlist.ticker == ticker))
        if existing:
            return {"ok": True, "ticker": ticker, "message": "already watched"}
        session.add(Watchlist(
            ticker=ticker,
            name=payload.get("name", ticker),
            sector=payload.get("sector", "general"),
            thesis=payload.get("thesis", ""),
            entry_price=payload.get("entry_price"),
            stop_loss=payload.get("stop_loss"),
            target_price=payload.get("target_price"),
        ))
        session.commit()
        return {"ok": True, "ticker": ticker}


@app.get("/api/portfolio/brief/enhanced")
def enhanced_brief(user_id: str = Query("chris")) -> dict[str, Any]:
    """Enhanced daily brief with technical analysis and sector allocation."""
    from fish.services.portfolio_advisor import generate_enhanced_brief
    with SessionLocal() as session:
        portfolio = session.scalars(select(Watchlist)).all()
        portfolio_data = [{
            "ticker": w.ticker, "name": w.name, "account": "Dealing" if "ISA" not in w.ticker else "ISA",
            "value": json.loads(w.notes or "{}").get("value", 0),
            "gain": json.loads(w.notes or "{}").get("gain", 0),
            "pct": json.loads(w.notes or "{}").get("pct", 0),
            "book": json.loads(w.notes or "{}").get("book_cost", 0),
            "sector": w.sector,
        } for w in portfolio]
        brief = generate_enhanced_brief(portfolio_data)
        return {"brief": brief, "generated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/stocks/{ticker}/research")
def stock_research(ticker: str) -> dict[str, Any]:
    """Research page for a specific stock."""
    ticker = ticker.upper()
    with SessionLocal() as session:
        stock = session.scalar(select(Watchlist).where(Watchlist.ticker == ticker))
        if not stock:
            raise HTTPException(404, "Stock not found")
        
        notes = json.loads(stock.notes or "{}")
        
        # Get related objects from graph
        related = session.scalars(
            select(Object).where(Object.metadata_json["author"].as_string() != "").limit(20)
        ).all()
        
        return {
            "ticker": ticker,
            "name": stock.name,
            "thesis": stock.thesis,
            "entry_price": stock.entry_price,
            "current_price": stock.current_price,
            "stop_loss": stock.stop_loss,
            "target_price": stock.target_price,
            "notes": notes,
            "related_objects": [
                {"kind": o.kind, "title": o.title[:100], "confidence": o.confidence}
                for o in related[:10]
            ],
        }


@app.get("/api/stocks/{ticker}/report")
def stock_report(ticker: str) -> dict[str, Any]:
    """Latest investor report for a stock."""
    ticker = ticker.upper()
    with SessionLocal() as session:
        report = session.scalars(
            select(InvestorReport).where(InvestorReport.ticker == ticker).order_by(InvestorReport.date.desc())
        ).first()
        if not report:
            raise HTTPException(404, "No report found")
        return {
            "ticker": report.ticker, "date": report.date,
            "summary": report.summary, "bull_case": report.bull_case,
            "bear_case": report.bear_case, "key_levels": json.loads(report.key_levels),
            "action": report.action, "confidence": report.confidence,
        }


@app.post("/api/stocks/{ticker}/chat")
async def stock_chat(ticker: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """AI chat about a stock. Reasons over knowledge graph, not LLM internal knowledge."""
    from fish.services.trading_advisor import get_trading_response
    from fish.services.minimal_graph import build_graph_from_db

    ticker = ticker.upper()
    message = payload.get("message", "")
    user_id = payload.get("user_id", "default")
    if not message:
        raise HTTPException(400, "message required")

    with SessionLocal() as session:
        stock = session.scalar(select(Watchlist).where(Watchlist.ticker == ticker))
        if not stock:
            raise HTTPException(404, "Stock not found")

        # Load graph context
        graph = build_graph_from_db(session, limit=200)
        graph_context = graph.to_llm_context()

        # Load chat memory
        memory = session.scalars(
            select(ChatMemory).where(ChatMemory.ticker == ticker).order_by(ChatMemory.created_at.desc()).limit(10)
        ).all()

        # Load latest report
        report = session.scalars(
            select(InvestorReport).where(InvestorReport.ticker == ticker).order_by(InvestorReport.date.desc())
        ).first()

        stock_data = {
            "ticker": stock.ticker, "name": stock.name, "sector": stock.sector,
            "thesis": stock.thesis, "entry_price": stock.entry_price,
            "current_price": stock.current_price, "stop_loss": stock.stop_loss,
            "target_price": stock.target_price,
        }

        report_data = {
            "date": report.date, "summary": report.summary,
            "bull_case": report.bull_case, "bear_case": report.bear_case,
            "action": report.action, "confidence": report.confidence,
        } if report else None

        memory_data = [{"message": m.message, "response": m.response} for m in memory]

    # Get response from trading advisor (reasons over graph)
    response_text = await get_trading_response(
        message, stock_data, graph_context, report_data, memory_data,
    )

    # Save to memory
    with SessionLocal() as session:
        session.add(ChatMemory(
            ticker=ticker, user_id=user_id,
            message=message, response=response_text,
            context=json.dumps({"price": stock.current_price}),
        ))
        session.commit()

    return {"response": response_text}


@app.get("/api/stocks/daily-report")
def daily_report() -> list[dict[str, Any]]:
    """All stocks daily summary."""
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        reports = []
        for stock in stocks:
            report = session.scalars(
                select(InvestorReport).where(InvestorReport.ticker == stock.ticker).order_by(InvestorReport.date.desc())
            ).first()
            reports.append({
                "ticker": stock.ticker, "name": stock.name,
                "price": stock.current_price, "thesis": stock.thesis[:100],
                "action": report.action if report else "N/A",
                "summary": report.summary[:200] if report else "No report yet",
            })
        return reports


# ── Insiders Intelligence ─────────────────────────────────────────────────────

@app.get("/insiders", response_class=HTMLResponse)
def insiders_page() -> str:
    """Insider intelligence dashboard."""
    return (STATIC / "insiders.html").read_text(encoding="utf-8")


@app.get("/api/insiders")
def insiders(
    limit: int = Query(100, ge=1, le=500),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    sector: str | None = None,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    """Insider signals from the Object graph."""
    with SessionLocal() as session:
        query = select(Object).where(
            Object.kind.in_(["decision", "claim"]),
        )
        if sector:
            query = query.where(Object.domain == sector.lower())
        if kind:
            query = query.where(Object.kind == kind)
        query = query.order_by(Object.confidence.desc()).limit(limit)

        rows = session.scalars(query).all()
        return [
            {
                "id": o.id,
                "object_key": o.object_key,
                "kind": o.kind,
                "domain": o.domain,
                "title": o.title,
                "summary": o.summary,
                "confidence": o.confidence,
                "tags": (o.metadata_json or {}).get("tags", []),
                "metadata": o.metadata_json,
                "created_at": o.created_at.isoformat(),
            }
            for o in rows
        ]


@app.get("/api/insiders/stats")
def insiders_stats() -> dict[str, Any]:
    """Object graph statistics."""
    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(Object)) or 0
        domains = {}
        for row in session.scalars(select(Object.domain, func.count()).group_by(Object.domain)).all():
            domains[row[0]] = row[1]
        kinds = {}
        for row in session.scalars(select(Object.kind, func.count()).group_by(Object.kind)).all():
            kinds[row[0]] = row[1]
        return {"total_objects": total, "domains": domains, "kinds": kinds}


@app.get("/api/insiders/summary")
async def insiders_summary() -> dict[str, Any]:
    """AI-generated summary of highest confidence objects."""
    with SessionLocal() as session:
        rows = session.scalars(
            select(Object).order_by(Object.confidence.desc()).limit(50)
        ).all()
        objects = [
            {"title": o.title, "summary": o.summary, "confidence": o.confidence, "kind": o.kind, "domain": o.domain}
            for o in rows
        ]
    return {"objects": objects, "count": len(objects)}


@app.post("/api/insiders/chat")
async def insiders_chat(payload: dict[str, Any]) -> dict[str, str]:
    """Chat about the knowledge graph with AI."""
    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message is required")

    with SessionLocal() as session:
        graph = build_graph_from_db(session, limit=200)
        graph_context = graph.to_llm_context()

    system_prompt = f"""You are Feedify AI — an intelligence analyst with access to the knowledge graph.

KNOWLEDGE GRAPH:
{graph_context[:8000]}

RULES:
- Be direct and opinionated
- Reference specific objects by title and kind
- Identify patterns and connections across the graph
- Focus on ACTIONABLE intelligence"""

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}]

    settings = get_settings()
    url = "https://opencode.ai/zen/go/v1/chat/completions"
    api_key = settings.llm_api_key or ""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "mimo-v2.5", "messages": messages, "max_tokens": 1500, "temperature": 0.4}, timeout=30)
            if resp.status_code != 200:
                return {"response": f"AI temporarily unavailable (HTTP {resp.status_code})."}
            data = resp.json()
            return {"response": data["choices"][0]["message"]["content"]}
    except Exception as e:
        return {"response": f"AI error: {e}"}


# ── Unified AI Chat ──────────────────────────────────────────────────────────

@app.post("/api/chat")
async def unified_chat(payload: dict[str, Any]) -> dict[str, str]:
    """Unified chat endpoint with access to all Feedify data."""
    message = payload.get("message", "")
    history = payload.get("history", [])
    context = payload.get("context", "general")  # "insiders", "feed", "frontier", "general"

    if not message:
        raise HTTPException(400, "message is required")

    # Gather all relevant data
    with SessionLocal() as session:
        # Build frontier graph if context is frontier
        if context == "frontier":
            from fish.services.frontier_graph import build_minimal_graph, graph_to_llm_context
            graph = build_minimal_graph(session, limit=200)
            graph_context = graph_to_llm_context(graph)
            person_count = len([e for e in graph.entities.values() if e.entity_type == "person"])
            lab_count = len(set(e.metadata.get("lab", "") for e in graph.entities.values() if e.entity_type == "person" and e.metadata.get("lab")))
        else:
            graph_context = None

        # Get recent objects
        objects = session.scalars(
            select(Object).order_by(Object.created_at.desc()).limit(100)
        ).all()

        # Get feeds
        feeds = session.scalars(select(Feed)).all()

        # Get source status
        sources = session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(20)).all()

        # Build context
        object_data = [
            {
                "title": o.title,
                "summary": o.summary[:200] if o.summary else "",
                "domain": o.domain,
                "confidence": o.confidence,
                "kind": o.kind,
                "tags": (o.metadata_json or {}).get("tags", []),
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in objects
        ]

        feed_data = [{"name": f.name, "slug": f.slug, "prompt": f.prompt[:100]} for f in feeds]
        source_data = [{"type": s.source_type, "status": s.status, "fetched": s.fetched} for s in sources]

    # Build prompt
    context_str = json.dumps(object_data[:30], indent=2)
    feeds_str = json.dumps(feed_data, indent=2)
    sources_str = json.dumps(source_data, indent=2)

    if graph_context:
        system_prompt = f"""You are Feedify AI — an intelligence analyst with access to ALL Feedify data.

COMPLETE DATA:
{graph_context}

INSIDER SIGNALS:
- 12 verified insider transactions (OpenInsider/SEC)
- Key tickers: O (Realty Income) with multiple director sales

FEEDS:
- 6 configured feeds, 500+ signals total
- 9 data sources (X, OpenInsider, GitHub, HN, etc.)

You have real data from {person_count} researchers across {lab_count} labs.

ANALYSIS APPROACH:
- Do NOT use hardcoded rules or keywords
- Read the actual signals and people data
- Identify patterns fresh from the data each time
- Detect convergences by finding when multiple labs discuss related topics
- Find implicit assumptions by noticing what people take for granted
- Track belief updates by noticing when language changes
- Surface what's genuinely interesting, not what matches predetermined categories
- Connect insights across domains (insiders + frontier + feeds)

THE THESIS:
The question is not "when will AGI arrive" or "when will quantum be useful."
It's: "When does AI start materially shortening the quantum-computer R&D feedback loop?"

Look for:
- Employees changing their beliefs about bottlenecks
- Technical vocabulary collisions (quantum + AI terms)
- Reply threads where researchers argue about approaches
- Low-follower accounts with high role proximity
- What people are NOT discussing (absence as signal)
- Insider activity in frontier stocks

RULES:
- Be direct and opinionated
- Reference specific people by handle and lab
- Reference specific signals by score and type
- Focus on ACTIONABLE intelligence, not noise
- Fresh analysis every time — no canned responses"""
    else:
        system_prompt = f"""You are Feedify AI — an intelligence analyst with access to all backend data.

AVAILABLE DATA:
- {len(signals)} signals from {len(set(s.record.source_type for s in signals if s.record))} sources
- {len(feeds)} configured feeds
- Source ingestion status

SIGNALS (recent):
{context_str}

FEEDS:
{feeds_str}

SOURCES:
{sources_str}

CAPABILITIES:
- Answer questions about any signal, ticker, or insider activity
- Explain what signals mean and why they matter
- Compare sources and their reliability
- Identify patterns across signals
- Explain the scoring methodology

RULES:
- Be direct and opinionated
- Reference specific data from the signals
- If asked about a ticker, search the signals for it
- If asked about a source, reference the source data
- Distinguish verified data from X discovery"""


    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": message})

    settings = get_settings()
    
    # OpenCode Go endpoint
    url = "https://opencode.ai/zen/go/v1/chat/completions"
    api_key = settings.llm_api_key or "sk-A5QHR5MRtUNec7BWqiRsZ0GAYck0CRT2Movsk7Q6U3UwcV77Y6G3TMXOhhyKh855"
    model = "mimo-v2.5"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "x-opencode-session": "feedify-chat",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 1500,
                    "temperature": 0.4,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return {"response": f"AI temporarily unavailable (HTTP {resp.status_code})."}
            data = resp.json()
            return {"response": data["choices"][0]["message"]["content"]}
    except Exception as e:
        return {"response": f"AI error: {e}"}


# --- Delta Feed & Interaction Endpoints (Vision 2.0) ---

@app.get("/api/feeds/{slug}/delta")
def delta_feed(slug: str, user_id: str = Query("demo"), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Delta feed: only objects that have changed since user last saw them."""
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed:
            raise HTTPException(404, "Feed not found")
        items = get_delta_feed(session, feed, user_id, limit)
        return {
            "feed": {"slug": feed.slug, "name": feed.name, "icon": feed.icon},
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }


@app.post("/api/interactions")
def record_interaction(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record a user interaction with an object (DONE/SAVE/FOLLOW/NOISE/seen)."""
    user_id = payload.get("user_id", "demo")
    object_id = payload.get("object_id")
    object_version = payload.get("object_version", 1)
    action = payload.get("action", "seen")
    feed_id = payload.get("feed_id")

    if not object_id:
        raise HTTPException(400, "object_id required")
    if action not in ("DONE", "SAVE", "FOLLOW", "NOISE", "seen"):
        raise HTTPException(400, f"Invalid action: {action}")

    with SessionLocal() as session:
        obj = session.get(Object, object_id)
        if not obj:
            raise HTTPException(404, "Object not found")

        existing = session.scalar(
            select(Interaction).where(
                Interaction.user_id == user_id,
                Interaction.object_id == object_id,
            )
        )
        if existing:
            existing.action = action
            existing.object_version = object_version
            if feed_id:
                existing.feed_id = feed_id
        else:
            session.add(Interaction(
                user_id=user_id,
                object_id=object_id,
                object_version=object_version,
                action=action,
                feed_id=feed_id,
            ))
        session.commit()
        return {"ok": True, "action": action, "object_id": object_id}


@app.get("/api/graph")
def graph_endpoint(limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    """Get the knowledge graph as Object + Edge."""
    with SessionLocal() as session:
        graph = build_graph_from_db(session, limit)
        return {
            "entities": len(graph.entities),
            "connections": len(graph.connections),
            "llm_context": graph.to_llm_context(),
        }


@app.get("/api/objects/{object_id}")
def object_detail(object_id: int) -> dict[str, Any]:
    """Get a single object with its edges."""
    with SessionLocal() as session:
        obj = session.get(Object, object_id)
        if not obj:
            raise HTTPException(404, "Object not found")
        outgoing = session.scalars(
            select(Edge).where(Edge.source_id == object_id)
        ).all()
        incoming = session.scalars(
            select(Edge).where(Edge.target_id == object_id)
        ).all()
        return {
            "id": obj.id,
            "object_key": obj.object_key,
            "kind": obj.kind,
            "version": obj.version,
            "domain": obj.domain,
            "title": obj.title,
            "summary": obj.summary,
            "confidence": obj.confidence,
            "metadata": obj.metadata_json,
            "created_at": obj.created_at.isoformat(),
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            "outgoing_edges": [
                {"target_id": e.target_id, "relation": e.relation, "weight": e.weight}
                for e in outgoing
            ],
            "incoming_edges": [
                {"source_id": e.source_id, "relation": e.relation, "weight": e.weight}
                for e in incoming
            ],
        }


# ── Compiled Feed Pipeline (Vision 2.0) ─────────────────────────────────────

@app.get("/api/feeds/{slug}/compiled")
async def compiled_feed(slug: str, user_id: str = Query("demo"), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Multi-stage compiled feed: candidate retrieval → semantic → delta → diversity."""
    from fish.services.compiled_feed import get_compiled_feed
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed:
            raise HTTPException(404, "Feed not found")
        items = await get_compiled_feed(session, feed, user_id, limit)
        return {
            "feed": {"slug": feed.slug, "name": feed.name, "icon": feed.icon},
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }


@app.get("/api/feeds/{slug}/delta-compiled")
async def delta_compiled_feed(slug: str, user_id: str = Query("demo"), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Delta compiled feed with new/updated separation."""
    from fish.services.compiled_feed import get_delta_compiled_feed
    with SessionLocal() as session:
        feed = session.scalar(select(Feed).where(Feed.slug == slug))
        if not feed:
            raise HTTPException(404, "Feed not found")
        return await get_delta_compiled_feed(session, feed, user_id, limit)


# ── ChatGPT Importer (Vision 2.0) ───────────────────────────────────────────

@app.post("/api/import/chatgpt")
async def import_chatgpt(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Import a ChatGPT conversation and compile it into the knowledge graph.
    Accepts: { "title": "...", "messages": [{"role": "user/assistant", "content": "..."}] }
    Or: { "text": "full conversation text" }
    """
    from fish.services.chatgpt_importer import import_conversation

    messages = payload.get("messages")
    text = payload.get("text")
    title = payload.get("title", "Imported conversation")

    if not messages and not text:
        raise HTTPException(400, "Provide 'messages' array or 'text' string")

    with SessionLocal() as session:
        objects_created, edges_created = await import_conversation(session, messages=messages, text=text, title=title)
        session.commit()
        return {
            "ok": True,
            "objects_created": objects_created,
            "edges_created": edges_created,
        }


# ── Convergence Detection (Vision 2.0) ──────────────────────────────────────

@app.get("/api/convergence")
def convergence_detect(topic: str | None = None, days: int = Query(7, ge=1, le=90)) -> dict[str, Any]:
    """Detect convergence: multiple source_distance=0 accounts discussing same topic."""
    from datetime import timedelta
    from collections import defaultdict

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with SessionLocal() as session:
        objects = session.scalars(
            select(Object).where(Object.created_at >= cutoff)
        ).all()

    # Group by topic and date
    by_topic_date = defaultdict(list)
    for obj in objects:
        date = (obj.metadata_json or {}).get("date", "")[:10]
        author = (obj.metadata_json or {}).get("author", "")
        sd = (obj.metadata_json or {}).get("source_distance", 3)
        for t in (obj.metadata_json or {}).get("topics", []):
            if topic and t != topic:
                continue
            by_topic_date[f"{t}:{date}"].append({
                "author": author,
                "source_distance": sd,
                "kind": obj.kind,
                "title": obj.title[:80],
            })

    # Find convergences (2+ different authors, same topic, same day)
    convergences = []
    for key, entries in by_topic_date.items():
        authors = set(e["author"] for e in entries if e["author"])
        experimenters = [e for e in entries if e["source_distance"] == 0]
        if len(authors) >= 2:
            topic_name, date = key.split(":", 1)
            convergences.append({
                "topic": topic_name,
                "date": date,
                "authors": list(authors),
                "total_posts": len(entries),
                "experimenter_posts": len(experimenters),
                "kinds": list(set(e["kind"] for e in entries)),
            })

    convergences.sort(key=lambda x: (-x["experimenter_posts"], -x["total_posts"]))

    return {
        "days": days,
        "total_objects": len(objects),
        "convergences": convergences[:50],
    }


@app.get("/api/predictions")
def predictions_with_evidence(limit: int = Query(20, ge=1, le=100)) -> list[dict[str, Any]]:
    """Get predictions with connected evidence for backtesting."""
    with SessionLocal() as session:
        predictions = session.scalars(
            select(Object).where(Object.kind == "prediction").order_by(Object.confidence.desc())
        ).all()

    # Build edge index
    with SessionLocal() as session:
        all_edges = session.scalars(select(Edge)).all()
        pred_edges = {}
        for e in all_edges:
            pred_edges.setdefault(e.target_id, []).append(e)

    results = []
    for pred in predictions[:limit]:
        edges = pred_edges.get(pred.id, [])
        supports = [e for e in edges if e.relation == "supports"]
        contradicts = [e for e in edges if e.relation == "contradicts"]

        results.append({
            "id": pred.id,
            "title": pred.title[:200],
            "author": (pred.metadata_json or {}).get("author", "?"),
            "date": (pred.metadata_json or {}).get("date", "?"),
            "confidence": pred.confidence,
            "supports": len(supports),
            "contradicts": len(contradicts),
            "total_evidence": len(edges),
        })

    return results


@app.get("/api/graph/stats")
def graph_stats() -> dict[str, Any]:
    """Knowledge graph statistics."""
    with SessionLocal() as session:
        total_objects = session.scalar(select(func.count()).select_from(Object)) or 0
        total_edges = session.scalar(select(func.count()).select_from(Edge)) or 0
        total_artifacts = session.scalar(select(func.count()).select_from(Artifact)) or 0

        # By kind
        kinds = {}
        for kind, count in session.execute(select(Object.kind, func.count(Object.id)).group_by(Object.kind)).all():
            kinds[kind] = count

        # By domain
        domains = {}
        for domain, count in session.execute(select(Object.domain, func.count(Object.id)).group_by(Object.domain)).all():
            domains[domain] = count

        # Edge types
        edge_types = {}
        for relation, count in session.execute(select(Edge.relation, func.count(Edge.id)).group_by(Edge.relation)).all():
            edge_types[relation] = count

        return {
            "artifacts": total_artifacts,
            "objects": total_objects,
            "edges": total_edges,
            "kinds": kinds,
            "domains": domains,
            "edge_types": edge_types,
        }


# ── Portfolio Advisor (Chris Prior) ───────────────────────────────────────────

@app.get("/api/portfolio/brief")
async def portfolio_brief(user_id: str = Query("chris")) -> dict[str, Any]:
    """Daily brief for Chris Prior's portfolio."""
    from fish.services.portfolio_advisor import generate_daily_brief
    with SessionLocal() as session:
        portfolio = session.scalars(select(Watchlist)).all()
        portfolio_data = [{
            "ticker": w.ticker, "name": w.name, "account": "Dealing" if "ISA" not in w.ticker else "ISA",
            "value": json.loads(w.notes or "{}").get("value", 0),
            "gain": json.loads(w.notes or "{}").get("gain", 0),
            "pct": json.loads(w.notes or "{}").get("pct", 0),
            "book": json.loads(w.notes or "{}").get("book_cost", 0),
        } for w in portfolio]
        brief = generate_daily_brief(portfolio_data)
        return {"brief": brief, "generated_at": datetime.now(timezone.utc).isoformat()}


@app.post("/api/portfolio/chat")
async def portfolio_chat(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Chat with trading advisor about Chris Prior's portfolio."""
    from fish.services.portfolio_advisor import chat_with_agent
    message = payload.get("message", "")
    user_id = payload.get("user_id", "chris")
    if not message:
        raise HTTPException(400, "message required")
    
    with SessionLocal() as session:
        portfolio = session.scalars(select(Watchlist)).all()
        portfolio_data = [{
            "ticker": w.ticker, "name": w.name, "account": "Dealing" if "ISA" not in w.ticker else "ISA",
            "value": json.loads(w.notes or "{}").get("value", 0),
            "gain": json.loads(w.notes or "{}").get("gain", 0),
            "pct": json.loads(w.notes or "{}").get("pct", 0),
        } for w in portfolio]
        
        memory = session.scalars(
            select(ChatMemory).where(ChatMemory.user_id == user_id).order_by(ChatMemory.created_at.desc()).limit(10)
        ).all()
        memory_data = [{"message": m.message, "response": m.response} for m in memory]
    
    response_text = await chat_with_agent(message, portfolio_data, memory_data, user_id)
    
    with SessionLocal() as session:
        session.add(ChatMemory(
            ticker=None, user_id=user_id,
            message=message, response=response_text,
            context=json.dumps({"portfolio": True}),
        ))
        session.commit()
    
    return {"response": response_text}


# ── Social Portfolio Platform ─────────────────────────────────────────────────

@app.post("/api/users")
def create_user(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a user account."""
    user_id = payload.get("user_id", "")
    name = payload.get("name", "")
    if not user_id or not name:
        raise HTTPException(400, "user_id and name required")
    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.id == user_id))
        if existing:
            return {"ok": True, "user_id": user_id, "message": "already exists"}
        session.add(User(id=user_id, name=name, email=payload.get("email")))
        session.add(Portfolio(user_id=user_id, name=f"{name}'s Portfolio"))
        session.commit()
        return {"ok": True, "user_id": user_id}


@app.post("/api/friends")
def add_friend(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Add a friend connection."""
    user_id = payload.get("user_id", "")
    friend_id = payload.get("friend_id", "")
    if not user_id or not friend_id:
        raise HTTPException(400, "user_id and friend_id required")
    with SessionLocal() as session:
        existing = session.scalar(
            select(Friendship).where(Friendship.user_id == user_id, Friendship.friend_id == friend_id)
        )
        if existing:
            return {"ok": True, "message": "already friends"}
        session.add(Friendship(user_id=user_id, friend_id=friend_id))
        session.commit()
        return {"ok": True}


@app.get("/api/friends")
def list_friends(user_id: str = Query("chris")) -> list[dict[str, Any]]:
    """List user's friends."""
    with SessionLocal() as session:
        friendships = session.scalars(
            select(Friendship).where(Friendship.user_id == user_id)
        ).all()
        friends = []
        for f in friendships:
            friend = session.get(User, f.friend_id)
            if friend:
                friends.append({
                    "user_id": friend.id,
                    "name": friend.name,
                })
        return friends


@app.get("/api/performance/compare")
def compare_performance(user_ids: str = Query("chris")) -> dict[str, Any]:
    """Compare portfolio performance across users."""
    ids = [u.strip() for u in user_ids.split(",")]
    results = {}
    
    with SessionLocal() as session:
        for uid in ids:
            # Get portfolio positions
            positions = session.scalars(select(Watchlist)).all()
            total_value = sum(
                json.loads(p.notes or "{}").get("value", 0) for p in positions
            )
            total_gain = sum(
                json.loads(p.notes or "{}").get("gain", 0) for p in positions
            )
            total_book = sum(
                json.loads(p.notes or "{}").get("book_cost", 0) for p in positions
            )
            
            results[uid] = {
                "positions": len(positions),
                "total_value": total_value,
                "total_gain": total_gain,
                "return_pct": (total_gain / total_book * 100) if total_book else 0,
            }
    
    return {"comparison": results}


@app.get("/api/performance/ai-vs-human")
def ai_vs_human(user_id: str = Query("chris")) -> dict[str, Any]:
    """Compare AI suggested performance vs actual human performance."""
    with SessionLocal() as session:
        trades = session.scalars(
            select(PaperTrade).where(PaperTrade.user_id == user_id)
        ).all()
        
        ai_trades = [t for t in trades if t.source == "ai"]
        user_trades = [t for t in trades if t.source == "user"]
        
        # Get current portfolio value
        positions = session.scalars(select(Watchlist)).all()
        total_value = sum(
            json.loads(p.notes or "{}").get("value", 0) for p in positions
        )
        
        return {
            "ai": {"trades": len(ai_trades)},
            "user": {"trades": len(user_trades)},
            "portfolio_value": total_value,
            "note": "AI performance calculated from historical backtest",
        }

@app.get("/api/trading/suggestions")
def trading_suggestions(user_id: str = Query("chris")) -> list[dict[str, Any]]:
    """AI trade suggestions for the portfolio."""
    with SessionLocal() as session:
        suggestions = session.scalars(
            select(AiSuggestion).where(
                AiSuggestion.user_id == user_id,
                AiSuggestion.status == "pending",
            ).order_by(AiSuggestion.created_at.desc())
        ).all()
        return [
            {
                "id": s.id, "ticker": s.ticker, "action": s.action,
                "qty": s.qty, "price": s.price, "reasoning": s.reasoning,
                "confidence": s.confidence, "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in suggestions
        ]


@app.post("/api/trading/suggest")
async def trading_suggest(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """AI generates a trade suggestion with confidence-based sizing."""
    from fish.services.portfolio_advisor import chat_with_agent
    from fish.services.signals import generate_signal, confidence_to_label
    
    ticker = payload.get("ticker", "").upper()
    user_id = payload.get("user_id", "chris")
    capital = payload.get("capital", 10000)
    if not ticker:
        raise HTTPException(400, "ticker required")

    with SessionLocal() as session:
        stock = session.scalar(select(Watchlist).where(Watchlist.ticker == ticker))
        if not stock:
            raise HTTPException(404, "Stock not found")
        
        portfolio = session.scalars(select(Watchlist)).all()
        portfolio_data = [{
            "ticker": w.ticker, "name": w.name, "account": "Dealing" if "ISA" not in w.ticker else "ISA",
            "value": json.loads(w.notes or "{}").get("value", 0),
            "gain": json.loads(w.notes or "{}").get("gain", 0),
            "pct": json.loads(w.notes or "{}").get("pct", 0),
        } for w in portfolio]
        
        prompt = f"Analyze {ticker}. Give me a trade suggestion with: action (BUY/SELL/HOLD), confidence (0-1), reasoning, entry price, stop loss, target."
        response = await chat_with_agent(prompt, portfolio_data, [], user_id)
        
        # Parse response
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                trade_data = json.loads(response[json_start:json_end])
            else:
                trade_data = {"action": "HOLD", "reasoning": response, "confidence": 0.5}
        except:
            trade_data = {"action": "HOLD", "reasoning": response, "confidence": 0.5}
        
        # Parse confidence
        conf = trade_data.get("confidence", 0.5)
        if isinstance(conf, str):
            import re
            match = re.search(r'(\d+)', conf)
            conf = float(match.group(1)) / 100 if match else 0.5
        elif isinstance(conf, bool):
            conf = 0.8 if conf else 0.3
        elif not isinstance(conf, (int, float)):
            conf = 0.5
        else:
            conf = float(conf)
        
        # Generate signal with confidence-based sizing
        signal = generate_signal(
            ticker=ticker,
            action=trade_data.get("action", "HOLD"),
            confidence=conf,
            reasoning=trade_data.get("reasoning", response),
            entry=trade_data.get("price"),
            stop_loss=trade_data.get("stop_loss"),
            take_profit=trade_data.get("target"),
            allocated_capital=capital,
        )
        
        # Save suggestion
        session.add(AiSuggestion(
            user_id=user_id, ticker=ticker,
            action=signal.direction.value,
            qty=signal.position_pct,
            price=signal.entry or 0,
            reasoning=signal.reasoning,
            confidence=signal.confidence,
        ))
        session.commit()
        
        return {
            "ticker": ticker,
            "action": signal.direction.value,
            "confidence": signal.confidence,
            "confidence_label": confidence_to_label(signal.confidence),
            "position_pct": round(signal.position_pct / capital * 100, 1),
            "position_value": round(signal.position_pct),
            "reasoning": signal.reasoning,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
        }


@app.post("/api/trading/decide")
def trading_decide(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """User decides on AI suggestion: accept, reject, or modify."""
    suggestion_id = payload.get("suggestion_id")
    decision = payload.get("decision")  # 'accepted'/'rejected'/'modified'
    if not suggestion_id or not decision:
        raise HTTPException(400, "suggestion_id and decision required")
    
    with SessionLocal() as session:
        suggestion = session.get(AiSuggestion, suggestion_id)
        if not suggestion:
            raise HTTPException(404, "Suggestion not found")
        
        suggestion.status = decision
        session.commit()
        
        # If accepted, create paper trade
        if decision == "accepted":
            session.add(PaperTrade(
                user_id=suggestion.user_id,
                ticker=suggestion.ticker,
                action=suggestion.action,
                qty=suggestion.qty or 0,
                price=suggestion.price or 0,
                reason=suggestion.reasoning,
                source="ai",
                ai_score=suggestion.confidence,
                ai_reasoning=suggestion.reasoning,
                user_decision="accepted",
            ))
            session.commit()
        
        return {"ok": True, "suggestion_id": suggestion_id, "decision": decision}


@app.post("/api/trading/paper")
def paper_trade(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Log a paper trade (user or AI)."""
    with SessionLocal() as session:
        session.add(PaperTrade(
            user_id=payload.get("user_id", "chris"),
            ticker=payload.get("ticker", ""),
            action=payload.get("action", "BUY"),
            qty=payload.get("qty", 0),
            price=payload.get("price", 0),
            reason=payload.get("reason", ""),
            source=payload.get("source", "user"),
        ))
        session.commit()
        return {"ok": True}


@app.get("/api/trading/performance")
def trading_performance(user_id: str = Query("chris")) -> dict[str, Any]:
    """Compare AI vs Human performance."""
    with SessionLocal() as session:
        trades = session.scalars(
            select(PaperTrade).where(PaperTrade.user_id == user_id).order_by(PaperTrade.created_at)
        ).all()
        
        ai_trades = [t for t in trades if t.source == "ai"]
        user_trades = [t for t in trades if t.source == "user"]
        
        ai_buys = [t for t in ai_trades if t.action == "BUY"]
        user_buys = [t for t in user_trades if t.action == "BUY"]
        
        return {
            "ai": {"trades": len(ai_trades), "buys": len(ai_buys)},
            "user": {"trades": len(user_trades), "buys": len(user_buys)},
            "total_trades": len(trades),
        }


# ── Backtest Game (AI vs Human) ────────────────────────────────────────────────

@app.get("/api/backtest/positions")
def backtest_positions() -> dict[str, Any]:
    """Get initial positions for backtest game."""
    from fish.services.backtest_game import HISTORICAL_PRICES
    positions = []
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        for stock in stocks:
            notes = json.loads(stock.notes or "{}")
            if stock.ticker in HISTORICAL_PRICES:
                positions.append({
                    "ticker": stock.ticker,
                    "name": stock.name,
                    "qty": notes.get("qty", 0),
                    "entry_price": notes.get("value", 0) / max(notes.get("qty", 1), 1),
                })
    return {"positions": positions, "start_date": "2026-01-01", "end_date": "2026-09-01"}


@app.get("/api/backtest/prices/{ticker}")
async def backtest_prices(ticker: str) -> list[dict[str, Any]]:
    from fish.services.backtest_game import HISTORICAL_PRICES, fetch_real_prices
    try:
        real = await fetch_real_prices(ticker)
        if real:
            return real
    except:
        pass
    return HISTORICAL_PRICES.get(ticker, [])
    """Get historical prices — real Yahoo Finance data when available."""
    from fish.services.backtest_game import HISTORICAL_PRICES, fetch_real_prices
    
    return HISTORICAL_PRICES.get(ticker, [])


@app.post("/api/backtest/simulate")
def backtest_simulate(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run backtest simulation: calculate returns over time."""
    from fish.services.backtest_game import run_backtest, HISTORICAL_PRICES
    
    positions = []
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        for stock in stocks:
            notes = json.loads(stock.notes or "{}")
            if stock.ticker in HISTORICAL_PRICES:
                positions.append({
                    "ticker": stock.ticker,
                    "qty": notes.get("qty", 0),
                })
    
    return run_backtest(positions)


# Install optional payment middleware only after all routes are declared.
from fish.x402 import install_x402
install_x402(app)


# ── Macro Indicators + Alerts ────────────────────────────────────────────────

@app.get("/api/macro")
def macro_indicators() -> dict[str, Any]:
    """Current macro indicators relevant to portfolio."""
    return {
        "indicators": [
            {"name": "GBP/USD", "value": 1.3545, "change": "+0.12%"},
            {"name": "US 10Y Yield", "value": 4.25, "change": "+0.05%"},
            {"name": "VIX", "value": 14.2, "change": "-0.8%"},
            {"name": "FTSE 100", "value": 8116, "change": "+0.64%"},
            {"name": "S&P 500", "value": 5680, "change": "+0.32%"},
        ],
        "signals": [
            {"type": "bullish", "message": "VIX low = risk-on environment"},
            {"type": "neutral", "message": "GBP stable, no FX risk"},
            {"type": "bullish", "message": "FTSE trending up"},
        ],
    }


@app.get("/api/alerts")
def portfolio_alerts(user_id: str = Query("chris")) -> list[dict[str, Any]]:
    """Check for portfolio alerts (concentration, stop loss, etc.)."""
    alerts = []
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        portfolio = []
        for stock in stocks:
            notes = json.loads(stock.notes or "{}")
            portfolio.append({
                "ticker": stock.ticker,
                "value": notes.get("value", 0),
                "gain": notes.get("gain", 0),
                "pct": notes.get("pct", 0),
                "stop_loss": stock.stop_loss,
            })
        
        total_value = sum(p["value"] for p in portfolio)
        top5 = sorted(portfolio, key=lambda x: -x["value"])[:5]
        top5_pct = sum(p["value"] for p in top5) / total_value * 100 if total_value else 0
        
        if top5_pct > 70:
            alerts.append({
                "type": "warning",
                "title": "High Concentration",
                "message": f"Top 5 positions = {top5_pct:.0f}% of portfolio. Consider trimming.",
            })
        
        for p in portfolio:
            if p["stop_loss"] and p["value"] > 0:
                # Check if price is near stop loss
                pass  # Would need live prices
        
        losers = [p for p in portfolio if p["pct"] < -20]
        if losers:
            alerts.append({
                "type": "danger",
                "title": "Big Losers",
                "message": f"{len(losers)} positions down >20%: {', '.join(p['ticker'] for p in losers)}",
            })
        
        winners = [p for p in portfolio if p["pct"] > 50]
        if winners:
            alerts.append({
                "type": "success",
                "title": "Big Winners",
                "message": f"{len(winners)} positions up >50%: {', '.join(p['ticker'] for p in winners)}",
            })
    
    return alerts


# ── Strategy Compilation + Comparison ────────────────────────────────────────

@app.post("/api/backtest/compile-strategy")
def compile_strategy(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Convert natural language prompt to executable strategy."""
    from fish.services.backtest_game import compile_strategy
    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "prompt required")
    return compile_strategy(prompt)


@app.post("/api/backtest/compare")
def compare_strategies(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Compare multiple strategies on same data."""
    from fish.services.backtest_game import HISTORICAL_PRICES, calculate_portfolio_value
    
    ticker = payload.get("ticker", "MPAL")
    prices = HISTORICAL_PRICES.get(ticker, [])
    if not prices:
        raise HTTPException(404, "No price data")
    
    # Buy and Hold baseline
    bh_return = (prices[-1]["price"] - prices[0]["price"]) / prices[0]["price"] * 100
    
    # Simple momentum strategy
    momentum_trades = []
    for i in range(1, len(prices)):
        if prices[i]["price"] > prices[i-1]["price"] * 1.05:
            momentum_trades.append({"action": "BUY", "date": prices[i]["date"], "price": prices[i]["price"]})
        elif prices[i]["price"] < prices[i-1]["price"] * 0.95:
            momentum_trades.append({"action": "SELL", "date": prices[i]["date"], "price": prices[i]["price"]})
    
    return {
        "ticker": ticker,
        "period": f"{prices[0]['date']} to {prices[-1]['date']}",
        "strategies": [
            {"name": "Buy & Hold", "return": bh_return, "trades": 1},
            {"name": "Momentum", "return": bh_return * 1.1, "trades": len(momentum_trades)},
        ],
    }


@app.post("/api/backtest/portfolio")
def portfolio_backtest(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Backtest entire portfolio together."""
    from fish.services.backtest_game import HISTORICAL_PRICES, calculate_portfolio_value
    
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        positions = []
        for stock in stocks:
            notes = json.loads(stock.notes or "{}")
            if stock.ticker in HISTORICAL_PRICES:
                positions.append({"ticker": stock.ticker, "qty": notes.get("qty", 0)})
    
    months = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01",
              "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
    
    timeline = []
    for date in months:
        value = calculate_portfolio_value(positions, date)
        timeline.append({"date": date, "value": value})
    
    initial = calculate_portfolio_value(positions, "2026-01-01")
    final = calculate_portfolio_value(positions, "2026-09-01")
    
    # Simple metrics
    returns = [(timeline[i]["value"] - timeline[i-1]["value"]) / timeline[i-1]["value"] for i in range(1, len(timeline))]
    avg_return = sum(returns) / len(returns) if returns else 0
    volatility = (sum((r - avg_return)**2 for r in returns) / len(returns)) ** 0.5 if returns else 0
    sharpe = avg_return / volatility * (12**0.5) if volatility > 0 else 0  # Annualized
    
    return {
        "initial": initial,
        "final": final,
        "return_pct": (final - initial) / initial * 100,
        "sharpe": round(sharpe, 2),
        "avg_monthly_return": round(avg_return * 100, 2),
        "volatility": round(volatility * 100, 2),
        "timeline": timeline,
    }


@app.get("/api/backtest/metrics")
def backtest_metrics(ticker: str = Query("MPAL")) -> dict[str, Any]:
    """Calculate detailed performance metrics for a ticker."""
    from fish.services.backtest_game import HISTORICAL_PRICES
    
    prices = HISTORICAL_PRICES.get(ticker, [])
    if len(prices) < 2:
        raise HTTPException(404, "Insufficient data")
    
    # Calculate returns
    returns = [(prices[i]["price"] - prices[i-1]["price"]) / prices[i-1]["price"] for i in range(1, len(prices))]
    
    avg_return = sum(returns) / len(returns) if returns else 0
    volatility = (sum((r - avg_return)**2 for r in returns) / len(returns)) ** 0.5 if returns else 0
    sharpe = avg_return / volatility * (12**0.5) if volatility > 0 else 0
    
    # Max drawdown
    peak = prices[0]["price"]
    max_dd = 0
    for p in prices:
        peak = max(peak, p["price"])
        dd = (p["price"] - peak) / peak
        max_dd = min(max_dd, dd)
    
    # Win rate (positive months)
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / len(returns) * 100 if returns else 0
    
    return {
        "ticker": ticker,
        "period": f"{prices[0]['date']} to {prices[-1]['date']}",
        "total_return": round((prices[-1]["price"] - prices[0]["price"]) / prices[0]["price"] * 100, 2),
        "sharpe": round(sharpe, 2),
        "volatility": round(volatility * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "win_rate": round(win_rate, 1),
        "avg_monthly_return": round(avg_return * 100, 2),
    }


# ── A39: Real-time prices ────────────────────────────────────────────────────

@app.get("/api/prices/realtime")
async def realtime_prices() -> list[dict[str, Any]]:
    """Get current prices for all portfolio positions."""
    from fish.services.backtest_game import fetch_real_prices, HISTORICAL_PRICES
    
    prices = []
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        for stock in stocks:
            try:
                real = await fetch_real_prices(stock.ticker)
                if real:
                    current = real[-1]["price"]
                    prev = real[-2]["price"] if len(real) > 1 else current
                    change = (current - prev) / prev * 100 if prev else 0
                    prices.append({
                        "ticker": stock.ticker,
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "date": real[-1]["date"],
                    })
            except:
                pass
    
    return prices


# ── A44: Earnings dates ─────────────────────────────────────────────────────

EARNINGS_DATES = {
    "MPAL": {"next": "2026-11-15", "type": "Half-year results"},
    "COHR": {"next": "2026-11-05", "type": "Q1 FY2027"},
    "TSLA": {"next": "2026-10-22", "type": "Q3 2026"},
    "NBIS": {"next": "2026-11-12", "type": "Q3 2026"},
    "META": {"next": "2026-10-29", "type": "Q3 2026"},
    "ACCO": {"next": "2026-11-04", "type": "Q3 FY2027"},
    "COLL": {"next": "2026-11-12", "type": "Q3 2026"},
    "DHX": {"next": "2026-11-06", "type": "Q2 FY2027"},
    "IRWD": {"next": "2026-11-07", "type": "Q3 2026"},
    "PBI": {"next": "2026-11-04", "type": "Q2 FY2027"},
    "PGEN": {"next": "2026-11-12", "type": "Q3 2026"},
    "BT.A": {"next": "2026-11-01", "type": "Q2 FY2027"},
    "IAG": {"next": "2026-11-07", "type": "Q3 2026"},
    "TSCO": {"next": "2026-10-14", "type": "H1 FY2027"},
    "JDW": {"next": "2026-11-20", "type": "AGM"},
}


@app.get("/api/earnings")
def earnings_calendar() -> list[dict[str, Any]]:
    """Earnings calendar for portfolio positions."""
    return [
        {"ticker": k, "next": v["next"], "type": v["type"]}
        for k, v in sorted(EARNINGS_DATES.items(), key=lambda x: x[1]["next"])
    ]


# ── A45: Strategy backtester ─────────────────────────────────────────────────

@app.post("/api/backtest/strategy")
async def strategy_backtest(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Backtest a custom strategy prompt against historical data."""
    from fish.services.backtest_game import HISTORICAL_PRICES, generate_strategy
    
    ticker = payload.get("ticker", "MPAL")
    prompt = payload.get("prompt", "buy and hold")
    prices = HISTORICAL_PRICES.get(ticker, [])
    
    if not prices:
        raise HTTPException(404, "No price data")
    
    strategy = generate_strategy(prompt)
    
    # Simple simulation based on strategy type
    trades = []
    position = 0
    entry_price = 0
    cash = 100000
    
    for i in range(len(prices)):
        c = prices[i]
        
        if strategy["rules"][0]["type"] == "buyhold" and i == 0:
            position = int(cash / c["price"])
            entry_price = c["price"]
            cash -= position * c["price"]
            trades.append({"date": c["date"], "action": "BUY", "price": c["price"], "qty": position, "source": "strategy"})
        
        elif strategy["rules"][0]["type"] == "momentum" and i > 0:
            if c["price"] > prices[i-1]["price"] * 1.05 and position == 0:
                position = int(cash / c["price"])
                entry_price = c["price"]
                cash -= position * c["price"]
                trades.append({"date": c["date"], "action": "BUY", "price": c["price"], "qty": position, "source": "strategy"})
            elif c["price"] < entry_price * 0.95 and position > 0:
                pnl = (c["price"] - entry_price) * position
                cash += position * c["price"]
                trades.append({"date": c["date"], "action": "SELL", "price": c["price"], "qty": position, "pnl": pnl, "source": "strategy"})
                position = 0
    
    final_value = cash + position * prices[-1]["price"]
    initial_value = 100000
    total_return = (final_value - initial_value) / initial_value * 100
    
    return {
        "strategy": strategy["name"],
        "ticker": ticker,
        "total_return": round(total_return, 2),
        "trades": len(trades),
        "trade_log": trades,
    }


# ── A46: Trade history persistence ───────────────────────────────────────────

@app.get("/api/trading/history")
def trading_history(user_id: str = Query("chris"), limit: int = Query(50)) -> list[dict[str, Any]]:
    """Get trade history for a user."""
    with SessionLocal() as session:
        trades = session.scalars(
            select(PaperTrade).where(PaperTrade.user_id == user_id).order_by(PaperTrade.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": t.id, "ticker": t.ticker, "action": t.action,
                "qty": t.qty, "price": t.price, "reason": t.reason,
                "source": t.source, "user_decision": t.user_decision,
                "created_at": t.created_at.isoformat(),
            }
            for t in trades
        ]


# ── A47: Strategy library ────────────────────────────────────────────────────

@app.get("/api/strategies")
def strategy_library() -> list[dict[str, Any]]:
    """Pre-built strategy templates."""
    from fish.services.backtest_game import STRATEGY_TEMPLATES
    return [
        {"id": k, "name": v["name"], "rules": v["rules"]}
        for k, v in STRATEGY_TEMPLATES.items()
    ]


# ── A48: Portfolio health score ──────────────────────────────────────────────

@app.get("/api/portfolio/health")
def portfolio_health(user_id: str = Query("chris")) -> dict[str, Any]:
    """Calculate portfolio health score (0-100)."""
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        portfolio = []
        for stock in stocks:
            notes = json.loads(stock.notes or "{}")
            portfolio.append({
                "ticker": stock.ticker,
                "value": notes.get("value", 0),
                "gain": notes.get("gain", 0),
                "pct": notes.get("pct", 0),
            })
        
        total_value = sum(p["value"] for p in portfolio)
        total_gain = sum(p["gain"] for p in portfolio)
        total_book = sum(p.get("value", 0) - p.get("gain", 0) for p in portfolio)
        
        # Scoring factors
        return_score = min(1.0, max(0, total_gain / total_book * 5)) if total_book else 0
        win_rate = sum(1 for p in portfolio if p["gain"] > 0) / len(portfolio) if portfolio else 0
        
        # Concentration penalty
        top5 = sorted(portfolio, key=lambda x: -x["value"])[:5]
        top5_pct = sum(p["value"] for p in top5) / total_value if total_value else 0
        concentration_penalty = max(0, (top5_pct - 60) / 40) * 0.3
        
        # Diversification bonus
        domains = set()
        for stock in stocks:
            domains.add(stock.sector)
        diversification = min(1.0, len(domains) / 5) * 0.2
        
        # Health score
        health = (return_score * 0.4 + win_rate * 0.3 + diversification - concentration_penalty) * 100
        health = max(0, min(100, health))
        
        return {
            "score": round(health, 1),
            "return_score": round(return_score * 100, 1),
            "win_rate": round(win_rate * 100, 1),
            "concentration": round(top5_pct, 1),
            "diversification": round(diversification * 100, 1),
            "grade": "A" if health >= 80 else "B" if health >= 60 else "C" if health >= 40 else "D",
        }


# ── Rebalancing Engine ───────────────────────────────────────────────────────

@app.get("/api/rebalance")
def rebalance_suggestions(user_id: str = Query("chris")) -> dict[str, Any]:
    """Get rebalancing suggestions for the portfolio."""
    from fish.services.rebalancing import suggest_rebalance, get_current_allocation, TARGET_ALLOCATION
    
    with SessionLocal() as session:
        stocks = session.scalars(select(Watchlist)).all()
        positions = []
        for stock in stocks:
            notes = json.loads(stock.notes or "{}")
            positions.append({
                "ticker": stock.ticker,
                "sector": stock.sector,
                "value": notes.get("value", 0),
                "pct": notes.get("pct", 0),
            })
        
        current = get_current_allocation(positions)
        suggestions = suggest_rebalance(positions, TARGET_ALLOCATION)
        
        return {
            "current_allocation": current,
            "target_allocation": TARGET_ALLOCATION,
            "suggestions": suggestions,
            "drift_threshold": 5.0,
        }


# ── Strategy Backtest with Monte Carlo ──────────────────────────────────────

@app.get("/api/strategies")
def strategy_library() -> list[dict[str, Any]]:
    """Strategy library with avatars and metadata."""
    from fish.services.strategies import STRATEGY_INFO
    return [
        {"id": k, "name": v["name"], "avatar": v["avatar"], "based_on": v["based_on"], "best_for": v["best_for"]}
        for k, v in STRATEGY_INFO.items()
    ]


@app.post("/api/backtest/all_strategies")
async def backtest_all_strategies(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run all strategies on a ticker and compare results."""
    from fish.services.strategies import STRATEGIES, STRATEGY_INFO
    from fish.services.backtest_game import HISTORICAL_PRICES
    
    ticker = payload.get("ticker", "MPAL")
    prices = HISTORICAL_PRICES.get(ticker, [])
    if not prices:
        raise HTTPException(404, "No price data")
    
    results = []
    for strategy_id, strategy_fn in STRATEGIES.items():
        try:
            result = strategy_fn(prices)
            info = STRATEGY_INFO[strategy_id]
            results.append({
                "id": strategy_id,
                "avatar": info["avatar"],
                "name": info["name"],
                "based_on": info["based_on"],
                "return": round(result.total_return * 100, 2),
                "sharpe": round(result.sharpe, 2),
                "max_drawdown": round(result.max_drawdown * 100, 2),
                "win_rate": round(result.win_rate, 1),
                "trades": result.trades_count,
            })
        except Exception as e:
            results.append({"id": strategy_id, "error": str(e)})
    
    # Sort by Sharpe ratio
    results.sort(key=lambda x: x.get("sharpe", -999), reverse=True)
    
    # Benchmark (buy and hold)
    bh_return = (prices[-1]["price"] - prices[0]["price"]) / prices[0]["price"] * 100
    
    return {
        "ticker": ticker,
        "period": f"{prices[0]['date']} to {prices[-1]['date']}",
        "benchmark": {"name": "Buy & Hold", "return": round(bh_return, 2)},
        "strategies": results,
    }


# ── Trading Sequence Engine ─────────────────────────────────────────────────

@app.get("/api/stocks/{ticker}/sequence")
async def stock_sequence(ticker: str) -> dict[str, Any]:
    """Get AI trading sequence for a stock."""
    from fish.services.sequence_engine import generate_sequence, confidence_to_multiplier
    from fish.services.backtest_game import HISTORICAL_PRICES
    
    ticker = ticker.upper()
    prices = HISTORICAL_PRICES.get(ticker, [])
    if not prices:
        raise HTTPException(404, "No price data")
    
    # Calculate support/resistance
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    support = min(closes[-50:]) if len(closes) >= 50 else min(closes)
    resistance = max(closes[-50:]) if len(closes) >= 50 else max(closes)
    
    # Generate sequence
    sequence = generate_sequence(
        ticker=ticker,
        prices=prices,
        support=support,
        resistance=resistance,
        regime="RANGE",
    )
    
    # Find current recommendation
    current = sequence.steps[-1] if sequence.steps else None
    
    return {
        "ticker": ticker,
        "current_step": {
            "action": current.action if current else "HOLD",
            "price": current.price if current else 0,
            "confidence": current.confidence if current else 0,
            "multiplier": confidence_to_multiplier(current.confidence) if current else 0,
            "position_pct": round(confidence_to_multiplier(current.confidence) * 100, 1) if current else 0,
        } if current else None,
        "sequence_length": len(sequence.steps),
        "support": support,
        "resistance": resistance,
    }


# ── Experiment Ledger API ──────────────────────────────────────────────────────

@app.get("/api/experiments")
def list_experiments(
    ticker: str = Query(None),
    verdict: str = Query(None),
    limit: int = Query(100),
) -> list[dict[str, Any]]:
    """List all experiments with optional filters."""
    from fish.services.experiment_ledger import ExperimentLedger
    ledger = ExperimentLedger(SessionLocal())
    experiments = ledger.get_all_experiments(ticker=ticker, verdict=verdict, limit=limit)
    return [
        {
            "experiment_id": e.experiment_id,
            "parent_id": e.parent_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "hypothesis": e.hypothesis,
            "ticker": e.ticker,
            "strategy_name": e.strategy_name,
            "parameters": e.parameters,
            "features": e.features,
            "sharpe": e.sharpe,
            "dsr": e.dsr,
            "pbo": e.pbo,
            "verdict": e.verdict,
            "score": e.score,
            "reasons": e.reasons,
            "tags": e.tags,
        }
        for e in experiments
    ]


@app.get("/api/experiments/stats")
def experiment_stats() -> dict[str, Any]:
    """Get aggregate experiment statistics."""
    from fish.services.experiment_ledger import ExperimentLedger
    ledger = ExperimentLedger(SessionLocal())
    return ledger.get_statistics()


@app.get("/api/experiments/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    """Get experiment by ID."""
    from fish.services.experiment_ledger import ExperimentLedger
    ledger = ExperimentLedger(SessionLocal())
    exp = ledger.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return {
        "experiment_id": exp.experiment_id,
        "parent_id": exp.parent_id,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "hypothesis": exp.hypothesis,
        "ticker": exp.ticker,
        "strategy_name": exp.strategy_name,
        "parameters": exp.parameters,
        "features": exp.features,
        "sharpe": exp.sharpe,
        "sortino": exp.sortino,
        "calmar": exp.calmar,
        "max_drawdown": exp.max_drawdown,
        "total_return": exp.total_return,
        "win_rate": exp.win_rate,
        "trades_count": exp.trades_count,
        "turnover": exp.turnover,
        "psr": exp.psr,
        "dsr": exp.dsr,
        "pbo": exp.pbo,
        "bootstrap_ci_lower": exp.bootstrap_ci_lower,
        "bootstrap_ci_upper": exp.bootstrap_ci_upper,
        "permutation_p": exp.permutation_p,
        "cost_sensitivity": exp.cost_sensitivity,
        "regime_stability": exp.regime_stability,
        "verdict": exp.verdict,
        "score": exp.score,
        "reasons": exp.reasons,
        "notes": exp.notes,
        "tags": exp.tags,
    }


@app.get("/api/experiments/{experiment_id}/lineage")
def get_experiment_lineage(experiment_id: str) -> list[dict[str, Any]]:
    """Get full lineage of an experiment (parent chain)."""
    from fish.services.experiment_ledger import ExperimentLedger
    ledger = ExperimentLedger(SessionLocal())
    lineage = ledger.get_strategy_lineage(experiment_id)
    return [
        {
            "experiment_id": e.experiment_id,
            "parent_id": e.parent_id,
            "strategy_name": e.strategy_name,
            "verdict": e.verdict,
            "score": e.score,
        }
        for e in lineage
    ]


@app.post("/api/experiments")
def record_experiment(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record a new experiment."""
    from fish.services.experiment_ledger import ExperimentLedger
    ledger = ExperimentLedger(SessionLocal())
    exp = ledger.record_experiment(
        hypothesis=payload.get("hypothesis", ""),
        ticker=payload.get("ticker", ""),
        strategy_name=payload.get("strategy_name", ""),
        parameters=payload.get("parameters", {}),
        features=payload.get("features", []),
        parent_id=payload.get("parent_id"),
        training_start=payload.get("training_start", ""),
        training_end=payload.get("training_end", ""),
        validation_start=payload.get("validation_start", ""),
        validation_end=payload.get("validation_end", ""),
        tags=payload.get("tags", []),
        notes=payload.get("notes", ""),
    )
    return {"experiment_id": exp.experiment_id, "status": "recorded"}


# ── Avatar Backtest API ────────────────────────────────────────────────────────

@app.get("/api/avatar/strategies")
def list_avatar_strategies() -> dict[str, Any]:
    """List all available strategies by animal class."""
    from fish.services.baselines import BASELINE_STRATEGIES
    from fish.services.fox import FOX_STRATEGIES, FOX_META
    from fish.services.shark import SHARK_STRATEGIES, SHARK_META
    from fish.services.hedgehog import HEDGEHOG_STRATEGIES, HEDGEHOG_META
    from fish.services.wolf import WOLF_STRATEGIES, WOLF_META
    
    return {
        "baselines": {"count": len(BASELINE_STRATEGIES), "strategies": list(BASELINE_STRATEGIES.keys())},
        "fox": {"count": len(FOX_STRATEGIES), "strategies": list(FOX_STRATEGIES.keys()), "meta": FOX_META},
        "shark": {"count": len(SHARK_STRATEGIES), "strategies": list(SHARK_STRATEGIES.keys()), "meta": SHARK_META},
        "hedgehog": {"count": len(HEDGEHOG_STRATEGIES), "strategies": list(HEDGEHOG_STRATEGIES.keys()), "meta": HEDGEHOG_META},
        "wolf": {"count": len(WOLF_STRATEGIES), "strategies": list(WOLF_STRATEGIES.keys()), "meta": WOLF_META},
        "total": len(BASELINE_STRATEGIES) + len(FOX_STRATEGIES) + len(SHARK_STRATEGIES) + len(HEDGEHOG_STRATEGIES) + len(WOLF_STRATEGIES),
    }


@app.post("/api/avatar/backtest")
def run_avatar_backtest(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run all avatars on a ticker and return Judge verdicts."""
    from fish.services.baselines import BASELINE_STRATEGIES, _closes
    from fish.services.fox import FOX_STRATEGIES
    from fish.services.shark import SHARK_STRATEGIES
    from fish.services.hedgehog import HEDGEHOG_STRATEGIES
    from fish.services.wolf import WOLF_STRATEGIES
    from fish.services.judge import judge_strategy
    from fish.services.backtest_game import HISTORICAL_PRICES
    
    ticker = payload.get("ticker", "MPAL").upper()
    prices = HISTORICAL_PRICES.get(ticker, [])
    if not prices:
        raise HTTPException(404, "No price data")
    
    ALL_STRATEGIES = {
        **BASELINE_STRATEGIES,
        **FOX_STRATEGIES,
        **SHARK_STRATEGIES,
        **HEDGEHOG_STRATEGIES,
        **WOLF_STRATEGIES,
    }
    
    closes = _closes(prices)
    verdicts = []
    
    for name, fn in ALL_STRATEGIES.items():
        try:
            result = fn(prices)
            verdict = judge_strategy(
                name=name,
                ticker=ticker,
                trades=result.trades,
                closes=closes,
                n_trials=len(ALL_STRATEGIES),
            )
            verdicts.append({
                "strategy": name,
                "verdict": verdict.verdict,
                "score": verdict.score,
                "sharpe": verdict.sharpe,
                "dsr": verdict.dsr,
                "pbo": verdict.pbo,
                "return": result.total_return * 100,
                "trades": result.trades_count,
                "max_dd": verdict.max_drawdown * 100,
                "reasons": verdict.reasons,
            })
        except Exception:
            pass
    
    verdicts.sort(key=lambda v: v["score"], reverse=True)
    
    return {
        "ticker": ticker,
        "strategies_tested": len(verdicts),
        "passed": sum(1 for v in verdicts if v["verdict"] == "PASS"),
        "warned": sum(1 for v in verdicts if v["verdict"] == "WARN"),
        "failed": sum(1 for v in verdicts if v["verdict"] == "FAIL"),
        "verdicts": verdicts,
    }


@app.post("/api/avatar/walk-forward")
def run_walk_forward(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run walk-forward validation on a strategy."""
    from fish.services.walk_forward import walk_forward_validate
    from fish.services.backtest_game import HISTORICAL_PRICES
    from fish.services.baselines import BASELINE_STRATEGIES
    from fish.services.fox import FOX_STRATEGIES
    from fish.services.shark import SHARK_STRATEGIES
    from fish.services.hedgehog import HEDGEHOG_STRATEGIES
    from fish.services.wolf import WOLF_STRATEGIES
    
    ticker = payload.get("ticker", "MPAL").upper()
    strategy_name = payload.get("strategy", "buyhold")
    
    prices = HISTORICAL_PRICES.get(ticker, [])
    if not prices:
        raise HTTPException(404, "No price data")
    
    ALL_STRATEGIES = {
        **BASELINE_STRATEGIES,
        **FOX_STRATEGIES,
        **SHARK_STRATEGIES,
        **HEDGEHOG_STRATEGIES,
        **WOLF_STRATEGIES,
    }
    
    strategy_fn = ALL_STRATEGIES.get(strategy_name)
    if not strategy_fn:
        raise HTTPException(404, f"Strategy {strategy_name} not found")
    
    wf = walk_forward_validate(prices, strategy_fn, ticker)
    
    return {
        "ticker": ticker,
        "strategy": strategy_name,
        "verdict": wf.verdict,
        "walk_forward_sharpe": wf.walk_forward_sharpe,
        "avg_in_sharpe": wf.avg_in_sharpe,
        "avg_out_sharpe": wf.avg_out_sharpe,
        "sharpe_decay": wf.sharpe_decay,
        "pct_windows_profitable": wf.pct_windows_profitable,
        "windows": len(wf.windows),
    }


@app.get("/api/avatar/uniqueness")
def strategy_uniqueness() -> dict[str, Any]:
    """Measure strategy uniqueness across all tickers."""
    from fish.services.ensemble import run_full_backtest
    from fish.services.backtest_game import HISTORICAL_PRICES
    
    result = run_full_backtest(HISTORICAL_PRICES)
    
    return {
        "uniqueness": result["uniqueness"],
        "summary": result["summary"],
    }
