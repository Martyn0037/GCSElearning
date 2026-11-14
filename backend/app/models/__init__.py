# backend/app/models/__init__.py
"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.audit_log import AuditLog
from app.models.consent import Consent
from app.models.curriculum import (
    ExamBoard,
    LearningObjective,
    SetTextOption,
    Specification,
    Subject,
    Subtopic,
    Tier,
    Topic,
)
from app.models.enrolment import StudentSetText, StudentSubject, StudentTopicSetting
from app.models.ops import AiUsage, Job, JobStatus, UsageStatus
from app.models.question import (
    Difficulty,
    ExplanationStatus,
    Hint,
    Mistake,
    ObjectiveProgress,
    PracticeItem,
    Question,
    QuestionFlag,
    QuestionStatus,
    QuestionType,
)
from app.models.rate_limit import RateLimitCounter
from app.models.refresh_token import RefreshToken
from app.models.user import GuardianLink, Role, User

__all__ = [
    "AiUsage",
    "AuditLog",
    "Consent",
    "Difficulty",
    "ExamBoard",
    "ExplanationStatus",
    "GuardianLink",
    "Hint",
    "Job",
    "JobStatus",
    "LearningObjective",
    "Mistake",
    "ObjectiveProgress",
    "PracticeItem",
    "Question",
    "QuestionFlag",
    "QuestionStatus",
    "QuestionType",
    "RateLimitCounter",
    "RefreshToken",
    "Role",
    "SetTextOption",
    "Specification",
    "StudentSetText",
    "StudentSubject",
    "StudentTopicSetting",
    "Subject",
    "Subtopic",
    "Tier",
    "Topic",
    "UsageStatus",
    "User",
]
