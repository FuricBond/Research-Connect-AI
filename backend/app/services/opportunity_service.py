from app.schemas.opportunity import Opportunity


def list_sample_opportunities() -> list[Opportunity]:
    return [
        Opportunity(
            id="sample-cfp-1",
            title="International Conference on AI Research",
            source="Sample CFP feed",
            opportunity_type="conference",
            deadline="2026-11-15",
            url="https://example.com/cfp/ai-research",
            summary="A placeholder opportunity used while the database layer is wired in.",
        )
    ]
