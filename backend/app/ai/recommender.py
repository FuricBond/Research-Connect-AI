from app.schemas.opportunity import Opportunity


def rank_opportunities(
    opportunities: list[Opportunity],
    research_interests: list[str],
) -> list[Opportunity]:
    if not research_interests:
        return opportunities

    keywords = {interest.lower() for interest in research_interests}

    def score(opportunity: Opportunity) -> int:
        haystack = f"{opportunity.title} {opportunity.summary or ''}".lower()
        return sum(1 for keyword in keywords if keyword in haystack)

    return sorted(opportunities, key=score, reverse=True)
