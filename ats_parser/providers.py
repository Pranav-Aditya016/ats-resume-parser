"""Provider contracts and factory. Add future providers here without changing the pipeline.

A provider receives the Markdown produced by `ats_parser.text_extraction` and returns a
canonical ATS record. It never touches the source document.
"""

from typing import Protocol


class ResumeProvider(Protocol):
    def parse(self, source_text: str) -> dict:
        """Return one canonical ATS record for a resume's extracted Markdown."""


def create_provider(name: str, model: str) -> ResumeProvider:
    if name.lower() == "gemini":
        from ats_parser.gemini_provider import GeminiProvider
        return GeminiProvider(model=model)
    if name.lower() == "mistral":
        from ats_parser.mistral_provider import MistralProvider
        return MistralProvider(model=model)
    raise ValueError(f"Unsupported provider: {name}. Available: gemini, mistral")
