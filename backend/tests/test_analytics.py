from app.services.analytics import classify_topic


def test_classify_topic_error_codes():
    assert classify_topic("What does error code E-047 mean?") == "error codes"


def test_classify_topic_common_cases():
    assert classify_topic("What does a flashing red battery light mean?") == "warning lights"
    assert classify_topic("How do I change the transmission fluid?") == "transmission"
    assert classify_topic("My brake pedal feels soft") == "brakes"


def test_classify_topic_fallback_other():
    assert classify_topic("What's the best fertilizer for wheat?") == "other"
