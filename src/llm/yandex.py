"""YandexGPT client for task parsing."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import requests

YANDEX_NATIVE_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YANDEX_OPENAI_API_URL = "https://llm.api.cloud.yandex.net/v1/chat/completions"

TASK_PARSE_SCHEMA = {
    "name": "task_parse_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "due_date": {"type": ["string", "null"]},
            "repeat_flag": {"type": ["string", "null"]},
            "is_all_day": {"type": "boolean"},
            "priority": {"type": "integer", "enum": [0, 1, 3, 5]}
        },
        "required": ["title", "due_date", "repeat_flag", "is_all_day", "priority"],
        "additionalProperties": False
    }
}


@dataclass
class TaskParseResult:
    """Parsed task from natural language input."""
    title: str
    due_date: Optional[str] = None
    repeat_flag: Optional[str] = None
    is_all_day: bool = False
    priority: int = 0

    def to_api_dict(self) -> dict:
        """Convert to TickTick API format."""
        data = {"title": self.title}
        if self.due_date:
            data["dueDate"] = self.due_date
            data["isAllDay"] = self.is_all_day
        if self.repeat_flag:
            data["repeatFlag"] = self.repeat_flag
        if self.priority:
            data["priority"] = self.priority
        return data


def _get_example_dates(current_date: str, current_weekday: str) -> dict:
    """Calculate real dates for prompt examples."""
    base = datetime.strptime(current_date, "%Y-%m-%d")
    tomorrow = (base + timedelta(days=1)).strftime("%Y-%m-%d")

    weekdays = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6}
    current_wd = weekdays[current_weekday]

    # Next Wednesday (2 = Wednesday)
    days_until_wed = (2 - current_wd) % 7 or 7
    next_wed = (base + timedelta(days=days_until_wed)).strftime("%Y-%m-%d")

    # Next Monday (0 = Monday)
    days_until_mon = (0 - current_wd) % 7 or 7
    next_mon = (base + timedelta(days=days_until_mon)).strftime("%Y-%m-%d")

    return {
        "tomorrow": tomorrow,
        "next_wednesday": next_wed,
        "next_monday": next_mon
    }


def _build_system_prompt(current_date: str, current_weekday: str, timezone: str) -> str:
    """Build system prompt for task parsing."""
    dates = _get_example_dates(current_date, current_weekday)
    return f"""You are a task parser for a todo app. Extract structured task data from natural language input in Russian.

CURRENT CONTEXT:
- Today's date: {current_date}
- Today's weekday: {current_weekday}
- Timezone: {timezone}

RULES:
1. Extract a clear, actionable task title (imperative form in Russian):
   - "Мне надо заказать шторы" -> "Заказать шторы"
   - "хочу бегать каждую среду" -> "Пробежка"
   - "купить молоко завтра" -> "Купить молоко"
   - "надо позвонить маме" -> "Позвонить маме"

2. Parse date/time to ISO 8601 format (yyyy-MM-ddTHH:mm:ss+0000):
   - "сегодня" = current day
   - "завтра" = next day
   - "послезавтра" = day after tomorrow
   - "в 19" / "до 19" / "к 19" = 19:00:00
   - "в обед" = 13:00:00
   - "утром" = 09:00:00
   - "вечером" = 18:00:00
   - "ночью" = 23:00:00
   - "через час" = current time + 1 hour
   - "через неделю" = current date + 7 days
   - "в понедельник" = next Monday
   - If time not specified but date is -> is_all_day = true, time = 00:00:00
   - If neither date nor time specified -> due_date = null

3. Parse repeat patterns to RRULE format:
   - "каждый день" / "ежедневно" -> RRULE:FREQ=DAILY
   - "каждую неделю" / "еженедельно" -> RRULE:FREQ=WEEKLY
   - "каждый месяц" / "ежемесячно" -> RRULE:FREQ=MONTHLY
   - "каждый год" / "ежегодно" -> RRULE:FREQ=YEARLY
   - "каждую среду" -> RRULE:FREQ=WEEKLY;BYDAY=WE
   - "каждый понедельник" -> RRULE:FREQ=WEEKLY;BYDAY=MO
   - "каждые выходные" -> RRULE:FREQ=WEEKLY;BYDAY=SA,SU
   - "каждый рабочий день" / "по будням" -> RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
   - "каждый понедельник и среду" -> RRULE:FREQ=WEEKLY;BYDAY=MO,WE

   Day codes: MO=Monday, TU=Tuesday, WE=Wednesday, TH=Thursday, FR=Friday, SA=Saturday, SU=Sunday

   For recurring tasks, set due_date to the FIRST occurrence.

4. Priority extraction:
   - "срочно" / "важно" / "ASAP" / "очень важно" -> priority = 5
   - "не срочно" / "когда-нибудь" -> priority = 1
   - Default -> priority = 0

RESPONSE FORMAT:
Return ONLY valid JSON without any markdown formatting or explanation.

EXAMPLES (use actual dates based on current context above):

Input: "Мне надо заказать шторы завтра до 19"
Output: {{"title": "Заказать шторы", "due_date": "{dates['tomorrow']}T19:00:00+0000", "repeat_flag": null, "is_all_day": false, "priority": 0}}

Input: "бегать каждую среду в обед"
Output: {{"title": "Пробежка", "due_date": "{dates['next_wednesday']}T13:00:00+0000", "repeat_flag": "RRULE:FREQ=WEEKLY;BYDAY=WE", "is_all_day": false, "priority": 0}}

Input: "срочно позвонить маме"
Output: {{"title": "Позвонить маме", "due_date": null, "repeat_flag": null, "is_all_day": true, "priority": 5}}

Input: "пить витамины каждое утро"
Output: {{"title": "Выпить витамины", "due_date": "{dates['tomorrow']}T09:00:00+0000", "repeat_flag": "RRULE:FREQ=DAILY", "is_all_day": false, "priority": 0}}

Input: "купить молоко"
Output: {{"title": "Купить молоко", "due_date": null, "repeat_flag": null, "is_all_day": true, "priority": 0}}

Input: "встреча с клиентом в понедельник в 10"
Output: {{"title": "Встреча с клиентом", "due_date": "{dates['next_monday']}T10:00:00+0000", "repeat_flag": null, "is_all_day": false, "priority": 0}}

IMPORTANT: Calculate actual dates based on today's date and weekday from CURRENT CONTEXT. For recurring tasks with weekday (e.g. "каждую среду"), set due_date to the NEXT occurrence of that weekday."""


def _build_simple_system_prompt(current_date: str, current_weekday: str, timezone: str) -> str:
    """Build simplified system prompt for structured output API (schema defines format)."""
    return f"""You are a task parser for a todo app. Parse Russian natural language input into structured task data.

CURRENT CONTEXT:
- Today: {current_date} ({current_weekday})
- Timezone: {timezone}

PARSING RULES:

TITLE: Extract clear, actionable task in imperative form:
- "Мне надо заказать шторы" → "Заказать шторы"
- "хочу бегать" → "Пробежка"

DATE/TIME (ISO 8601: yyyy-MM-ddTHH:mm:ss+0000):
- "сегодня" = today, "завтра" = tomorrow, "послезавтра" = +2 days
- "в 19" / "до 19" / "к 19" = 19:00:00
- "утром" = 09:00, "в обед" = 13:00, "вечером" = 18:00
- "в понедельник" = next Monday
- No time specified → is_all_day = true, time = 00:00:00
- No date/time → due_date = null

REPEAT (RRULE format):
- "каждый день" → RRULE:FREQ=DAILY
- "каждую неделю" → RRULE:FREQ=WEEKLY
- "каждую среду" → RRULE:FREQ=WEEKLY;BYDAY=WE
- "по будням" → RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
- Day codes: MO,TU,WE,TH,FR,SA,SU
- For recurring: due_date = first occurrence

PRIORITY:
- "срочно"/"важно"/"ASAP" → 5
- "не срочно" → 1
- Default → 0"""


def _dict_to_result(data: dict, fallback_title: str) -> TaskParseResult:
    """Convert parsed dict to TaskParseResult."""
    return TaskParseResult(
        title=data.get("title") or fallback_title,
        due_date=data.get("due_date"),
        repeat_flag=data.get("repeat_flag"),
        is_all_day=data.get("is_all_day", False),
        priority=data.get("priority", 0)
    )


def _call_openai_compatible_api(
    user_input: str,
    api_key: str,
    folder_id: str,
    system_prompt: str
) -> Optional[dict]:
    """Call YandexGPT via OpenAI-compatible API with structured output."""
    payload = {
        "model": f"gpt://{folder_id}/yandexgpt-lite/latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        "temperature": 0.1,
        "max_tokens": 500,
        "response_format": {
            "type": "json_schema",
            "json_schema": TASK_PARSE_SCHEMA
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
    }

    try:
        response = requests.post(
            YANDEX_OPENAI_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return None

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return json.loads(content) if content else None

    except Exception:
        return None


def _call_native_api(
    user_input: str,
    api_key: str,
    folder_id: str,
    system_prompt: str
) -> Optional[dict]:
    """Call YandexGPT via Native API with prompt engineering."""
    payload = {
        "modelUri": f"gpt://{folder_id}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": "500",
        },
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_input}
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
    }

    try:
        response = requests.post(
            YANDEX_NATIVE_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return None

        result = response.json()
        content = (
            result.get("result", {})
            .get("alternatives", [{}])[0]
            .get("message", {})
            .get("text", "")
        )

        json_content = _extract_json(content)
        return json.loads(json_content) if json_content else None

    except Exception:
        return None


def parse_task_with_llm(
    user_input: str,
    api_key: str,
    folder_id: str,
    current_date: str,
    current_weekday: str,
    timezone: str = "+0000"
) -> TaskParseResult:
    """Parse natural language task input using YandexGPT.

    Uses OpenAI-compatible API with structured output as primary method,
    falls back to Native API with prompt engineering if that fails.

    Args:
        user_input: Natural language task description
        api_key: YandexGPT API key
        folder_id: Yandex Cloud folder ID
        current_date: Current date in ISO format (YYYY-MM-DD)
        current_weekday: Current weekday in English (Monday, Tuesday, etc.)
        timezone: Timezone offset (default: +0000)

    Returns:
        TaskParseResult with extracted fields
    """
    # 1. Try OpenAI-compatible API with structured output (guaranteed JSON schema)
    simple_prompt = _build_simple_system_prompt(current_date, current_weekday, timezone)
    data = _call_openai_compatible_api(user_input, api_key, folder_id, simple_prompt)
    if data:
        return _dict_to_result(data, user_input)

    # 2. Fallback: Native API with detailed prompt engineering
    full_prompt = _build_system_prompt(current_date, current_weekday, timezone)
    data = _call_native_api(user_input, api_key, folder_id, full_prompt)
    if data:
        return _dict_to_result(data, user_input)

    # 3. Final fallback: simple parser (no LLM)
    return _fallback_parse(user_input)


def _extract_json(content: str) -> str:
    """Extract JSON from response that may contain markdown."""
    content = content.strip()

    if content.startswith("```"):
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline + 1:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    if not content.startswith("{"):
        start = content.find("{")
        if start != -1:
            content = content[start:]

    if not content.endswith("}"):
        end = content.rfind("}")
        if end != -1:
            content = content[:end + 1]

    return content


def _fallback_parse(user_input: str) -> TaskParseResult:
    """Simple fallback when LLM is unavailable."""
    return TaskParseResult(
        title=user_input,
        due_date=None,
        repeat_flag=None,
        is_all_day=True,
        priority=0
    )
