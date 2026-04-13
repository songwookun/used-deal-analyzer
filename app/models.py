"""
[TASK-005] SQLAlchemy 모델 정의 (8개 테이블)

ARCHITECTURE.md 6번 섹션의 DDL을 보고 ORM 모델로 변환해주세요.
SQLAlchemy 2.0 스타일(DeclarativeBase + Mapped + mapped_column)로 작성합니다.
"""
from datetime import datetime, date

from sqlalchemy import (
    String, Integer, Float, Text, JSON,
    DateTime, Date, Boolean, ForeignKey, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass   

"""
[요구사항 1] Item 모델 — __tablename__ = "items"

- ARCHITECTURE.md 6-1 DDL 그대로 변환 (컬럼 18개)
- itemId: INTEGER PK (autoincrement 아님)
- platform: String(20), NOT NULL
- sellerId: String(50), NOT NULL
- sellerReliability: String(20), nullable — S/A/B/C/F 등급 "문자열"이야 (Float 아님!)
- title: String(200), NOT NULL
- description: Text, nullable
- askingPrice: Integer, NOT NULL
- estimatedPrice: Integer, nullable
- priceDiffPercent: Float, nullable
- category: String(30), NOT NULL — DDL에 NOT NULL로 돼있어
- llmConfidence: Integer, nullable — DDL에 INTEGER야 (Float 아님)
- llmReason: String(200), nullable
- status: String(20), NOT NULL
- failStage: String(30), nullable
- failReason: String(50), nullable
- collectedAt: DateTime, NOT NULL — 수집 시간 (server_default 아님, 워커에서 넣음)
- analyzedAt: DateTime, nullable
- notifiedAt: DateTime, nullable
- createdAt, updatedAt: server_default=func.now()

[주의] nullable 컬럼은 Mapped[타입 | None]으로 선언해야 함
  예: estimatedPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
[주의] String에 길이 꼭 넣기 — String(20), String(50) 등 DDL 참고
"""
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

"""
[요구사항 2] ItemImage 모델 — __tablename__ = "item_images"

- ARCHITECTURE.md 6-2 DDL 참고
- id: autoincrement PK
- itemId: Integer, FK → items.itemId, NOT NULL
- imageUrl: String(500), NOT NULL
- imageOrder: Integer, NOT NULL
- analysisResult: JSON, nullable
- createdAt: server_default=func.now()

[주의] nullable인 analysisResult → Mapped[dict | None]
[주의] imageUrl에 String(500) 길이 지정
"""
class ItemImage(Base):
    __tablename__ = "item_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[int] = mapped_column(Integer, ForeignKey("items.itemId"), nullable=False)
    imageUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    imageOrder: Mapped[int] = mapped_column(Integer, nullable=False)
    analysisResult: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""
[요구사항 3] PriceHistory 모델 — __tablename__ = "price_history"

- ARCHITECTURE.md 6-3 DDL 참고
- id: autoincrement PK
- category: String(30), NOT NULL
- keyword: String(100), NOT NULL
- avgPrice: Integer, NOT NULL
- minPrice: Integer, nullable
- maxPrice: Integer, nullable
- sampleCount: Integer, NOT NULL
- snapshotDate: Date 타입 (DateTime 아님, 주의!)
- createdAt: server_default=func.now()

[주의] nullable인 minPrice, maxPrice → Mapped[int | None]
[주의] String 길이: category(30), keyword(100)
"""
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

"""
[요구사항 4] NotificationLog 모델 — __tablename__ = "notification_logs"

- ARCHITECTURE.md 6-4 DDL 참고
- id: autoincrement PK
- itemId: Integer, FK → items.itemId, NOT NULL
- notifyType: String(20), NOT NULL (TELEGRAM / DISCORD / EMAIL)
- notifyStatus: String(20), NOT NULL, server_default="PENDING"
- processedAt: DateTime, nullable
- resultDetail: JSON, nullable
- errorDetail: JSON, nullable
- createdAt, updatedAt: server_default=func.now()

[주의] nullable 컬럼들 → Mapped[타입 | None]
[주의] String 길이: notifyType(20), notifyStatus(20)
"""
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


"""
[요구사항 5] PipelineLog 모델 — __tablename__ = "pipeline_logs"

- ARCHITECTURE.md 6-5 DDL 참고
- id: autoincrement PK
- itemId: Integer, NOT NULL (FK 아님 — 아직 items에 없는 매물도 로그 남겨야 해서)
- sellerId: String(50), NOT NULL
- stage: String(30), NOT NULL (item_collector, seller_check 등)
- event: String(20), NOT NULL (START / SUCCESS / FAILED / SKIP)
- detail: JSON, nullable
- createdAt: server_default=func.now()

[주의] detail → Mapped[dict | None]
[주의] String 길이: sellerId(50), stage(30), event(20)
"""
class PipelineLog(Base):
    __tablename__ = "pipeline_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[int] = mapped_column(Integer, nullable=False)
    sellerId: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""
[요구사항 6] ApiReqResLog 모델 — __tablename__ = "api_req_res_logs"

- ARCHITECTURE.md 6-6 DDL 참고
- id: autoincrement PK
- callId: String(36), unique=True, NOT NULL (UUID 문자열)
- itemId: Integer, nullable
- apiType: String(20), NOT NULL (PLATFORM_API, LLM_API, NOTIFY_API, PRICE_API)
- event: String(10), NOT NULL (SENT / SUCCESS / FAILED)
- requestBody: JSON, nullable
- responseBody: JSON, nullable
- httpStatus: Integer, nullable
- durationMs: Integer, nullable
- createdAt, updatedAt: server_default=func.now()

[주의] nullable 컬럼 전부 → Mapped[타입 | None]
[주의] String 길이: callId(36), apiType(20), event(10)
"""
class ApiReqResLog(Base):
    __tablename__ = "api_req_res_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    callId: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    itemId: Mapped[int | None] = mapped_column(Integer, nullable=True)
    apiType: Mapped[str] = mapped_column(String(20), nullable=False)
    event: Mapped[str] = mapped_column(String(10), nullable=False)
    requestBody: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    responseBody: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    httpStatus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    durationMs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

"""
[요구사항 7] WatchKeyword 모델 — __tablename__ = "watch_keywords"

- ARCHITECTURE.md 6-7 DDL 참고
- id: autoincrement PK
- keyword: String(100), NOT NULL
- category: String(30), nullable
- maxPrice: Integer, nullable
- isActive: Boolean, NOT NULL, default=True (파이썬 레벨 기본값 사용)
- createdAt: server_default=func.now()

[주의] nullable 컬럼 → Mapped[타입 | None]
[주의] isActive 기본값: server_default="true" 쓰지 말고 default=True 사용 (SQLite 호환)
[주의] String 길이: keyword(100), category(30)
"""
class WatchKeyword(Base):
    __tablename__ = "watch_keywords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    maxPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""
[요구사항 8] ItemEmbedding 모델 — __tablename__ = "item_embeddings"

- README.md의 item_embeddings DDL 참고
- id: autoincrement PK
- itemId: Text, NOT NULL (FK 아님, 문자열 ID)
- title: Text, NOT NULL
- cleanedTitle: Text, NOT NULL
- category: Text, nullable
- price: Integer, nullable
- analyzedPrice: Integer, nullable
- vector: Text, NOT NULL (벡터를 JSON 문자열로 저장)
- createdAt: server_default=func.now()

[주의] nullable 컬럼 → Mapped[타입 | None]
[주의] DDL에서 TEXT로 돼있으니 String 아니고 Text 사용
"""
class ItemEmbedding(Base):
    __tablename__ = "item_embeddings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    itemId: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cleanedTitle: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyzedPrice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
