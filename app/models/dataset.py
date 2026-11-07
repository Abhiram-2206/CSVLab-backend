import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, JSON, Text
from sqlalchemy.orm import relationship
from app.database import Base


class DatasetStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    status = Column(String(32), default=DatasetStatus.PROCESSING.value, nullable=False, index=True)
    row_count = Column(Integer, nullable=True)
    profile = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    owner = relationship("User", back_populates="datasets")
    saved_queries = relationship("SavedQuery", back_populates="dataset", cascade="all, delete-orphan")
    share_links = relationship("ShareLink", back_populates="dataset", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_datasets_owner_created", "owner_id", "created_at"),
    )
