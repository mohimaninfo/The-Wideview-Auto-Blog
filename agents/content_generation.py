"""
agents/content_generation.py
Agent 4: Content Generation — Generates full blog post drafts using layer-specific prompts.
"""

import json
import logging
import re
import math
from utils.gemini_client import smart_gemini_call

logger = logging.getLogger(__name__)

# [D] Parameterized Gemini prompt templates per layer type
LAYER_PROMPTS = {

    "latest-news": """You are a skilled technology and science journalist writing for {genre}.
Tone: {tone_profile}
Write a LATEST NEWS article in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS TO INCLUDE: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE (use these as H2 headings):
1. Headline Summary — 2-3 sentence summary of the breaking development
2. Key Facts — Bullet list of 5-7 verified facts with inline citations (¹²³)
3. Background Context — 2 paragraphs establishing why this matters
4. Impact Analysis — Who is affected and how (2-3 paragraphs)
5. Expert Reaction — Quote or paraphrase from a named expert (cited)
6. What To Watch — 3-5 bullet points on what to monitor going forward
7. Sources — Do not include here; reference section is added separately

SEO RULES:
- Include primary keyword "{keywords[0]}" in first H2 and first 100 words
- Use LSI keywords naturally in H2s and body text
- Target word count: {word_count} words
- Add a JSON-LD Article schema block at the very end (inside a <script> tag)

ANTI-HALLUCINATION RULES:
- Every specific number, date, name, or claim must reference the research brief
- Use inline superscript citation markers ¹²³ after each cited claim
- Do NOT invent quotes — only use quotes from the research brief
- Mark anything uncertain as [UNVERIFIED — see source]

FORMATTING:
- Output clean HTML with <h1>, <h2>, <h3>, <p>, <ul>, <li>, <strong> tags
- No markdown — pure HTML only
- Include a <div class="article-meta"> block at top with: author byline, date, read time, genre badge, layer badge
- Do NOT include <html>, <head>, or <body> tags — article fragment only

Write the full article now:""",

    "research-articles": """You are a science communicator and research journalist writing for {genre}.
Tone: {tone_profile}
Write a RESEARCH ARTICLE in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS TO INCLUDE: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE (use these as H2 headings):
1. Abstract — 3-4 sentence summary of the article's scope and findings
2. Background & Literature — Prior research, context, what was already known (3-4 paragraphs)
3. Key Findings — The core discoveries/data, explained clearly (3-4 paragraphs with citations)
4. Methodology Overview — How the research/analysis was conducted (1-2 paragraphs)
5. Implications — What this means for practitioners, society, future research
6. Limitations & Caveats — Honest assessment of what we don't yet know
7. Future Directions — What researchers/industry should explore next
8. Frequently Asked Questions — 3-5 Q&A pairs covering common questions
9. Further Reading — 3 suggested resources (use source URLs from research brief)

SEO RULES:
- Include primary keyword "{keywords[0]}" in H1, Abstract, and one H2
- Use academic-adjacent LSI terms in body
- Target word count: {word_count} words
- Include JSON-LD ScholarlyArticle schema

ANTI-HALLUCINATION RULES:
- All statistics must come from the research brief with citation markers ¹²³
- Do not invent study authors or journal names
- Use hedged language: "suggests," "indicates," "preliminary data shows"

FORMATTING: Clean HTML fragment, no <html>/<head>/<body> tags.

Write the full article now:""",

    "how-to-guides": """You are an expert technical writer and educator writing for {genre}.
Tone: {tone_profile}
Write a HOW-TO GUIDE in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS TO INCLUDE: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE:
1. Overview & Goal — What will the reader achieve? Why does it matter? (1-2 paragraphs)
2. Prerequisites — What readers need before starting (bulleted list)
3. Tools & Materials — Required tools, software, or resources (bulleted list with links from research brief)
4. Step-by-Step Instructions — Numbered <ol> with detailed steps. Each step gets its own <h3>.
   Include: what to do, why to do it, common mistake to avoid for each step.
5. Tips & Pro Tips — <ul> with 5-7 practical tips
6. Troubleshooting — 3-5 common problems with solutions (Q&A format)
7. Next Steps — What to do after completing this guide
8. References & Resources — Not included here; added by citation agent

SEO RULES:
- Keyword "{keywords[0]}" in H1, first 100 words, and one step heading
- Use action verbs in step headings (e.g., "Install," "Configure," "Test")
- Target word count: {word_count} words
- Include HowTo JSON-LD schema with each step as a HowToStep

FORMATTING: Clean HTML fragment. Steps MUST use <ol><li> structure.

Write the full guide now:""",

    "opinion-analysis": """You are a seasoned analyst and opinion writer for {genre}.
Tone: {tone_profile}
Write an OPINION & ANALYSIS piece in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS TO INCLUDE: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE:
1. Thesis Statement — One clear, arguable claim in bold. Your central position.
2. Context & Background — Why this matters now (2-3 paragraphs)
3. Core Argument — Main argument with supporting evidence and citations (3-4 paragraphs)
4. Counter-Arguments — Steelman the opposing view honestly (2 paragraphs)
5. Rebuttal — Why the author's position prevails despite counter-arguments (1-2 paragraphs)
6. Evidence & Data — Key statistics and expert opinions supporting the thesis (use research brief)
7. Author's Verdict — Strong, memorable closing statement + call to action

SEO RULES:
- "{keywords[0]}" in H1 and first 150 words
- Use opinion signal words: "argue," "contend," "the evidence suggests"
- Target word count: {word_count} words
- Add OpinionNewsArticle JSON-LD schema

ANTI-HALLUCINATION: Label all opinions clearly. Cite all factual claims.
FORMATTING: Clean HTML fragment.

Write the full piece now:""",

    "case-studies": """You are a business and research journalist for {genre}.
Tone: {tone_profile}
Write a CASE STUDY in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE:
1. Executive Summary — Key outcome in 3-4 sentences (callout box style: <div class="callout">)
2. Background & Challenge — Who faced what problem, why it mattered (2-3 paragraphs)
3. Solution Implemented — What approach was taken and why chosen (2-3 paragraphs)
4. Process & Timeline — Chronological breakdown of implementation
5. Results & Metrics — Quantified outcomes with citation markers (tables encouraged: <table>)
6. Key Lessons — 5-7 bulleted takeaways for readers
7. Applicability — Who else can apply this approach and how
8. Sources — Added by citation agent

SEO RULES: "{keywords[0]}" in H1 and executive summary. Target: {word_count} words.
FORMATTING: Clean HTML fragment.

Write the full case study now:""",

    "interviews": """You are an interviewer and editor for {genre}.
Tone: {tone_profile}
Write an INTERVIEW piece in HTML format. Simulate a realistic Q&A with a named expert.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS: {internal_links}

RESEARCH BRIEF (use this to ground the expert's responses):
{research_brief}

ARTICLE STRUCTURE:
1. About the Expert — Name, title, organization, 2-3 sentence bio
2. Introduction — Why this expert? Why now? (1-2 paragraphs)
3. Q&A Section — 8-10 Q&A pairs. Format:
   <div class="qa-pair">
     <p class="question"><strong>Q: [question]</strong></p>
     <p class="answer">[Expert's answer based on research brief facts]</p>
   </div>
   Questions should move from background → core topic → future outlook
4. Key Takeaways — 5 bulleted lessons from the interview
5. Resources Mentioned — Links from research brief

NOTE: The expert persona MUST be consistent with real people or plausibly described.
Do NOT attribute false quotes to real named individuals. Use a clearly labeled
"composite expert" or fictional named expert if no real quotes are available.
Clearly label the piece as "A simulated interview based on published research."

FORMATTING: Clean HTML fragment. {word_count} words.

Write the full interview now:""",

    "listicles": """You are an engaging content writer for {genre}.
Tone: {tone_profile}
Write a LISTICLE in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE:
1. Introduction & Why This List — Hook the reader, explain the list's value (1-2 paragraphs)
2. The List — 10-15 items. Each item gets:
   <div class="list-item">
     <h3>[Number]. [Item Title]</h3>
     <p>[2-3 sentence description with citation if applicable]</p>
   </div>
   Items must be ordered by relevance/impact, not random
3. Honorable Mentions — 3-5 items briefly noted
4. Verdict & Recommendations — Which items matter most and why (1 paragraph)
5. References — Added by citation agent

SEO RULES: "{keywords[0]}" in H1 and intro. Include ItemList JSON-LD schema.
Target: {word_count} words.
FORMATTING: Clean HTML fragment.

Write the full listicle now:""",

    "reviews": """You are a critical reviewer for {genre}.
Tone: {tone_profile}
Write a REVIEW in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE:
1. Overview & Rating Summary — <div class="rating-box"> with overall score (X/10) and 2-sentence verdict
2. What We Tested/Evaluated — Methodology and scope
3. Pros — <ul class="pros"> with 5-8 positive points
4. Cons — <ul class="cons"> with 3-5 drawbacks
5. Performance Details — Detailed breakdown by category (use <h3> per category)
6. Comparison to Alternatives — Table comparing 3-4 competitors: <table class="comparison">
7. Who Should Use This — Specific audience recommendations
8. Final Verdict — Definitive recommendation with score

SEO: "{keywords[0]}" in H1, overview. Include Review JSON-LD schema with ratingValue.
Target: {word_count} words.
FORMATTING: Clean HTML fragment.

Write the full review now:""",

    "explainers": """You are a science communicator and explainer writer for {genre}.
Tone: {tone_profile}
Write an EXPLAINER in HTML format.

TITLE: {title}
KEYWORDS: {keywords}
INTERNAL LINKS: {internal_links}

RESEARCH BRIEF:
{research_brief}

ARTICLE STRUCTURE:
1. What Is It? — Clear, jargon-free definition (1-2 paragraphs + pull quote)
2. Why It Matters — Real-world significance (2 paragraphs)
3. How It Works — Mechanism/process explained step-by-step (use diagrams in alt text, numbered steps)
4. Real-World Examples — 3 concrete examples with brief descriptions
5. Common Misconceptions — 3-5 myths debunked
6. Frequently Asked Questions — 5 Q&A pairs in <details><summary> accordion HTML
7. Further Reading — 3-5 resources from source_urls in research brief

SEO: "{keywords[0]}" in H1 and "What Is It?" section. Include FAQPage JSON-LD schema.
Target: {word_count} words.
FORMATTING: Clean HTML fragment.

Write the full explainer now:""",
}


class ContentGenerationAgent:
    def generate(self, task: dict) -> dict:
        """
        Input: task with all prior agent outputs
        Output: dict with html_body, title, meta_description, slug, word_count
        """
        genre = task["genre_label"]
        topic = task["topic_label"]
        layer = task["layer"]
        tone = task["tone_profile"]
        title = task["topic_idea"]["title"]
        keywords = task["topic_idea"]["keywords"]
        word_count = task["topic_idea"].get("suggested_word_count", 1400)
        research_brief = json.dumps(task["research_brief"], indent=2)
        section_template = task["layer_meta"]["section_template"]
        internal_links = self._get_internal_links(task)

        prompt_template = LAYER_PROMPTS.get(layer, LAYER_PROMPTS["explainers"])

        prompt = prompt_template.format(
            genre=genre,
            topic=topic,
            tone_profile=tone,
            title=title,
            keywords=keywords,
            keywords_0=keywords[0] if keywords else topic,
            word_count=word_count,
            research_brief=research_brief,
            section_template="\n".join(f"- {s}" for s in section_template),
            internal_links=internal_links,
        ).replace("{keywords[0]}", keywords[0] if keywords else topic)

        html_content = smart_gemini_call(
            prompt,
            primary_model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            system_instruction=f"You are an expert {genre} writer. Output clean HTML only. No markdown.",
            json_mode=False,
            max_tokens=8192,
            temperature=0.65,
        )

        # Generate meta description
        meta_prompt = f"""Write a compelling SEO meta description (150-160 characters) for this article:
Title: {title}
Primary keyword: {keywords[0] if keywords else topic}
Genre: {genre}
Respond with ONLY the meta description text, no quotes."""

        meta_description = smart_gemini_call(
            meta_prompt,
            primary_model="gemini-3.1-flash-lite",
            fallback_model="gemini-3.1-flash-lite",
            max_tokens=200,
            temperature=0.5,
            json_mode=False,
        ).strip()[:160]

        # Generate URL slug
        slug = re.sub(r'[^a-z0-9\s-]', '', title.lower())
        slug = re.sub(r'\s+', '-', slug.strip())[:80]

        # Estimate word count
        estimated_words = len(re.sub(r'<[^>]+>', '', html_content).split())

        logger.info(f"Content generated: ~{estimated_words} words, slug: {slug}")

        return {
            "html_body": html_content,
            "title": title,
            "meta_description": meta_description,
            "slug": slug,
            "estimated_word_count": estimated_words,
            "layer": layer,
            "genre": task["genre_id"],
            "topic": task["topic_id"],
        }

    def _get_internal_links(self, task: dict) -> str:
        """Build internal link suggestions from published posts."""
        genre = task["genre_id"]
        # This would typically pull from published_posts log
        # For now returns placeholder format
        return f"Link to pillar post for {task['topic_label']} if available in /logs/published_posts.json"
