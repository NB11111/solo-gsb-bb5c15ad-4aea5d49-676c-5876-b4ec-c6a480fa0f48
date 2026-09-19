"""Archive quote-alignment API."""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .align import MAX_ALLOWED_EDITS, align_quotes, align_quotes_fuzzy

app = FastAPI(title="Archive Quote Alignment API", version="1.1.0")


class AlignRequest(BaseModel):
    text: str = Field(..., description="Original source text")
    quotes: list[str] = Field(
        ..., description="Quotes to locate, matched in array order"
    )


class FuzzyQuote(BaseModel):
    text: str = Field(..., description="Quote text to locate")
    max_edits: int = Field(
        ...,
        ge=0,
        le=MAX_ALLOWED_EDITS,
        description="Maximum allowed Levenshtein distance (0-2)",
    )


class FuzzyAlignRequest(BaseModel):
    text: str = Field(..., description="Original source text")
    quotes: list[FuzzyQuote] = Field(
        ..., description="Quotes to locate, matched in array order"
    )


class Span(BaseModel):
    start: int = Field(..., description="Start offset in the original text")
    end: int = Field(..., description="End offset (exclusive) in the original text")


class FuzzySpan(BaseModel):
    start: int = Field(..., description="Start offset in the original text")
    end: int = Field(..., description="End offset (exclusive) in the original text")
    edit_distance: int = Field(
        ..., description="Levenshtein distance between the quote and the span"
    )


class AlignResponse(BaseModel):
    results: list[Span | None] = Field(
        ..., description="One entry per quote; null when the quote is not located"
    )


class FuzzyAlignResponse(BaseModel):
    results: list[FuzzySpan | None] = Field(
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


@app.post("/quotes/align-fuzzy", response_model=FuzzyAlignResponse)
def align_fuzzy(request: FuzzyAlignRequest) -> FuzzyAlignResponse:
    spans = align_quotes_fuzzy(
        request.text, [(quote.text, quote.max_edits) for quote in request.quotes]
    )
    return FuzzyAlignResponse(
        results=[
            FuzzySpan(start=span[0], end=span[1], edit_distance=span[2])
            if span is not None
            else None
            for span in spans
        ]
    )
