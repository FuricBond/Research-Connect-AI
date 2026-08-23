def extract_basic_topics(text: str) -> list[str]:
    words = [
        word.strip(".,:;!?()[]{}").lower()
        for word in text.split()
        if len(word.strip(".,:;!?()[]{}")) > 4
    ]
    return sorted(set(words))[:10]
