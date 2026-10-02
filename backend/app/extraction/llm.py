# Thin wrapper around the Anthropic client for schema-constrained
# extraction. One method: `extract(system, text, schema)` -> a validated
# instance of `schema`.
#
# Model selection: defaults to claude-opus-5. Override per-deployment
# with the TENK_EXTRACTION_MODEL env var (e.g. claude-sonnet-5 to cut
# cost) - no code change needed.
#
# Error policy: infrastructure failures (auth, network, rate limits after
# the SDK's own retries) propagate as the SDK's typed exceptions so the
# caller fails loudly. Only content-level problems - the model refused,
# or returned nothing parseable - are raised as ExtractionError, which
# the pipeline catches per-section so one bad section doesn't sink the
# whole filing.

import os
from typing import TypeVar

from pydantic import BaseModel

DEFAULT_EXTRACTION_MODEL = "claude-opus-5"
MAX_TOKENS = 16000

T = TypeVar("T", bound=BaseModel)


class ExtractionError(RuntimeError):
    """The section was sent to the model but no usable result came back."""


class ExtractionRefused(ExtractionError):
    """The model declined to process the section (safety refusal)."""


def extraction_model() -> str:
    return os.getenv("TENK_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL)


class LLMClient:
    def __init__(
        self,
        client=None,
        model: str | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self._client = client
        self.model = model or extraction_model()
        self.max_tokens = max_tokens

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def extract(self, *, system: str, text: str, schema: type[T]) -> T:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": text}],
            output_format=schema,
        )

        if response.stop_reason == "refusal":
            detail = getattr(response.stop_details, "explanation", None)
            raise ExtractionRefused(detail or "model refused the request")

        parsed = response.parsed_output
        if parsed is None:
            raise ExtractionError(
                f"no parseable {schema.__name__} in response "
                f"(stop_reason={response.stop_reason})"
            )
        return parsed
