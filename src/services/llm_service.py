"""llm service: chatopenai instance using openrouter."""

from langchain_openai import ChatOpenAI

from src.core.config import settings


def get_llm() -> ChatOpenAI:
    """initialize and return a chatopenai instance configured for openrouter.
    
    returns:
        ChatOpenAI: configured llm instance using openrouter api.
    """
    return ChatOpenAI(
        model=settings.model_name,
        openai_api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/omnimind-backend",
            "X-Title": "OmniMind Backend",
        },
    )


# global llm instance
llm = get_llm()
