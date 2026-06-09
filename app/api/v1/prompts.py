"""CRUD for the custom prompt library.

Prompts are stored durably on disk (see services/prompt_store.py) and selected
per analysis request via `prompt_id`. Behind the API key like the other data
routes.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from app.schemas.prompt import PromptCreate, PromptListResponse, PromptResponse, PromptUpdate
from app.services import prompt_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(body: PromptCreate) -> PromptResponse:
    """Store a new prompt version. Returns its generated id."""
    record = prompt_store.create_prompt(body.name, body.text)
    logger.info("Created prompt %s (%s)", record["id"], record["name"])
    return PromptResponse(**record)


@router.get("", response_model=PromptListResponse)
async def list_prompts() -> PromptListResponse:
    """List every stored prompt, newest first."""
    records = prompt_store.list_prompts()
    return PromptListResponse(prompts=[PromptResponse(**r) for r in records], total=len(records))


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(prompt_id: str) -> PromptResponse:
    record = prompt_store.get_prompt(prompt_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return PromptResponse(**record)


@router.put("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(prompt_id: str, body: PromptUpdate) -> PromptResponse:
    """Update a prompt's name and/or text in place (id is stable)."""
    record = prompt_store.update_prompt(prompt_id, name=body.name, text=body.text)
    if record is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    logger.info("Updated prompt %s", prompt_id)
    return PromptResponse(**record)


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: str) -> Response:
    if not prompt_store.delete_prompt(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    logger.info("Deleted prompt %s", prompt_id)
    return Response(status_code=204)
