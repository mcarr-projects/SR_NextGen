#For now, validates the grade result contract
MAX_FEEDBACK = 2000
def validate_grade_result(card, result):
    if not isinstance(result, dict):
        raise TypeError("grader result must be a dictionary")

    score = result.get("score")
    feedback = result.get("feedback")

    if score not in (1, 2, 3, 4, 5):
        raise ValueError("Grader score must be an integer from 1 through 5")
    if card["grading_type"] == "binary" and score not in (1, 5):
        raise ValueError("Binary grader score must be either 1 or 5")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("Grader feedback must be a non-empty string")
    if len(feedback) > MAX_FEEDBACK:
        raise ValueError("Feedback exceeds maximum acceptable length")
    
    return {"score": score, "feedback": feedback.strip()}