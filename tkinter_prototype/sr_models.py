from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


CardLength = Literal["short", "medium", "long"]
GradingType = Literal["binary", "scaled"]
DeckType = Literal["personal", "standard"]

VALID_LENGTHS = {"short", "medium", "long"}
VALID_GRADING_TYPES = {"binary", "scaled"}
VALID_PERFORMANCE_SCORES = {1, 2, 3, 4, 5}
FAILED_AI_SCORE = -1
VALID_DECK_TYPES = {"personal", "standard"}

def validate_score(score: int, allow_ai_failure: bool = False) -> None:
    if type(score) is not int:
        raise TypeError("score must be an integer")

    if score in VALID_PERFORMANCE_SCORES:
        return

    if allow_ai_failure and score == FAILED_AI_SCORE:
        return

    if allow_ai_failure:
        raise ValueError("score must be one of: -1, 1, 2, 3, 4, 5")
    raise ValueError("score must be one of: 1, 2, 3, 4, 5")

def clean_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, (list, tuple)):
        raise TypeError("tags must be a list or tuple of strings")

    cleaned = []
    seen = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("each tag must be a string")

        clean_tag = " ".join(word.capitalize() for word in tag.strip().split())
        if clean_tag and clean_tag not in seen:
            cleaned.append(clean_tag)
            seen.add(clean_tag)

    return cleaned

def parse_db_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"invalid database datetime: {value!r}") from error
    elif not isinstance(value, datetime):
        raise TypeError("datetime value must be an ISO string or datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def clean_optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    return value.strip() or None

@dataclass
class Card:
    question: str
    answer: str
    grading_type: GradingType | None = None
    tags: list[str] = field(default_factory=list)
    length: CardLength = "short"
    grading_criteria: str | None = None
    llm_grading_info: str | None = None
    id: int | None = None
    is_deprecated: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.question, str):
            raise TypeError("question must be a string")
        if not isinstance(self.answer, str):
            raise TypeError("answer must be a string")
        if type(self.is_deprecated) is not bool:
            raise TypeError("is_deprecated must be a boolean")
        self.question = self.question.strip()
        self.answer = self.answer.strip()
        self.grading_criteria = clean_optional_text(self.grading_criteria, "grading_criteria")
        self.llm_grading_info = clean_optional_text(self.llm_grading_info, "llm_grading_info")
        self.tags = clean_tags(self.tags)

        if not self.question:
            raise ValueError("question cannot be empty")
        if not self.answer:
            raise ValueError("answer cannot be empty")
        if self.length not in VALID_LENGTHS:
            raise ValueError("length must be one of: short, medium, long")
        if self.grading_type is not None and self.grading_type not in VALID_GRADING_TYPES:
            raise ValueError("grading_type must be one of: binary, scaled, or None")
        if self.id is not None and (not isinstance(self.id, int) or self.id <= 0):
            raise ValueError("id must be a positive integer or None")

        if self.created_at is not None:
            parse_db_datetime(self.created_at)
        if self.updated_at is not None:
            parse_db_datetime(self.updated_at)

    def validate_for_creation(self) -> None:
        if self.grading_type is None:
            raise ValueError("grading_type must be selected before creating a card")

@dataclass
class UserCardState:
    user_id: int
    card_id: int
    next_review_time: str
    last_reviewed_at: str | None = None
    last_performance: int | None = None
    current_interval: int = 1
    repetitions: int = 0
    #ef and lapse_count are from a previous more complex scheduling plan, currently unused
    ef: float = 2.5
    lapse_count: int = 0
    recent_scores: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recent_scores = list(self.recent_scores)

        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not isinstance(self.card_id, int) or self.card_id <= 0:
            raise ValueError("card_id must be a positive integer")
        if not isinstance(self.current_interval, int) or self.current_interval <= 0:
            raise ValueError("current_interval must be a positive integer")
        if not isinstance(self.repetitions, int) or self.repetitions < 0:
            raise ValueError("repetitions must be a non-negative integer")
        if not isinstance(self.ef, (int, float)) or self.ef <= 0:
            raise ValueError("ef must be positive")
        if not isinstance(self.lapse_count, int) or self.lapse_count < 0:
            raise ValueError("lapse_count must be a non-negative integer")
        if self.last_performance is not None:
            validate_score(self.last_performance)
        for score in self.recent_scores:
            validate_score(score)

        parse_db_datetime(self.next_review_time)
        if self.last_reviewed_at is not None:
            parse_db_datetime(self.last_reviewed_at)

    def is_due(self, at: str | datetime | None = None) -> bool:
        comparison_time = datetime.now(timezone.utc) if at is None else parse_db_datetime(at)
        return parse_db_datetime(self.next_review_time) <= comparison_time


@dataclass
class ReviewItem:
    card: Card
    state: UserCardState

    def __post_init__(self) -> None:
        if not isinstance(self.card, Card):
            raise TypeError("card must be a Card")
        if not isinstance(self.state, UserCardState):
            raise TypeError("state must be a UserCardState")
        if self.card.id is None:
            raise ValueError("ReviewCard requires a saved Card with an id")
        if self.card.id != self.state.card_id:
            raise ValueError("Card.id and UserCardState.card_id must match")

    @property
    def id(self) -> int:
        return self.state.card_id

    @property
    def user_id(self) -> int:
        return self.state.user_id

    def is_due(self, at: str | datetime | None = None) -> bool:
        return self.state.is_due(at)

@dataclass
class Deck:
    name: str
    owner_user_id: int
    deck_type: DeckType = "personal"
    source_deck_id: int | None = None
    is_published: bool = False
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not isinstance(self.owner_user_id, int) or self.owner_user_id <= 0:
            raise ValueError("owner_user_id must be a positive integer")
        if self.deck_type not in VALID_DECK_TYPES:
            raise ValueError("deck_type must be one of: personal, standard")
        if self.source_deck_id is not None and (
            not isinstance(self.source_deck_id, int) or self.source_deck_id <= 0
        ):
            raise ValueError("source_deck_id must be a positive integer or None")
        if type(self.is_published) is not bool:
            raise TypeError("is_published must be a boolean")
        if self.id is not None and (not isinstance(self.id, int) or self.id <= 0):
            raise ValueError("id must be a positive integer or None")

        self.name = self.name.strip()

        if not self.name:
            raise ValueError("name cannot be empty")
        if self.deck_type == "personal" and self.is_published:
            raise ValueError("personal decks cannot be published")
        if self.deck_type == "standard" and self.source_deck_id is not None:
            raise ValueError("standard decks cannot have a source deck")

        if self.created_at is not None:
            parse_db_datetime(self.created_at)
        if self.updated_at is not None:
            parse_db_datetime(self.updated_at)


    