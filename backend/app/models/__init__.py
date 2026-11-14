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
from app.models.rate_limit import RateLimitCounter
from app.models.refresh_token import RefreshToken
from app.models.user import GuardianLink, Role, User

__all__ = [
    "AuditLog",
    "Consent",
    "ExamBoard",
    "GuardianLink",
    "LearningObjective",
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
    "User",
]
