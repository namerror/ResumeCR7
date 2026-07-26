import tiktoken
from app.config import get_openai_api_key, settings
from openai import OpenAI
import logging

logger = logging.getLogger("embedding_client")

MAX_ROLE_TOKENS = 512
MAX_SKILL_TOKENS = 16

def get_tokenizer(model_name: str):
    """Get the appropriate tiktoken encoding for the specified model."""
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Fallback to a default encoding if model-specific one is not found
        return tiktoken.get_encoding("cl100k_base")

def truncate_texts(
    texts: list[str],
    max_tokens: int,
    model: str,
    *,
    text_kind: str | None = None,
) -> list[str]:
    """
    Truncate an array of strings to fit within max_tokens (per string) for the specified model.
    """
    tokenizer = get_tokenizer(model)
    truncated = []
    for text in texts:
        tokens = tokenizer.encode(text)
        if len(tokens) > max_tokens:
            truncated_text = tokenizer.decode(tokens[:max_tokens])
            truncated.append(truncated_text)
            extra = {
                "event": "text_truncated",
                "original_length": len(tokens),
                "truncated_length": max_tokens,
            }
            if text_kind is not None:
                extra["text_kind"] = text_kind
            logger.info("text_truncated", extra=extra)
        else:
            truncated.append(text)
    return truncated


def embed_role(role_text: str) -> list[float]:
    """
    Embed a single role text (job role + job description)
    """
    # Validation
    if role_text == "" or not isinstance(role_text, str):
        raise ValueError("Input role text cannot be an empty string or non-string")
    
    # Truncate to max tokens for role
    truncated_role = truncate_texts(
        [role_text],
        MAX_ROLE_TOKENS,
        settings.EMBEDDING_MODEL,
        text_kind="role",
    )[0]

    # Call OpenAI API to get embedding
    client = OpenAI(api_key=get_openai_api_key())
    embed_kwargs = {
        "input": truncated_role,
        "model": settings.EMBEDDING_MODEL,
    }
    if getattr(settings, "EMBEDDING_DIMENSIONS", None) is not None:
        embed_kwargs["dimensions"] = settings.EMBEDDING_DIMENSIONS
    response = client.embeddings.create(**embed_kwargs)

    embedding = response.data[0].embedding
    return embedding

def embed_skills(texts: list[str]) -> list[list[float]]:
    """
    Embed an array of strings (batch)
    """

    # Validation
    if not texts:
        raise ValueError("Input texts cannot be an empty list")
    if any((t=="" or not isinstance(t, str)) for t in texts):
        raise ValueError("Input texts cannot be empty strings or non-strings")
    
    # Truncate each skill text to max tokens for skills
    truncated_texts = truncate_texts(
        texts,
        MAX_SKILL_TOKENS,
        settings.EMBEDDING_MODEL,
        text_kind="skill",
    )

    # Call OpenAI API to get embeddings in batch
    client = OpenAI(api_key=get_openai_api_key())
    
    embed_kwargs = {
        "input": truncated_texts,
        "model": settings.EMBEDDING_MODEL,
    }
    if getattr(settings, "EMBEDDING_DIMENSIONS", None) is not None:
        embed_kwargs["dimensions"] = settings.EMBEDDING_DIMENSIONS

    response = client.embeddings.create(**embed_kwargs)

    embeddings = [item.embedding for item in response.data]

    if settings.DEV_MODE:
        logger.debug(f"Embedding batch request: {embed_kwargs}")
        logger.debug(f"Embedding batch response size: {len(response.data)}")
        logger.debug(f"Embedding usage: {response.usage}")

    return embeddings

    
