"""Return abstract semantic hints without exposing You's internal records."""

from typing import Optional

from .. import _runtime as rt


async def dispatch(
    query: Optional[str] = "",
    aspect: Optional[str] = "",
    max_results: Optional[int] = 6,
) -> str:
    """Recall safe hints which the caller must paraphrase in the current reply."""

    if rt.mark_op:
        rt.mark_op("You")
    return await rt.you_service.recall(
        query="" if query is None else str(query),
        aspect="" if aspect is None else str(aspect),
        max_results=6 if max_results is None else max_results,
    )
