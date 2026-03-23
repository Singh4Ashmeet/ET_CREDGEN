import os
import logging
import json
import google.generativeai as genai
from typing import Dict, List, Optional, Any

# Set up logging
logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = None
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash') # using a fast model
                logger.info("Gemini Service initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
        else:
            logger.warning("No GEMINI_API_KEY found. Gemini Service will not work.")

    def is_available(self) -> bool:
        return self.model is not None

    def generate_response(
        self, 
        user_message: str, 
        system_prompt: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> Any:
        """
        Generates a response from Gemini.
        If stream=True, returns a generator yielding {"type": "token", "content": "..."} 
        and finally {"type": "json", "data": {...}}.
        """
        if not self.model:
            return {
                "message": "Gemini is not configured.",
                "worker": "none",
                "intent": "error",
                "terminate": False
            }

        retries = 3
        delay = 1

        import time
        for attempt in range(retries):
            try:
                # Construct prompt
                if stream:
                    prompt = f"""{system_prompt}

You must respond in two parts:
1. First, provide a natural language response to the user.
2. Then, on a new line, write [JSON] followed immediately by the JSON object containing suggestions and entities.

Output format:
Your helpful response text here...
[JSON]
{{
  "suggestions": ["Option 1", "Option 2"],
  "extracted_entities": {{...}}
}}

User Query: {user_message}
"""
                else:
                    prompt = f"""{system_prompt}

You must respond in strict JSON format.
Output schema:
{{
  "response": "Your natural language response here (can include markdown)",
  "suggestions": ["Short follow-up option 1", "Short follow-up option 2", "Option 3"]
}}

User Query: {user_message}
"""

                if stream:
                    response = self.model.generate_content(
                        contents=[{"role": "user", "parts": [{"text": prompt}]}],
                        generation_config=genai.types.GenerationConfig(
                            candidate_count=1,
                            max_output_tokens=1000,
                            temperature=0.7
                        ),
                        stream=True
                    )
                    
                    def stream_generator():
                        buffer = ""
                        json_started = False
                        json_buffer = ""
                        
                        try:
                            for chunk in response:
                                text = chunk.text
                                if '[JSON]' in text:
                                    parts = text.split('[JSON]')
                                    if parts[0]:
                                        yield {"type": "token", "content": parts[0]}
                                    json_started = True
                                    json_buffer += parts[1]
                                elif json_started:
                                    json_buffer += text
                                else:
                                    yield {"type": "token", "content": text}
                                    buffer += text
                            
                            # Parse JSON at the end
                            import json
                            try:
                                if json_buffer:
                                    data = json.loads(json_buffer)
                                    # Normalize keys
                                    if "response" not in data:
                                        data["response"] = buffer.strip() # Should be unused if logic is correct
                                    data["status"] = "success"
                                    yield {"type": "json", "data": data}
                                else:
                                    # Fallback if no JSON found
                                    yield {"type": "json", "data": {"status": "success", "suggestions": []}}
                            except json.JSONDecodeError:
                                logger.error("Failed to parse JSON from stream")
                                yield {"type": "json", "data": {"status": "error", "message": "Failed to parse AI response"}}

                        except Exception as e:
                            logger.error(f"Stream error: {e}")
                            yield {"type": "error", "message": str(e)}

                    return stream_generator()

                else:
                    # Non-streaming (original logic)
                    response = self.model.generate_content(
                        contents=[{"role": "user", "parts": [{"text": prompt}]}],
                        generation_config=genai.types.GenerationConfig(
                            candidate_count=1,
                            max_output_tokens=500,
                            temperature=0.7,
                            response_mime_type="application/json"
                        )
                    )
                    
                    import json
                    try:
                        data = json.loads(response.text)
                        return {
                            "message": data.get("response", ""),
                            "suggestions": data.get("suggestions", []),
                            "worker": "none",
                            "intent": "gemini_response",
                            "status": "success"
                        }
                    except json.JSONDecodeError:
                        logger.warning("Gemini failed to return valid JSON, falling back to raw text.")
                        return {
                            "message": response.text,
                            "suggestions": [],
                            "worker": "none",
                            "intent": "gemini_response",
                            "status": "success_text_only"
                        }

            except Exception as e:
                logger.error(f"Gemini generation error (Attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return {
                        "message": "I'm having trouble connecting to my AI services right now.",
                        "worker": "none",
                        "intent": "error",
                        "error": str(e),
                        "status": "fallback"
                    }
