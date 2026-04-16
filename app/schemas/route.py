from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class RouteBase(BaseModel):
    name: Optional[str] = Field(None, description="Name of the survey route")
    description: Optional[str] = Field(None, description="Short description of the route")

class RouteCreate(RouteBase):
    pass

class RouteResponse(RouteBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
