from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


class SavedQuery(Base):
    __tablename__ = "saved_queries"
    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    sql_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    dataset = relationship("Dataset", back_populates="saved_queries")
    owner = relationship("User", back_populates="saved_queries")
    share_links = relationship("ShareLink", back_populates="query", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_saved_queries_dataset_id", "dataset_id"),
    )
