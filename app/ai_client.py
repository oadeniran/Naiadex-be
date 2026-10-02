import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("uvicorn")

class VertexAIClient:
    def __init__(self):
        # Initialize the new Gen AI Client
        self.client = genai.Client(http_options=types.HttpOptions(api_version="v1"))

    def chat_completion(self, messages: list[dict], model: str = "gemini-3-flash-preview", **kwargs) -> str:
        try:
            formatted_contents = []

            for msg in messages:
                role = msg["role"]
                raw_content = msg["content"]
                parts = []

                if isinstance(raw_content, list):
                    # Handle Mixed Content (Text + Audio/Image Parts)
                    for item in raw_content:
                        if isinstance(item, str):
                            parts.append(types.Part.from_text(text=item))
                        elif hasattr(item, "mime_type"): 
                            # If it's already a types.Part (audio/image) created in orchestrator
                            parts.append(item)
                        else:
                            # Fallback for unknown types, try to cast to string
                            parts.append(types.Part.from_text(text=str(item)))
                else:
                    # Simple String
                    parts.append(types.Part.from_text(text=str(raw_content)))

                formatted_contents.append(types.Content(role=role, parts=parts))

            response = self.client.models.generate_content(
                model=model,
                contents=formatted_contents,
                config=types.GenerateContentConfig(
                    temperature=kwargs.get("temperature", 0.7),
                    response_mime_type=kwargs.get("response_mime_type", "text/plain")
                )
            )
            
            return response.text

        except Exception as err:
            logger.exception(f"Error in LLM Client: {err}")
            # Return a fallback JSON to prevent the Orchestrator from crashing entirely
            return {"error": "LLM generation failed."}
    
    def generate_content_with_audio(self, audio_bytes: bytes, prompt: str, mime_type: str = "audio/webm") -> str:
        """
        Sends audio bytes directly (Inline) to Vertex AI.
        Avoids 'files.upload' error and works perfectly for files < 20MB.
        """
        try:
            print(f"🎤 Sending {len(audio_bytes)} bytes inline to Gemini...")

            # 1. Create the Audio Part correctly
            # This wraps the raw bytes so Vertex knows it's media, not text.
            audio_part = types.Part.from_bytes(
                data=audio_bytes,
                mime_type=mime_type
            )

            # 2. Create the Text Part
            text_part = types.Part.from_text(text=prompt)

            # 3. Single "Super-Call"
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    types.Content(
                        role="user",
                        parts=[audio_part, text_part] # Order matters: Audio context first, then Prompt
                    )
                ]
            )
            
            return response.text

        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            raise e

    def generate_structured_from_image(
        self,
        image_bytes: bytes,
        prompt: str,
        mime_type: str = "image/jpeg",
        model: str = "gemini-3-flash-preview",
    ) -> str:
        """Send an image + prompt inline and ask for a JSON response.

        Returns the raw model text (expected to be a JSON string).
        """
        try:
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            text_part = types.Part.from_text(text=prompt)

            response = self.client.models.generate_content(
                model=model,
                contents=[
                    types.Content(role="user", parts=[image_part, text_part])
                ],
                config=types.GenerateContentConfig(
                    temperature=0.2,  # low = consistent classification
                    response_mime_type="application/json",
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise e

    def generate_structured_from_images(
        self,
        labeled_images: list[tuple[str, bytes, str]],
        prompt: str,
        model: str = "gemini-3-flash-preview",
    ) -> str:
        """Send multiple labeled images + a prompt, ask for JSON.

        labeled_images: list of (label, image_bytes, mime_type). Each image is
        preceded by a text part naming it, so the model knows which view is which.
        """
        try:
            parts = []
            for label, img_bytes, mime in labeled_images:
                parts.append(types.Part.from_text(text=f"[{label}]"))
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
            parts.append(types.Part.from_text(text=prompt))

            response = self.client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"Multi-image generation failed: {e}")
            raise e