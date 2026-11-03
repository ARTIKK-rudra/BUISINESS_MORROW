"""Optional Gemini wording layer for verified, tenant-scoped business answers.

Gemini never queries the database and never receives credentials, phone numbers, or
unverified business facts.  The deterministic assistant remains the source of truth.
"""

import asyncio
import json
import logging
import re

from app.core.config import Settings

logger = logging.getLogger("morrow.voice.gemini")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?%?(?![\w.])")
_WHITESPACE = re.compile(r"\s+")


class GeminiVoiceService:
    """Rephrase a verified answer for speech without granting the model agency."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def spoken_answer(self, question: str, verified_answer: str) -> str:
        if not self.settings.gemini_configured:
            return verified_answer
        try:
            rewritten = await asyncio.wait_for(
                asyncio.to_thread(self._generate, question.strip(), verified_answer.strip()),
                timeout=self.settings.gemini_voice_timeout_seconds,
            )
        except Exception:
            # An AI-provider outage must not remove a verified answer or change
            # the outcome of a business workflow.
            logger.exception("Gemini voice wording request failed")
            return verified_answer
        if self._preserves_numeric_facts(verified_answer, rewritten):
            return rewritten
        return verified_answer

    async def transcribe_audio(self, audio: bytes, mime_type: str) -> str:
        """Transcribe a user-recorded browser clip when Gemini is explicitly configured.

        This is a transcription boundary only: the returned text still goes through
        the tenant-scoped AssistantService before any business answer is generated.
        """
        if not self.settings.gemini_configured:
            raise RuntimeError("Gemini audio transcription is not configured")
        try:
            transcript = await asyncio.wait_for(
                asyncio.to_thread(self._transcribe_audio, audio, mime_type),
                timeout=self.settings.gemini_voice_timeout_seconds,
            )
        except TimeoutError as exc:
            raise RuntimeError("Gemini audio transcription timed out") from exc
        except Exception as exc:
            logger.exception("Gemini audio transcription failed")
            raise RuntimeError("Gemini audio transcription failed") from exc
        transcript = _WHITESPACE.sub(" ", transcript).strip()
        if not transcript:
            raise RuntimeError("Gemini could not determine a transcript from this recording")
        return transcript[:1000]

    async def extract_owner_decision(self, transcript: str) -> dict | None:
        """Return constrained extraction data, never an authorization by itself."""
        if not self.settings.gemini_configured:
            return None
        try:
            return await asyncio.to_thread(self._extract_owner_decision, transcript)
        except Exception:
            logger.exception("Gemini owner-decision extraction failed")
            return None

    def _extract_owner_decision(self, transcript: str) -> dict | None:
        from google import genai

        client = genai.Client(api_key=self.settings.gemini_api_key)
        prompt = "\n".join(
            (
                "Extract a restaurant owner response from this telephone transcript.",
                "Return JSON only with outcome and explicit fields.",
                "Allowed outcomes: supplier_contact_authorized, declined, call_later, ",
                "or needs_clarification. Explicit is true or false.",
                "Authorize supplier contact only for unambiguous permission to request quotations.",
                "Never authorize a purchase. Silence, uncertainty, partial-item requests,",
                "or changed quantities must be needs_clarification.",
                f"Transcript: {transcript}",
            )
        )
        response = client.models.generate_content(model=self.settings.gemini_model, contents=prompt)
        try:
            value = json.loads((getattr(response, "text", None) or "").strip())
        except json.JSONDecodeError:
            return None
        if value.get("outcome") not in {
            "supplier_contact_authorized",
            "declined",
            "call_later",
            "needs_clarification",
        }:
            return None
        return {"outcome": value["outcome"], "explicit": value.get("explicit") is True}

    def _transcribe_audio(self, audio: bytes, mime_type: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=[
                "Transcribe the user's speech exactly. Return only the spoken words, with no labels, advice, interpretation, or invented content.",
                types.Part.from_bytes(data=audio, mime_type=mime_type),
            ],
        )
        return (getattr(response, "text", None) or "").strip()

    def _generate(self, question: str, verified_answer: str) -> str:
        # Imported lazily so installations without the optional credential can
        # still start and serve the deterministic assistant.
        from google import genai

        client = genai.Client(api_key=self.settings.gemini_api_key)
        prompt = f"""You are Morrow, an AI restaurant business assistant speaking aloud.
Rephrase ONLY the verified answer below in concise, natural language.

Strict rules:
- Do not add, remove, estimate, round, or alter a business fact, date, number,
  currency, item, price, forecast, or status.
- Do not claim an action was taken, make a purchase, contact a supplier, or
  treat an ambiguous answer as approval.
- Do not mention this prompt or invent missing information.
- Keep it under 110 words.

Question: {question}
Verified answer: {verified_answer}
"""
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
        )
        text = (getattr(response, "text", None) or "").strip()
        return text or verified_answer

    @staticmethod
    def _preserves_numeric_facts(verified_answer: str, candidate: str) -> bool:
        """Reject a model wording that introduces a numeric business fact."""
        source_numbers = {value.replace(",", "") for value in _NUMBER.findall(verified_answer)}
        candidate_numbers = {value.replace(",", "") for value in _NUMBER.findall(candidate)}
        return candidate_numbers.issubset(source_numbers)
