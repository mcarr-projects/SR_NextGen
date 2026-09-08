from django.core.exceptions import ValidationError
from django.db import models
# Create your models here.

class Card(models.Model):
    class Length(models.TextChoices):
        SHORT = "short", "Short"
        MEDIUM = "medium", "Medium"
        LONG = "long", "Long"

    class GradingType(models.TextChoices):
        BINARY = "binary", "Correct / Incorrect"
        SCALED = "scaled", "Scaled"

    question = models.TextField()
    answer = models.TextField()
    length = models.CharField(
        max_length=6,
        choices=Length,
        default=Length.SHORT,
    )
    grading_type = models.CharField(
        max_length=6,
        choices=GradingType,
    )
    grading_criteria = models.TextField(blank=True)
    llm_grading_info = models.TextField(blank=True)
    is_deprecated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    length__in=["short", "medium", "long"]
                ),
                name="study_content_card_valid_length",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    grading_type__in=["binary", "scaled"]
                ),
                name="study_content_card_valid_grading_type",
            ),
        ]

    def clean(self):
        super().clean()

        for field_name in (
            "question",
            "answer",
            "grading_criteria",
            "llm_grading_info",
        ):
            value = getattr(self, field_name)

            if isinstance(value, str):
                setattr(self, field_name, value.strip())

        errors = {}

        if not self.question:
            errors["question"] = "Question cannot be empty."

        if not self.answer:
            errors["answer"] = "Answer cannot be empty."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.question