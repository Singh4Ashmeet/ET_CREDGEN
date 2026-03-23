import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any

# Set up logging
logger = logging.getLogger(__name__)

class OpenRouterService:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model_name = "google/gemma-3-27b-it:free"
        
        if self.api_key:
            logger.info("OpenRouter Service initialized successfully.")
        else:
            logger.warning("No OPENROUTER_API_KEY found. Agent will likely fail.")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_response(
        self, 
        user_message: str, 
        system_prompt: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> Any:
        """
        Generates a response using OpenRouter with entity extraction.
        If stream=True, returns a generator.
        """
        if not self.api_key:
            return {
                "message": "AI Service not configured (Missing API Key).",
                "suggestions": [],
                "worker": "none",
                "intent": "error",
                "status": "error"
            }

        import time
        retries = 3
        delay = 1

        for attempt in range(retries):
            try:
                # Prepare headers
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:5000",
                    "X-Title": "CredGen AI Assistant"
                }
                
                # Streaming prompt adjustment
                if stream:
                    full_system_prompt = f"""{system_prompt}

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

Entity Extraction Rules:
- loan_amount: Extract numbers with lakh/lac/L (e.g., '5 lakhs' = 500000)
- tenure: Extract years/months (e.g., '3 years' = 36)
- income: Extract LPA/monthly
- pan: 10 chars
- aadhaar: 12 digits
- pincode: 6 digits
- employment_type: 'salaried' or 'self_employed'

User Query: {user_message}
"""
                else:
                    # Enhanced JSON instruction for entity extraction (Existing)
                    json_instruction = """
You must respond in strict JSON format. 
Your response should include natural language and extracted entities.

Output JSON schema:
{
  "response": "Your natural language response here (be conversational and helpful)",
  "suggestions": ["Short follow-up option 1", "Option 2", "Option 3"],
  "extracted_entities": {
    "loan_amount": null or number,
    "tenure": null or number (in months),
    "age": null or number,
    "income": null or number,
    "name": null or string,
    "employment_type": null or "salaried" or "self_employed" or "professional",
    "purpose": null or string,
    "pan": null or string (format: ABCDE1234F),
    "aadhaar": null or string (12 digits),
    "address": null or string,
    "pincode": null or string (6 digits)
  }
}
"""
                    full_system_prompt = f"{system_prompt}\n\n{json_instruction}\n\nUser Query: {user_message}"

                messages = [{"role": "system", "content": full_system_prompt}]
                if chat_history:
                    messages.extend(chat_history)
                messages.append({"role": "user", "content": user_message})

                data = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1000,
                    "stream": stream
                }

                if stream:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        data=json.dumps(data),
                        stream=True,
                        timeout=30
                    )
                    response.raise_for_status()

                    def stream_generator():
                        buffer = ""
                        json_started = False
                        json_buffer = ""
                        try:
                            for line in response.iter_lines():
                                if line:
                                    decoded_line = line.decode('utf-8')
                                    if decoded_line.startswith('data: '):
                                        content = decoded_line[6:]
                                        if content == '[DONE]':
                                            break
                                        try:
                                            chunk = json.loads(content)
                                            delta = chunk['choices'][0]['delta']
                                            if 'content' in delta:
                                                text = delta['content']
                                                
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
                                        except json.JSONDecodeError:
                                            continue
                            
                            # End of stream, parse JSON
                            if json_buffer:
                                try:
                                    parsed = json.loads(json_buffer)
                                    # Normalize format to match generate_response output
                                    yield {
                                        "type": "json", 
                                        "data": {
                                            "suggestions": parsed.get("suggestions", []),
                                            "extracted_entities": parsed.get("extracted_entities", {}),
                                            "status": "success"
                                        }
                                    }
                                except json.JSONDecodeError:
                                    yield {"type": "json", "data": {"status": "success", "suggestions": []}} # Fallback
                            else:
                                yield {"type": "json", "data": {"status": "success", "suggestions": []}}
                                
                        except Exception as e:
                             logger.error(f"Stream error: {e}")
                             yield {"type": "error", "message": str(e)}

                    return stream_generator()

                else:
                    # Non-streaming (original logic)
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        data=json.dumps(data),
                        timeout=30 
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result["choices"][0]["message"]["content"]
                        
                        # Clean the content (remove markdown code blocks if present)
                        clean_content = content.strip()
                        if "```json" in clean_content:
                            clean_content = clean_content.replace("```json", "").replace("```", "").strip()
                        elif "```" in clean_content:
                            clean_content = clean_content.replace("```", "").strip()
                        
                        # Try to parse the JSON content
                        try:
                            parsed = json.loads(clean_content)
                            
                            # Validate extracted entities (simplified for brevity, assume existing logic works)
                            extracted_entities = parsed.get("extracted_entities", {})
                            validated_entities = {}
                            # ... (validation logic similar to original) ...
                            # For brevity, I'll trust the parsed logic or copy it if needed. 
                            # But wait, I must output the full original validation logic or replace it correctly.
                            # I'll just reuse the variable `extracted_entities` assuming LLM did okay, 
                            # or strictly speaking I should include the validation loop. 
                            # Since I am replacing the method, I SHOULD include the validation loop.
                            
                            for key, value in extracted_entities.items():
                                if value is not None:
                                    if key == "loan_amount" and isinstance(value, (int, float)) and value > 0:
                                        validated_entities[key] = value
                                    elif key == "tenure" and isinstance(value, (int, float)) and value > 0:
                                        validated_entities[key] = int(value)
                                    elif key == "age" and isinstance(value, (int, float)) and 18 <= value <= 80:
                                        validated_entities[key] = int(value)
                                    elif key == "income" and isinstance(value, (int, float)) and value > 0:
                                        validated_entities[key] = value
                                    elif key in ["name", "address", "purpose"] and isinstance(value, str) and value.strip():
                                        validated_entities[key] = value.strip()
                                    elif key == "employment_type" and value in ["salaried", "self_employed", "professional"]:
                                        validated_entities[key] = value
                                    elif key == "pan" and isinstance(value, str) and len(value.strip()) == 10:
                                        validated_entities[key] = value.strip().upper()
                                    elif key == "aadhaar" and isinstance(value, str):
                                        clean_aadhaar = value.replace(" ", "").replace("-", "")
                                        if clean_aadhaar.isdigit() and len(clean_aadhaar) == 12:
                                            validated_entities[key] = clean_aadhaar
                                    elif key == "pincode" and isinstance(value, str) and value.isdigit() and len(value) == 6:
                                        validated_entities[key] = value

                            return {
                                "message": parsed.get("response", ""),
                                "suggestions": parsed.get("suggestions", []),
                                "extracted_entities": validated_entities,
                                "worker": "none",
                                "intent": "openrouter_response",
                                "status": "success"
                            }
                            
                        except json.JSONDecodeError as e:
                            logger.warning(f"OpenRouter returned invalid JSON: {e}")
                            return {
                                "message": clean_content,
                                "suggestions": [],
                                "extracted_entities": {},
                                "worker": "none",
                                "intent": "openrouter_response",
                                "status": "success_text_only"
                            }
                    else:
                        logger.error(f"OpenRouter API Error: {response.status_code} - {response.text}")
                        raise Exception(f"OpenRouter API Error: {response.status_code}") # Trigger retry

            except Exception as e:
                logger.error(f"OpenRouter Request Failed (Attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return {
                        "message": "AI service is currently unavailable.",
                        "intent": "error",
                        "worker": "none",
                        "status": "error"
                    }