"""8개 테이블 SQLAlchemy 2.0 모델 (DeclarativeBase + Mapped + mapped_column)."""
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    itemId: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    sellerId: Mapped[str] = mapped_column(String(50), nullable=False)
    sellerReliability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    askingPrice: Mapped[int] = mapped_column(Integer, nullable=False)
    estimatedPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priceDiffPercent: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    llmConfidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llmReason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failStage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    failReason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    collectedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analyzedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notifiedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ItemImage(Base):
    __tablename__ = "item_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[int] = mapped_column(Integer, ForeignKey("items.itemId"), nullable=False)
    imageUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    imageOrder: Mapped[int] = mapped_column(Integer, nullable=False)
    analysisResult: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    avgPrice: Mapped[int] = mapped_column(Integer, nullable=False)
    minPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maxPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sampleCount: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshotDate: Mapped[date] = mapped_column(Date, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[int] = mapped_column(Integer, ForeignKey("items.itemId"), nullable=False)
    notifyType: Mapped[str] = mapped_column(String(20), nullable=False)
    notifyStatus: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    processedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resultDetail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    errorDetail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[int] = mapped_column(Integer, nullable=False)  # FK 아님 — 아직 items에 없는 매물도 로그 남김
    sellerId: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiReqResLog(Base):
    __tablename__ = "api_req_res_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    callId: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    itemId: Mapped[int | None] = mapped_column(Integer, nullable=True)
    apiType: Mapped[str] = mapped_column(String(20), nullable=False)
    event: Mapped[str] = mapped_column(String(10), nullable=False)
    requestBody: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    responseBody: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    httpStatus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    durationMs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WatchKeyword(Base):
    __tablename__ = "watch_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    maxPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # default=True (SQLite Boolean 호환)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ItemEmbedding(Base):
    __tablename__ = "item_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cleanedTitle: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyzedPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector: Mapped[str] = mapped_column(Text, nullable=False)  # 384차원 벡터를 JSON 문자열로 저장
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
