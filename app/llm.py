import logging
import time

from groq import APIConnectionError, Groq, RateLimitError

from app.config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger("agent.llm")

MAX_RETRIES = 3
BASE_DELAY_SECONDS = 5


class LLMError(Exception):
    """Raised when the LLM cannot be reached or returns an error."""


_client = None


def _get_client() -> Groq:
    global _client
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is missing. Add it to your .env file.")
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
    temperature: float = 0.3,
) -> str:
    """Send one prompt to the LLM and return its text reply.

    Rate limits and connection errors are retried with exponential backoff.
    If json_mode=True, the model is forced to return valid JSON
    (your prompt must also mention the word "JSON").
    """
    extra = {}
    if json_mode:
        extra["response_format"] = {"type": "json_object"}

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = _get_client().chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                **extra,
            )
            return response.choices[0].message.content
        except LLMError:
            raise
        except (RateLimitError, APIConnectionError) as exc:
            if attempt == MAX_RETRIES:
                raise LLMError(f"LLM unavailable after retries: {exc}") from exc
            delay = BASE_DELAY_SECONDS * (2**attempt)
            logger.warning(
                "LLM busy or unreachable (%s). Retrying in %ds (%d/%d)",
                type(exc).__name__, delay, attempt + 1, MAX_RETRIES,
            )
            time.sleep(delay)
        except Exception as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc