def keyword_score(text: str, keywords: list[str]) -> int:
    normalized_text = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in normalized_text)
