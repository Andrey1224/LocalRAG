"""Sample unit test to ensure pytest hook works."""


def test_sample() -> None:
    """Basic test to verify testing infrastructure."""
    assert 1 + 1 == 2


def test_string_operations() -> None:
    """Test string operations."""
    text = "LocalRAG"
    assert text.lower() == "localrag"
    assert len(text) == 8
