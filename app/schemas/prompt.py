from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


def _check_len(v: str) -> str:
    if len(v) > settings.MAX_PROMPT_CHARS:
        raise ValueError(f"text exceeds the {settings.MAX_PROMPT_CHARS}-character limit")
    return v


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)

    _len = field_validator("text")(_check_len)


class PromptUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    text: Optional[str] = Field(default=None, min_length=1)

    @field_validator("text")
    @classmethod
    def _len(cls, v: Optional[str]) -> Optional[str]:
        return _check_len(v) if v is not None else v


class PromptResponse(BaseModel):
    id: str
    name: str
    text: str
    created_at: float
    updated_at: float


class PromptListResponse(BaseModel):
    prompts: list[PromptResponse]
    total: int
