import httpx
import logging
from fastapi import HTTPException, status
from app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service to interact with the local Ollama LLM for text rewriting."""
    
    @classmethod
    async def get_available_models(cls) -> list[str]:
        """Queries Ollama for the list of available local models."""
        url = f"{settings.OLLAMA_URL.rstrip('/')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return [m["name"] for m in data.get("models", [])]
                else:
                    logger.warning(f"Ollama tags endpoint returned status {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to fetch models from Ollama: {e}")
        return []

    @classmethod
    async def rewrite_text(cls, text: str, tone: str = "academic") -> str:
        """
        Rewrites a sentence or paragraph to eliminate plagiarism,
        maintaining a specified tone.
        """
        if not text.strip():
            return ""

        # Fetch available models
        available = await cls.get_available_models()
        model_to_use = settings.OLLAMA_MODEL
        
        # Determine model to use
        if available:
            if model_to_use not in available:
                # Try prefix matching (e.g., matching "llama3" to "llama3:latest")
                candidates = [
                    m for m in available 
                    if m.startswith(model_to_use) or model_to_use.startswith(m.split(':')[0])
                ]
                if candidates:
                    model_to_use = candidates[0]
                    logger.info(f"Requested model '{settings.OLLAMA_MODEL}' not found. Using matched model '{model_to_use}'.")
                else:
                    model_to_use = available[0]
                    logger.info(f"Requested model '{settings.OLLAMA_MODEL}' not found. Falling back to first available model '{model_to_use}'.")
        else:
            logger.warning("No models found in Ollama tags query. Attempting call with default model configuration.")

        # Determine prompt instructions and generation options based on tone
        tone_instruction = "Maintain a strict academic and professional tone."
        temp = 0.5
        presence_penalty = 1.0
        frequency_penalty = 1.0
        
        if tone == "creative":
            tone_instruction = "Use a creative, engaging, and modern tone."
            temp = 0.85
            presence_penalty = 1.2
            frequency_penalty = 1.2
        elif tone == "standard":
            tone_instruction = "Use a clear, neutral, and highly readable tone."
            temp = 0.7
            presence_penalty = 1.1
            frequency_penalty = 1.1

        # Construct generation prompt
        prompt = (
            "You are an expert academic and technical editor. Rewrite the following sentence or text segment to eliminate plagiarism. "
            f"{tone_instruction} Preserve the original meaning, and ensure it is grammatically correct. "
            "Respond ONLY with the rewritten text, and do not include any introductory remarks, quotes, markdown formatting, explanations, or filler text.\n\n"
            f"Original text: {text}\n\n"
            "Rewritten text:"
        )
        
        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temp,
                "presence_penalty": presence_penalty,
                "frequency_penalty": frequency_penalty,
                "top_p": 0.9,
                "top_k": 40
            }
        }
        
        url = f"{settings.OLLAMA_URL.rstrip('/')}/api/generate"
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    rewritten = data.get("response", "").strip()
                    
                    # Clean up any surrounding quotes that the LLM might have outputted
                    if rewritten.startswith('"') and rewritten.endswith('"'):
                        rewritten = rewritten[1:-1].strip()
                    elif rewritten.startswith("'") and rewritten.endswith("'"):
                        rewritten = rewritten[1:-1].strip()
                    return rewritten
                else:
                    logger.error(f"Ollama returned error status: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Ollama service error: Received status {response.status_code}."
                    )
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama service at {settings.OLLAMA_URL}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ollama service is unavailable at {settings.OLLAMA_URL}. Ensure Ollama is running locally."
            )

    @classmethod
    async def extract_abstract(cls, text_excerpt: str) -> str:
        """
        Use the local Ollama LLM to extract the abstract from document text.

        This is the Tier-2 fallback when regex/heading heuristics fail to
        locate a clearly labeled abstract section.

        Parameters
        ----------
        text_excerpt : str
            The first ~2000 characters of the document text.

        Returns
        -------
        str
            The extracted abstract text, or empty string on failure.
        """
        if not text_excerpt or not text_excerpt.strip():
            return ""

        # Fetch available models
        available = await cls.get_available_models()
        model_to_use = settings.OLLAMA_MODEL

        if available:
            if model_to_use not in available:
                candidates = [
                    m for m in available
                    if m.startswith(model_to_use) or model_to_use.startswith(m.split(':')[0])
                ]
                if candidates:
                    model_to_use = candidates[0]
                elif available:
                    model_to_use = available[0]

        prompt = (
            "You are an expert academic document parser. "
            "Extract ONLY the abstract from the following academic paper text. "
            "Return ONLY the abstract text, nothing else. "
            "If no abstract is found, return exactly the text: NO_ABSTRACT_FOUND\n\n"
            f"Document text:\n{text_excerpt}\n\n"
            "Abstract:"
        )

        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "top_k": 20,
            },
        }

        url = f"{settings.OLLAMA_URL.rstrip('/')}/api/generate"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    result = data.get("response", "").strip()

                    # Clean up
                    if result.startswith('"') and result.endswith('"'):
                        result = result[1:-1].strip()
                    elif result.startswith("'") and result.endswith("'"):
                        result = result[1:-1].strip()

                    if "NO_ABSTRACT_FOUND" in result.upper():
                        return ""

                    return result
                else:
                    logger.warning(f"Ollama abstract extraction returned status {response.status_code}")
                    return ""
        except Exception as e:
            logger.warning(f"Failed to extract abstract via Ollama: {e}")
            return ""

