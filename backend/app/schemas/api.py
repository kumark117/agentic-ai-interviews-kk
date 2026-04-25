from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.models import Confidence, Difficulty, EventType, ExperienceLevel, InterviewType, QuestionSource, SessionStatus


class QuestionDTO(BaseModel):
    question_id: str
    text: str
    difficulty: Difficulty


class StartSessionRequest(BaseModel):
    candidate_id: str
    candidate_name: str
    role: str
    experience_level: ExperienceLevel
    interview_type: InterviewType
    max_questions: int = Field(ge=1, le=20)

    @field_validator("candidate_id", "role", mode="before")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Must not be empty.")
        return normalized

    @field_validator("candidate_name", mode="before")
    @classmethod
    def validate_candidate_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Candidate Name must be a string.")
        normalized = value.strip()
        if len(normalized) < 2 or len(normalized) > 80:
            raise ValueError("Candidate Name must be 2 to 80 characters.")
        if not re.fullmatch(r"[A-Za-z .'-]+", normalized):
            raise ValueError("Candidate Name can contain letters, spaces, apostrophe ('), hyphen (-), and dot (.) only.")
        return normalized


class StartSessionResponse(BaseModel):
    session_id: str
    session_token: str
    status: SessionStatus
    current_question: QuestionDTO
    stream_url: str


class SubmitAnswerRequest(BaseModel):
    question_id: str
    answer_text: str = Field(min_length=1)


class SubmitAnswerResponse(BaseModel):
    status: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: str


class SessionEventDTO(BaseModel):
    event_id: str
    event_seq: int
    session_id: str
    event_type: EventType
    payload: dict[str, Any]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class GeneratedQuestion(BaseModel):
    question_id: str
    text: str
    difficulty: Difficulty
    topic: str
    source: QuestionSource


class EvaluationPayload(BaseModel):
    question_id: str
    score: float
    feedback: str
    confidence: Confidence
    fallback_flag: bool
    source: str
