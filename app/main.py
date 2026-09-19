"""Archive quote-alignment API."""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .align import align_quotes

app = FastAPI(title="Archive Quote Alignment API", version="1.0.0")


class AlignRequest(BaseModel):
    text: str = Field(..., description="Original source text")
    quotes: list[str] = Field(
        ..., description="Quotes to locate, matched in array order"
    )


class Span(BaseModel):
    start: int = Field(..., description="Start offset in the original text")
    end: int = Field(..., description="End offset (exclusive) in the original text")


class AlignResponse(BaseModel):
    results: list[Span | None] = Field(
        ..., description="One entry per quote; null when the quote is not located"
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/quotes/align", response_model=AlignResponse)
def align(request: AlignRequest) -> AlignResponse:
    spans = align_quotes(request.text, request.quotes)
    return AlignResponse(
        results=[
            Span(start=span[0], end=span[1]) if span is not None else None
            for span in spans
        ]
    )
