def create_placeholder_embedding(text: str, dimensions: int = 1536) -> list[float]:
    if not text:
        return [0.0] * dimensions

    seed = sum(ord(character) for character in text)
    return [float((seed + index) % 97) / 97.0 for index in range(dimensions)]
