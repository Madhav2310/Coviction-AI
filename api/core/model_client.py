"""

Unified LLM abstraction layer.

All model calls go through here — never hardcode model strings in business logic.

Uses `instructor` for structured outputs everywhere.

Configured for Visa GenAI proxy with custom CA cert.

"""

import os

import httpx

import instructor

from openai import AsyncOpenAI

from typing import Type, TypeVar, Optional

from pydantic import BaseModel



from .config import Settings, get_settings



T = TypeVar("T", bound=BaseModel)





def _build_http_client(settings: Settings) -> httpx.AsyncClient | None:

    """Build httpx client with custom CA cert if configured."""

    ca_cert = settings.genai_ca_cert or os.getenv("GENAI_CA_CERT", os.getenv("SSL_CERT_FILE", ""))

    if ca_cert and os.path.isfile(ca_cert):

        return httpx.AsyncClient(verify=ca_cert, timeout=httpx.Timeout(60, connect=10))

    return None





class ModelClient:

    """

    Single interface for all LLM operations:

    - extract(): Structured output via instructor (Pydantic model in, Pydantic model out)

    - chat(): Raw text completion

    - chat_stream(): Streaming text completion (yields chunks)

    - embed(): Single text -> 1536-dim vector

    - embed_batch(): Multiple texts -> list of vectors

    - transcribe(): Audio -> text via Whisper

    - vision(): Image -> text via GPT-4o Vision

    """



    def __init__(self, settings: Settings):

        self.settings = settings

        kwargs: dict = {"api_key": settings.openai_api_key}

        if settings.openai_base_url:

            kwargs["base_url"] = settings.openai_base_url



        custom_client = _build_http_client(settings)

        if custom_client:

            kwargs["http_client"] = custom_client



        self._openai = AsyncOpenAI(**kwargs)

        self._instructor = instructor.from_openai(self._openai)



    async def extract(

        self,

        prompt: str,

        response_model: Type[T],

        model: Optional[str] = None,

        system: str = "",

        temperature: float = 0.0,

        max_retries: int = 2,

    ) -> T:

        """Structured extraction. Returns a typed Pydantic model."""

        messages = []

        if system:

            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})



        return await self._instructor.chat.completions.create(

            model=model or self.settings.default_strong_model,

            response_model=response_model,

            messages=messages,

            temperature=temperature,

            max_retries=max_retries,

        )



    async def chat(

        self,

        messages: list[dict],

        model: Optional[str] = None,

        temperature: float = 0.0,

    ) -> str:

        """Unstructured chat. Returns raw text."""

        response = await self._openai.chat.completions.create(

            model=model or self.settings.default_strong_model,

            messages=messages,

            temperature=temperature,

        )

        return response.choices[0].message.content or ""



    async def chat_stream(

        self,

        messages: list[dict],

        model: Optional[str] = None,

        temperature: float = 0.3,

    ):

        """Streaming chat. Yields content chunks as they arrive."""

        stream = await self._openai.chat.completions.create(

            model=model or self.settings.default_strong_model,

            messages=messages,

            temperature=temperature,

            stream=True,

        )

        async for chunk in stream:

            delta = chunk.choices[0].delta if chunk.choices else None

            if delta and delta.content:

                yield delta.content



    async def embed(self, text: str) -> list[float]:

        """Single text -> embedding vector."""

        response = await self._openai.embeddings.create(

            model=self.settings.default_embedding_model,

            input=text[:8000],

        )

        return response.data[0].embedding



    async def embed_batch(self, texts: list[str]) -> list[list[float]]:

        """Batch embed — up to 2048 inputs per call."""

        if not texts:

            return []

        response = await self._openai.embeddings.create(

            model=self.settings.default_embedding_model,

            input=[t[:8000] for t in texts],

        )

        return [r.embedding for r in sorted(response.data, key=lambda x: x.index)]



    async def transcribe(self, audio_file, language: str = "en") -> str:

        """Audio -> text via Whisper API."""

        response = await self._openai.audio.transcriptions.create(

            model=self.settings.whisper_model,

            file=audio_file,

            language=language,

            response_format="text",

        )

        return response



    async def vision(self, image_url: str, prompt: str, model: Optional[str] = None) -> str:

        """Image -> text via GPT-4o Vision."""

        response = await self._openai.chat.completions.create(

            model=model or self.settings.default_strong_model,

            messages=[{

                "role": "user",

                "content": [

                    {"type": "text", "text": prompt},

                    {"type": "image_url", "image_url": {"url": image_url}},

                ],

            }],

            max_tokens=2000,

        )

        return response.choices[0].message.content or ""





# Singleton

_model_client: Optional[ModelClient] = None





def get_model_client() -> ModelClient:

    global _model_client

    if _model_client is None:

        _model_client = ModelClient(get_settings())

    return _model_client
