import json
import os
import re
import time
from typing import List, Optional
import requests

class GeminiTranslator:
    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash-lite", min_interval: float = 2.5):
        self.api_key = api_key.strip()
        self.model_name = model_name.strip()
        self.min_interval = min_interval  # Enforces safe delay between requests
        self.last_request_time = 0.0

    def _call_api(self, prompt: str, system_instruction: str = "") -> str:
        """Calls Gemini API with proactive pacing and exponential backoff."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 8192
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    raise ValueError(f"Empty candidate in Gemini response: {data}")
                elif response.status_code in (429, 503):
                    backoff = 4 * (attempt + 1)
                    time.sleep(backoff)
                else:
                    error_msg = response.text
                    try:
                        err_json = response.json()
                        error_msg = err_json.get("error", {}).get("message", response.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Gemini API Error ({response.status_code}): {error_msg}")
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Network error communicating with Gemini API: {e}")
                time.sleep(2)
        raise RuntimeError("Failed to get response from Gemini API after multiple retries.")

    def _translate_chunk(self, items: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translates a small chunk (12-15 items) with high reliability and zero dropped items."""
        if not items:
            return []

        system_instruction = (
            f"You are a certified professional medical and document translator matching DeepL quality.\n"
            f"Translate the provided strings from {source_lang} to {target_lang}.\n"
            f"Strict Clinical & Document Rules:\n"
            f"1. Medical Accuracy:\n"
            f"   - 'nhu mô' = 'parénquima' (e.g. 'nhu mô tăng âm đều' -> 'parénquima con aumento homogéneo de la ecogenicidad'). Never omit 'parénquima'.\n"
            f"   - 'TM cửa' / 'Tĩnh mạch cửa' = 'vena porta' ('vena porta de calibre normal, permeable, sin trombosis').\n"
            f"   - 'Đường mật: Trong gan không giãn' = 'Vías biliares: Intrahepáticas no dilatadas'.\n"
            f"   - 'OMC' = 'colédoco' / 'conducto colédoco'.\n"
            f"   - 'không giun' = 'sin evidencia de parásitos'.\n"
            f"   - 'sỏi' = 'litiasis' / 'cálculo'.\n"
            f"   - 'gan nhiễm mỡ độ II' = 'esteatosis hepática grado II'.\n"
            f"   - 'Sỏi thận trái' = 'Litiasis renal izquierda'.\n"
            f"   - Preserve lab abbreviations (WBC, RBC, HGB, HCT, PLT, etc.).\n"
            f"2. Academic & Standardized Test Sections:\n"
            f"   - Translate all academic categories and test section titles: 'Craft and Structure' -> 'Estructura y destreza', 'Standard English Conventions' -> 'Convenciones del inglés estándar', 'Expression of Ideas' -> 'Expresión de ideas', 'Information and Ideas' -> 'Información e ideas'. Do not leave test category titles in English.\n"
            f"3. Strict Layout & Length-Parity Constraints:\n"
            f"   - Match the syllable count, brevity, and physical line compactness of the source string as closely as possible.\n"
            f"   - Avoid verbose paraphrasing or unnecessary filler words. Use concise, precise terms so translated lines fit into identical visual horizontal bounds without forcing downscaling or vertical overflow.\n"
            f"   - Preserve proper nouns, candidate names, numbers, codes, dates, and punctuation.\n"
            f"4. Output format:\n"
            f"   - Output ONLY a JSON array of strings with the exact same count ({len(items)} items).\n"
            f"   - Do NOT output markdown ticks or explanation."
        )

        prompt = (
            f"Translate each string in this JSON array to {target_lang}. "
            f"Return strictly a JSON array of {len(items)} strings in identical order:\n"
            f"{json.dumps(items, ensure_ascii=False)}"
        )

        raw = self._call_api(prompt, system_instruction).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        # Parse JSON
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            match = re.search(r"\[\s*[\"'].*[\"']\s*\]", raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except Exception:
                    pass

        if isinstance(parsed, list) and len(parsed) == len(items):
            return [str(x) for x in parsed]

        # Line-by-line fallback if JSON had minor syntax issue
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        if len(lines) == len(items):
            return lines

        # If length still mismatches, split chunk in half instead of spamming 1-by-1
        if len(items) > 1:
            mid = len(items) // 2
            left = self._translate_chunk(items[:mid], source_lang, target_lang)
            right = self._translate_chunk(items[mid:], source_lang, target_lang)
            return left + right

        # Single item fallback
        return [raw if raw else items[0]]

    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translates text units by safely chunking into groups of 15 to stay well under rate and token limits."""
        if not texts:
            return []

        valid_items = [(idx, t) for idx, t in enumerate(texts) if t and t.strip()]
        if not valid_items:
            return list(texts)

        items_to_translate = [t for _, t in valid_items]
        translated_results = []

        # Process in safe chunks of 15 items
        CHUNK_SIZE = 15
        for i in range(0, len(items_to_translate), CHUNK_SIZE):
            chunk = items_to_translate[i : i + CHUNK_SIZE]
            chunk_res = self._translate_chunk(chunk, source_lang, target_lang)
            translated_results.extend(chunk_res)

        # Restore exact indices
        result = list(texts)
        for (original_idx, _), translated_text in zip(valid_items, translated_results):
            result[original_idx] = translated_text

        return result
