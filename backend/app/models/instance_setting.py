"""Instance configuration entered in the browser (#220), encrypted at rest."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InstanceSetting(Base):
    __tablename__ = "instance_settings"

    # A Settings field name, e.g. "llm_api_key".
    key: Mapped[str] = mapped_column(String, primary_key=True)
    # Fernet token (app.utils.secretbox, purpose "instance-settings").
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
