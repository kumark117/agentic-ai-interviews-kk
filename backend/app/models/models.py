import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ExperienceLevel(str, enum.Enum):
    junior = "junior"
    mid = "mid"
    senior = "senior"


class InterviewType(str, enum.Enum):
    frontend_ai_fullstack = "frontend_ai_fullstack"
    backend_systems = "backend_systems"
    fullstack_general = "fullstack_general"
    data_ml = "data_ml"
    devops = "devops"


class SessionStatus(str, enum.Enum):
    INIT = "INIT"
    QUESTIONING = "QUESTIONING"
    EVALUATING = "EVALUATING"
    DECIDING = "DECIDING"
    END = "END"


class EndReason(str, enum.Enum):
    candidate_completed = "candidate_completed"
    max_questions_reached = "max_questions_reached"
    inactive_timeout = "inactive_timeout"
    manual = "manual"


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Confidence(str, enum.Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class EvaluationSource(str, enum.Enum):
    llm = "llm"
    fallback_timeout = "fallback_timeout"


class QuestionSource(str, enum.Enum):
    interviewer_agent = "interviewer_agent"
    fallback_bank = "fallback_bank"


class EventType(str, enum.Enum):
    thinking = "thinking"
    evaluation_started = "evaluation_started"
    evaluation_completed = "evaluation_completed"
    question_generated = "question_generated"
    interview_completed = "interview_completed"
    error = "error"
    queue_delay = "queue_delay"


class Session(Base):
    __tablename__ = "sessions"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_token: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(256), nullable=False)
    experience_level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(Enum(InterviewType), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), nullable=False)
    end_reason: Mapped[EndReason | None] = mapped_column(Enum(EndReason), nullable=True)
    current_question_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_difficulty: Mapped[Difficulty] = mapped_column(Enum(Difficulty), nullable=False)
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    questions_asked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Question(Base):
    __tablename__ = "questions"
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(Enum(Difficulty), nullable=False)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[QuestionSource] = mapped_column(Enum(QuestionSource), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_answers_session_question"),)
    answer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.question_id"), nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Evaluation(Base):
    __tablename__ = "evaluations"
    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.question_id"), nullable=False)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.answer_id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), nullable=False)
    fallback_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[EvaluationSource] = mapped_column(Enum(EvaluationSource), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("session_id", "event_seq", name="uq_events_session_event_seq"),)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeaknessMap(Base):
    __tablename__ = "weakness_map"
    __table_args__ = (UniqueConstraint("session_id", "topic", name="uq_weakness_session_topic"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    low_score_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    follow_up_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_score: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionEventSequence(Base):
    __tablename__ = "session_event_sequences"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), primary_key=True)
    last_event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
