"""Extraction service interface (FR-3). The provider is chosen by EXTRACTION_PROVIDER;
switching provider needs no code change elsewhere (Strategy pattern)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import MockExtraction
from app.settings import settings


@dataclass
class ExtractionResult:
    doc_type: str
    doc_type_confidence: float
    fields: list[tuple[str, str, float]] = field(default_factory=list)   # (name, value, confidence)
    provider: str = ""

    def as_long_format(self, doc_id: str) -> list[dict]:
        rows = [{"doc_id": doc_id, "field_name": "doc_type", "value": self.doc_type,
                 "confidence": round(self.doc_type_confidence, 2)}]
        rows += [{"doc_id": doc_id, "field_name": n, "value": v, "confidence": round(c, 2)} for n, v, c in self.fields]
        return rows


class ExtractionProvider(ABC):
    name = "base"

    @abstractmethod
    def extract(self, doc_ref: str, text: str) -> ExtractionResult:
        """Classify the document and extract its fields with confidence."""


class MockProvider(ExtractionProvider):
    """Looks up the supplied extraction_mock rows by doc_id; unknown document -> OTHER, 0.00."""
    name = "mock"

    def __init__(self, db: Session):
        self.db = db

    def extract(self, doc_ref: str, text: str) -> ExtractionResult:
        rows = self.db.scalars(select(MockExtraction).where(MockExtraction.doc_id == doc_ref)
                               .order_by(MockExtraction.id)).all()
        result = ExtractionResult("OTHER", 0.0, provider=self.name)
        for r in rows:
            if r.field_name == "doc_type":
                result.doc_type, result.doc_type_confidence = r.value, r.confidence
            else:
                result.fields.append((r.field_name, r.value, r.confidence))
        return result


PROVIDERS: dict[str, type[ExtractionProvider]] = {"mock": MockProvider}
# An AI/OCR provider would be added here, e.g. PROVIDERS["ai"] = AiProvider


def get_provider(db: Session) -> ExtractionProvider:
    cls = PROVIDERS.get(settings.extraction_provider)
    if cls is None:
        raise ApiError(503, "EXTRACTION_PROVIDER_UNAVAILABLE",
                       f"Extraction provider '{settings.extraction_provider}' is not available")
    return cls(db)
