"""
agents/research.py
Agent 3: Research Agent — Produces a structured research brief with cited sources.
Anti-hallucination: only verifiable claims with source URLs.
"""

import json
import logging
import re
from utils.gemini_client import call_gemini
from utils.link_validator import validate_urls

logger = logging.getLogger(__name__)


class ResearchAgent:
    def research(self, task: dict) -> dict:
        """
        Input: task dict with genre, topic, layer, topic_idea
        Output: research_brief dict
        """
        genre = task["genre_label"]
        topic = task["topic_label"]
        layer = task["layer"]
        title = task["topic_idea"]["title"]
        angle = task["topic_idea"]["angle"]
        keywords = task["topic_idea"]["keywords"]
        tone = task["tone_profile"]
        layer_meta = task["layer_meta"]
        section_template = layer_meta["section_template"]

        sections_str = "\n".join(f"- {s}" for s in section_template)
        keywords_str = ", ".join(keywords)

        prompt = f"""You are a senior research journalist with expertise in {genre}, specifically {topic}.

Your task: Create a structured research brief for the following article.

ARTICLE DETAILS:
- Title: {title}
- Angle: {angle}
- Content Layer: {layer}
- Target sections: {sections_str}
- Keywords: {keywords_str}
- Tone: {tone}

CRITICAL ANTI-HALLUCINATION RULES:
1. Every factual claim MUST include a real, verifiable source URL
2. Do NOT invent statistics, quotes, or data
3. If you are uncertain about a fact, mark it as [NEEDS VERIFICATION] and suggest where to verify
4. Use only real organizations, real researchers, real studies
5. All URLs must be from authoritative sources (.gov, .edu, peer-reviewed journals, major news orgs)

RESEARCH BRIEF FORMAT (respond in JSON):
{{
  "title": "{title}",
  "key_facts": [
    {{"fact": "...", "source_url": "https://...", "source_name": "...", "year": 2024}}
  ],
  "statistics": [
    {{"stat": "...", "source_url": "https://...", "source_name": "...", "year": 2024}}
  ],
  "expert_quotes": [
    {{"quote": "...", "expert_name": "...", "expert_title": "...", "source_url": "https://..."}}
  ],
  "background_context": "2-3 sentence background paragraph",
  "key_arguments": ["argument 1", "argument 2", "argument 3"],
  "counterarguments": ["counterargument 1", "counterargument 2"],
  "source_urls": ["https://url1", "https://url2", "https://url3"],
  "suggested_image_search": "3-5 word image search query",
  "suggested_video_search": "YouTube search query if applicable"
}}

Produce the research brief now: 

OUTPUT FORMAT — STRICT JSON ONLY

Return ONLY valid JSON.

Do NOT include:
- markdown
- ```json code fences
- explanations
- extra text
"""

        response_text = call_gemini(
            prompt,
            system_instruction="You are a rigorous research journalist. Never fabricate facts or URLs.",
            json_mode=True,
            temperature=0.3,
        )

        try:
            

            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not match:
                raise ValueError("No JSON found")
            
            brief = json.loads(match.group(0))
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                brief = json.loads(match.group())
            else:
                logger.error("Research agent returned malformed JSON. Using skeleton brief.")
                brief = {
                    "title": title,
                    "key_facts": [],
                    "statistics": [],
                    "expert_quotes": [],
                    "background_context": f"This article covers {title}.",
                    "key_arguments": [angle],
                    "counterarguments": [],
                    "source_urls": [],
                    "suggested_image_search": f"{topic} {genre}",
                    "suggested_video_search": f"{title} explained",
                }

        # Validate source URLs (remove dead links, try archive.org fallback)
        raw_urls = brief.get("source_urls", [])
        if raw_urls:
            validated = validate_urls(raw_urls)
            brief["source_urls"] = validated
            logger.info(f"URLs validated: {len(validated)}/{len(raw_urls)} alive")

        logger.info(f"Research brief created with {len(brief.get('key_facts', []))} facts")
        return brief
