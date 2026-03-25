from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Material(BaseModel):
    id: Optional[int] = None
    filename: str
    filepath: str
    num_pages: int
    created_at: datetime = Field(default_factory=datetime.now)


class ContentChunk(BaseModel):
    id: Optional[int] = None
    material_id: int
    page: int
    chunk_text: str


class QuizSession(BaseModel):
    id: Optional[int] = None
    material_ids: list[int]
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)


class QuizQuestion(BaseModel):
    id: Optional[int] = None
    session_id: int
    question: str
    correct_answer: str
    page_reference: str
    material_id: int


class Answer(BaseModel):
    id: Optional[int] = None
    question_id: int
    user_answer: str
    is_correct: bool
    feedback: str
