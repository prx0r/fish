from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Artifact(Base):
    """Immutable input: tweet, filing, message, paper, note, blog post.
    Replaces SourceRecord. Same contract with adapters via NormalizedItem."""
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("source_type", "external_id", name="uq_artifact_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    objects: Mapped[list["Object"]] = relationship(back_populates="artifact", cascade="all, delete-orphan")


class Object(Base):
    """Something meaningful discovered from artifacts.
    Evolves via versioning: when knowledge changes, version increments.
    Replaces Signal. Kind is deliberately open-ended."""
    __tablename__ = "objects"
    __table_args__ = (
        UniqueConstraint("object_key", "version", name="uq_object_key_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    object_key: Mapped[str] = mapped_column(String(256), index=True, comment="stable dedup key, e.g. 'entity:lpkf' or 'theory:ai-bottleneck'")
    kind: Mapped[str] = mapped_column(String(64), index=True, comment="entity|person|company|technology|idea|claim|theory|problem|question|decision|prediction|pick|joke|concept|thread")
    version: Mapped[int] = mapped_column(Integer, default=1, index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    domain: Mapped[str] = mapped_column(String(64), default="general", index=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True, comment="pgvector-compatible embedding for semantic search")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    artifact: Mapped[Artifact | None] = relationship(back_populates="objects")
    outgoing_edges: Mapped[list["Edge"]] = relationship(
        back_populates="source_object", foreign_keys="Edge.source_id",
        cascade="all, delete-orphan"
    )
    incoming_edges: Mapped[list["Edge"]] = relationship(
        back_populates="target_object", foreign_keys="Edge.target_id",
        cascade="all, delete-orphan"
    )
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="object", cascade="all, delete-orphan")


class Edge(Base):
    """Relationship between objects, backed by evidence.
    Generic edge types that work across domains."""
    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation", name="uq_edge_triple"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(64), index=True, comment="mentions|related_to|supports|contradicts|supersedes|causes|depends_on|evidence_for|authored_by|about")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_object: Mapped[Object] = relationship(foreign_keys=[source_id], back_populates="outgoing_edges")
    target_object: Mapped[Object] = relationship(foreign_keys=[target_id], back_populates="incoming_edges")


class Feed(Base):
    """A versioned attention program.
    The feed algorithm is the product object, not the post.
    Feed algorithms are versioned, forkable, and shareable."""
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    public: Mapped[bool] = mapped_column(Boolean, default=True)
    icon: Mapped[str] = mapped_column(String(8), default="⚡")
    version: Mapped[int] = mapped_column(Integer, default=1)
    weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    forked_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="ID of feed this was forked from")
    creator_id: Mapped[str] = mapped_column(String(128), default="system", comment="User or agent that created this feed")
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    interactions: Mapped[list["Interaction"]] = relationship(back_populates="feed", cascade="all, delete-orphan")
    versions: Mapped[list["FeedVersion"]] = relationship(back_populates="feed", cascade="all, delete-orphan")


class FeedVersion(Base):
    """Immutable snapshot of a feed's algorithm at a point in time.
    Every edit creates a new version. Users can fork from any version."""
    __tablename__ = "feed_versions"
    __table_args__ = (UniqueConstraint("feed_id", "version", name="uq_feed_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text, default="")
    weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feed: Mapped[Feed] = relationship(back_populates="versions")


class Interaction(Base):
    """What a user/agent did with an object at a specific version.
    The key primitive for delta feeds: user last saw version N."""
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("user_id", "object_id", name="uq_user_object_interaction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    feed_id: Mapped[int | None] = mapped_column(ForeignKey("feeds.id", ondelete="CASCADE"), nullable=True, index=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    object_version: Mapped[int] = mapped_column(Integer, default=1)
    action: Mapped[str] = mapped_column(String(32), comment="DONE|SAVE|FOLLOW|NOISE|seen")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feed: Mapped[Feed | None] = relationship(back_populates="interactions")
    object: Mapped[Object] = relationship(back_populates="interactions")


class Channel(Base):
    """Something a creator publishes. Separated from Feed (consumer algorithm).
    A Channel is a producer output; a Feed is a consumer's attention program."""
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    creator_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(8), default="📡")
    visibility: Mapped[str] = mapped_column(String(32), default="public", comment="public|unlisted|private")
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IngestionRun(Base):
    """Audit log for ingestion pipeline runs."""
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    objects_created: Mapped[int] = mapped_column(Integer, default=0)
    edges_created: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Watchlist(Base):
    """Stocks to monitor daily."""
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    sector: Mapped[str] = mapped_column(String(64), default="general")
    thesis: Mapped[str] = mapped_column(Text, default="")
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StockSnapshot(Base):
    """Daily price snapshot."""
    __tablename__ = "stock_snapshots"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ticker_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[str] = mapped_column(String(10))
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    news: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvestorReport(Base):
    """Daily investor report for a stock."""
    __tablename__ = "investor_reports"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ticker_report_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[str] = mapped_column(String(10))
    summary: Mapped[str] = mapped_column(Text, default="")
    bull_case: Mapped[str] = mapped_column(Text, default="")
    bear_case: Mapped[str] = mapped_column(Text, default="")
    key_levels: Mapped[str] = mapped_column(Text, default="{}")
    action: Mapped[str] = mapped_column(String(16), default="HOLD")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMemory(Base):
    """AI chat memory per stock."""
    __tablename__ = "chat_memory"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), default="default")
    message: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperTrade(Base):
    """Paper trade log — AI vs Human performance tracking."""
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8), comment="BUY/SELL")
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(8), comment="ai/user")
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_reasoning: Mapped[str] = mapped_column(Text, default="")
    user_decision: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiSuggestion(Base):
    """AI trade suggestion awaiting user decision."""
    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    """User account."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Portfolio(Base):
    """User's portfolio (one per user)."""
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="My Portfolio")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Friendship(Base):
    """Friend connections between users."""
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_friendship"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    friend_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PerformanceSnapshot(Base):
    """Daily performance snapshot for a portfolio."""
    __tablename__ = "performance_snapshots"
    __table_args__ = (UniqueConstraint("portfolio_id", "date", name="uq_portfolio_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[str] = mapped_column(String(10))
    total_value: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float, default=0)
    daily_return: Mapped[float] = mapped_column(Float, default=0)
    cumulative_return: Mapped[float] = mapped_column(Float, default=0)
    ai_suggested_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
