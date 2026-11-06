from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AgentRequest(BaseModel):
    request: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Natural language request, e.g. 'Create a project plan for a mobile app'.",
    )

    @field_validator("request")
    @classmethod
    def clean_request(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 10:
            raise ValueError("Request is too short. Please describe the document you need.")
        return cleaned


class TaskItem(BaseModel):
    id: int
    title: str
    status: str = "pending"  # pending | done | failed


class Plan(BaseModel):
    document_type: str
    title: str
    assumptions: List[str] = []
    tasks: List[TaskItem]


class AgentResponse(BaseModel):
    status: str  # success | partial | failed
    message: str
    document_type: Optional[str] = None
    title: Optional[str] = None
    assumptions: List[str] = []
    review_notes: List[str] = []
    tasks: List[TaskItem] = []
    document_filename: Optional[str] = None
    download_url: Optional[str] = None