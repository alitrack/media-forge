"""LLM-driven script composition.

Converts cleaned source text into structured multi-speaker conversation scripts.
Supports four styles: interview, tutorial, explainer, debate.

Configuration (priority: CLI args > .env file > env vars > defaults):
  OPENAI_API_KEY       — LLM API key (OpenAI-compatible)
  OPENAI_BASE_URL      — LLM API base URL (default: https://api.deepseek.com/v1)
  MEDIAFORGE_MODEL     — Model name (default: deepseek-chat)
"""

import json
import os
from pathlib import Path
from typing import Optional

from mediaforge.types import (
    Script, Segment, ContentStyle, VoiceConfig,
)


def _load_dotenv() -> None:
    """Load .env from project root (no external dependency)."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key and val and key not in os.environ:
                os.environ[key] = val

# Auto-load on import
_load_dotenv()


# ── Prompt Templates ──────────────────────────────────────

SYSTEM_PROMPTS = {
    ContentStyle.INTERVIEW: """你是一个专业的对话脚本撰写人。你的任务是将输入的文章内容转化为一场自然流畅的双人访谈播客脚本。

## 角色设定
- 主持人（女性，友善好奇）：引导话题，提出读者关心的问题，说"嗯""对""有意思"等自然过渡
- 专家（男性，深度专业）：解答问题，提供案例和数据，语气自然不做作

## 输出格式
严格输出 JSON 数组，每个元素包含：
- speaker: "host" 或 "expert"
- text: 该段对话内容（中文，30-120字）

## 要求
- 总共 6-12 段对话
- 开头主持人不直接念标题，而是用一个引人好奇的问题开场
- 结尾用一句话总结+行动号召
- 语气像朋友聊天，不要像在读稿子
- 避免"大家好""欢迎收听"等电台腔""",

    ContentStyle.TUTORIAL: """你是一个技术教程作者。将输入内容转化为单人分步教学脚本。

## 输出格式
严格输出 JSON 数组：
- speaker: "host"
- text: 该步骤的讲解（30-100字）

## 要求
- 总共 5-8 段
- 每段一个清晰步骤
- 用"现在""接下来""最后"等过渡词
- 结尾给出输出结果或下一步建议""",

    ContentStyle.EXPLAINER: """你是一个科普解说员。将输入内容转化为由浅入深的单人解说脚本。

## 输出格式
严格输出 JSON 数组：
- speaker: "host"
- text: 讲解内容（40-120字）

## 要求
- 总共 4-8 段
- 开头从一个生活化的比喻或场景引入
- 逐层深入核心概念
- 结尾总结关键要点""",

    ContentStyle.DEBATE: """你是一个辩论脚本撰写人。将输入内容转化为正反双方交替辩论的播客脚本。

## 角色设定
- 正方（男性，立场坚定）：阐述支持观点的论据和数据
- 反方（女性，质疑犀利）：指出漏洞、提出反例

## 输出格式
严格输出 JSON 数组：
- speaker: "pro" 或 "con"
- text: 辩论发言（30-100字）

## 要求
- 总共 6-10 段
- 有来有回，每方发言 3-5 次
- 语气激烈但不失理性
- 结尾给出双方共识或保留分歧""",
}


USER_PROMPT_TEMPLATE = """请将以下内容转化为{style_desc}脚本：

---
{content}
---

直接输出 JSON 数组，不要加其他文字。"""

STYLE_DESC = {
    ContentStyle.INTERVIEW: "双人访谈",
    ContentStyle.TUTORIAL: "单人教学",
    ContentStyle.EXPLAINER: "单人解说",
    ContentStyle.DEBATE: "双人辩论",
}


# ── Composer ──────────────────────────────────────────────

class ComposeError(Exception):
    """Script generation failed."""
    pass


class Composer:
    """Generate conversation scripts from text using LLM."""

    def __init__(
        self,
        model: str = "",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.model = (
            model
            or os.environ.get("MEDIAFORGE_MODEL")
            or "deepseek-chat"
        )
        # Priority: arg > OPENAI_* env > legacy fallbacks
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )
        self.base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("ANTHROPIC_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        self.max_retries = max_retries

    def compose(
        self,
        text: str,
        style: ContentStyle = ContentStyle.INTERVIEW,
        voice_map: Optional[dict[str, str]] = None,
        title: str = "",
    ) -> Script:
        """Generate a conversation script from source text."""
        if not text.strip():
            return Script(
                title=title or "Untitled",
                style=style,
                segments=[Segment(speaker="host", voice_id="default", text="没有足够内容生成脚本。")],
                source_summary="(empty)",
            )

        system = SYSTEM_PROMPTS.get(style, SYSTEM_PROMPTS[ContentStyle.INTERVIEW])
        user = USER_PROMPT_TEMPLATE.format(
            style_desc=STYLE_DESC.get(style, "对话"),
            content=text[:8000],  # keep under token limits
        )

        raw = self._call_llm(system, user)
        segments = self._parse_response(raw, voice_map or {})

        return Script(
            title=title or self._generate_title(text),
            style=style,
            segments=segments,
            source_summary=text[:200] + "..." if len(text) > 200 else text,
        )

    def _call_llm(self, system: str, user: str) -> str:
        """Call LLM with retry."""
        import openai

        client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.8,
                    max_tokens=4096,
                )
                text = resp.choices[0].message.content
                if text:
                    return text
                raise ComposeError("LLM returned empty response")
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)

        raise ComposeError(f"LLM failed after {self.max_retries} attempts: {last_error}")

    def _parse_response(self, raw: str, voice_map: dict[str, str]) -> list[Segment]:
        """Parse LLM JSON response into Segment list. Robust against common LLM JSON quirks."""
        raw = self._clean_json(raw)

        # Try strict parse first
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return self._build_segments(data, voice_map)
        except json.JSONDecodeError:
            pass

        # Try with automatic JSON repair
        try:
            import re
            # Fix 1: trailing commas
            fixed = re.sub(r',\s*}', '}', raw)
            fixed = re.sub(r',\s*]', ']', fixed)
            # Fix 2: missing comma between } and { (common in LLM JSON arrays)
            fixed = re.sub(r'}\s*\n\s*{', '},\n    {', fixed)
            # Fix 3: missing comma between ] and [
            fixed = re.sub(r']\s*\n\s*\[', '],\n    [', fixed)
            data = json.loads(fixed)
            if isinstance(data, list):
                return self._build_segments(data, voice_map)
        except json.JSONDecodeError:
            pass

        raise ComposeError(f"Cannot parse LLM response as JSON. Raw: {raw[:300]}")

    def _clean_json(self, raw: str) -> str:
        """Strip markdown fences and other wrappers."""
        raw = raw.strip()
        # Remove ```json ... ``` fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first line (``` or ```json)
            lines = lines[1:]
            # Remove last line if ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        return raw

    def _build_segments(self, data: list, voice_map: dict[str, str]) -> list[Segment]:
        """Convert parsed JSON array to Segment objects."""
        segments = []
        for item in data:
            if not isinstance(item, dict):
                continue
            speaker = item.get("speaker", "host")
            voice_id = voice_map.get(speaker, "zh-CN-XiaoxiaoNeural")
            text = item.get("text", "")
            if not text.strip():
                continue
            segments.append(Segment(speaker=speaker, voice_id=voice_id, text=text))
        if not segments:
            raise ComposeError("No valid segments in LLM response")
        return segments

    def _generate_title(self, text: str) -> str:
        """Generate a title from the first 100 chars."""
        first_line = text.split("\n")[0][:80].strip()
        if first_line.startswith("#"):
            first_line = first_line.lstrip("#").strip()
        return first_line or "Untitled"
