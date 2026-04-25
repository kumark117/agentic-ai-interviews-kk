"""init v5 schema

Revision ID: 20260425_0001
Revises:
Create Date: 2026-04-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260425_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("sessions", sa.Column("session_id", sa.String(64), primary_key=True), sa.Column("session_token", sa.String(128), nullable=False), sa.Column("candidate_id", sa.String(128), nullable=False), sa.Column("candidate_name", sa.String(256), nullable=False), sa.Column("role", sa.String(256), nullable=False), sa.Column("experience_level", sa.Enum("junior", "mid", "senior", name="experiencelevel"), nullable=False), sa.Column("interview_type", sa.Enum("frontend_ai_fullstack", "backend_systems", "fullstack_general", "data_ml", "devops", name="interviewtype"), nullable=False), sa.Column("status", sa.Enum("INIT", "QUESTIONING", "EVALUATING", "DECIDING", "END", name="sessionstatus"), nullable=False), sa.Column("end_reason", sa.Enum("candidate_completed", "max_questions_reached", "inactive_timeout", "manual", name="endreason"), nullable=True), sa.Column("current_question_id", sa.String(64)), sa.Column("current_difficulty", sa.Enum("easy", "medium", "hard", name="difficulty"), nullable=False), sa.Column("max_questions", sa.Integer(), nullable=False), sa.Column("questions_asked", sa.Integer(), nullable=False, server_default="0"), sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("session_event_sequences", sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.session_id"), primary_key=True), sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("questions", sa.Column("question_id", sa.String(64), primary_key=True), sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.session_id"), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("difficulty", sa.Enum("easy", "medium", "hard", name="difficulty"), nullable=False), sa.Column("topic", sa.String(128), nullable=False), sa.Column("source", sa.Enum("interviewer_agent", "fallback_bank", name="questionsource"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_questions_session_id", "questions", ["session_id"], unique=False)
    op.create_table("answers", sa.Column("answer_id", sa.String(64), primary_key=True), sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.session_id"), nullable=False), sa.Column("question_id", sa.String(64), sa.ForeignKey("questions.question_id"), nullable=False), sa.Column("answer_text", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "question_id", name="uq_answers_session_question"))
    op.create_index("ix_answers_session_id", "answers", ["session_id"], unique=False)
    op.create_table("evaluations", sa.Column("evaluation_id", sa.String(64), primary_key=True), sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.session_id"), nullable=False), sa.Column("question_id", sa.String(64), sa.ForeignKey("questions.question_id"), nullable=False), sa.Column("answer_id", sa.String(64), sa.ForeignKey("answers.answer_id"), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("feedback", sa.Text(), nullable=False), sa.Column("confidence", sa.Enum("HIGH", "LOW", name="confidence"), nullable=False), sa.Column("fallback_flag", sa.Boolean(), nullable=False), sa.Column("source", sa.Enum("llm", "fallback_timeout", name="evaluationsource"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_evaluations_session_id", "evaluations", ["session_id"], unique=False)
    op.create_table("events", sa.Column("event_id", sa.String(64), primary_key=True), sa.Column("event_seq", sa.Integer(), nullable=False), sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.session_id"), nullable=False), sa.Column("event_type", sa.Enum("thinking", "evaluation_started", "evaluation_completed", "question_generated", "interview_completed", "error", "queue_delay", name="eventtype"), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "event_seq", name="uq_events_session_event_seq"))
    op.create_index("ix_events_session_id", "events", ["session_id"], unique=False)
    op.create_table("weakness_map", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.session_id"), nullable=False), sa.Column("topic", sa.String(128), nullable=False), sa.Column("low_score_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("follow_up_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("last_score", sa.Float(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "topic", name="uq_weakness_session_topic"))
    op.create_index("ix_weakness_map_session_id", "weakness_map", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_weakness_map_session_id", table_name="weakness_map")
    op.drop_table("weakness_map")
    op.drop_index("ix_events_session_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_evaluations_session_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_answers_session_id", table_name="answers")
    op.drop_table("answers")
    op.drop_index("ix_questions_session_id", table_name="questions")
    op.drop_table("questions")
    op.drop_table("session_event_sequences")
    op.drop_table("sessions")
