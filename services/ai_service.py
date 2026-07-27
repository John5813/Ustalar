import json
import logging
import os
import re
from openai import AsyncOpenAI
from typing import Dict, List
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Clean text from special characters, formatting issues, and technical JSON snippets"""
    if not text:
        return ""

    # Remove AI conversation artifacts that leak from model training data
    # Truncate at the first occurrence of role labels like "Human:", "Assistant:", "User:"
    text = re.sub(r'\s*(Human|Assistant|User|System)\s*:\s*.*', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Remove any JSON-like structures that might leak into the content
    # Remove lines that start with JSON keys
    text = re.sub(r'^\s*["\']?(?:title|content|column_content|keyword|slides|columns|plan_items|references)["\']?\s*[:\-]\s*.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove JSON object/array markers only if they're standalone lines
    text = re.sub(r'^\s*[\{\[\}\]]\s*$', '', text, flags=re.MULTILINE)
    
    # Remove common JSON delimiters if they leak at start/end
    text = re.sub(r'^\s*["\']|["\']\s*$', '', text)
    text = re.sub(r'["\']?\s*[,\]\}]\s*$', '', text)
    
    # Remove JSON-like patterns only if they contain specific JSON keys (more conservative)
    # Only remove braces/brackets that look like JSON structures with quotes and colons
    text = re.sub(r'\{[^}]*"[^"]*"[^}]*:[^}]*\}', '', text)  # JSON objects with key:value pairs
    text = re.sub(r'\[[^\]]*"[^"]*"[^]]*\]', '', text)  # JSON arrays with quoted strings
    
    # Standard cleaning for other characters - but preserve brackets/braces for legitimate content
    text = re.sub(r'[#@&<>\\|~`]', '', text)  # Removed *{}[]| from here to preserve brackets
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_rate_limit_error(exception: BaseException) -> bool:
    """Check if the exception is a rate limit or quota violation error."""
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or (hasattr(exception, "status_code") and exception.status_code == 429)
    )

class AIService:
    """AI Service using OpenRouter with dynamic model selection"""
    
    _cached_model = None
    _cache_time = None
    
    def __init__(self):
        api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY") or "dummy-key"
        base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    @classmethod
    def clear_model_cache(cls):
        """Clear the model cache to force refresh on next request"""
        cls._cached_model = None
        cls._cache_time = None
        logger.info("AI model cache cleared")
    
    async def _get_current_model_id(self) -> str:
        """Get current AI model ID from database with caching"""
        import time
        from config import AI_MODELS, DEFAULT_AI_MODEL
        from database.database import Database
        
        cache_duration = 30
        
        if AIService._cached_model and AIService._cache_time:
            if time.time() - AIService._cache_time < cache_duration:
                return AIService._cached_model
        
        try:
            model_key = await Database.get_current_ai_model()
            model_info = AI_MODELS.get(model_key, AI_MODELS[DEFAULT_AI_MODEL])
            AIService._cached_model = model_info["id"]
            AIService._cache_time = time.time()
            return AIService._cached_model
        except Exception as e:
            logger.error(f"Error getting current model: {e}")
            return AI_MODELS[DEFAULT_AI_MODEL]["id"]

    def _parse_json_safely(self, json_str: str) -> Dict:
        """Parse JSON with automatic repair for common AI output issues"""
        import re
        
        if not json_str or not json_str.strip():
            raise ValueError("AI returned empty response")
        
        json_str = json_str.strip()
        first_brace = json_str.find('{')
        if first_brace == -1:
            raise ValueError(f"AI response contains no JSON object (no '{{' found). Response: {json_str[:200]!r}")
        if first_brace > 0:
            logger.warning(f"JSON does not start with '{{', stripping {first_brace} leading chars")
            json_str = json_str[first_brace:]
        
        last_brace = json_str.rfind('}')
        if last_brace >= 0 and last_brace < len(json_str) - 1:
            trailing = json_str[last_brace+1:].strip()
            if trailing and not trailing.startswith(','):
                logger.warning(f"Stripping trailing content after last '}}'")
                json_str = json_str[:last_brace+1]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error, attempting repair: {e}")
            
            repaired = json_str
            
            repaired = re.sub(r',\s*}', '}', repaired)
            repaired = re.sub(r',\s*]', ']', repaired)
            
            quote_count = repaired.count('"') - repaired.count('\\"')
            if quote_count % 2 != 0:
                last_complete_slide = repaired.rfind('},')
                if last_complete_slide > 0:
                    repaired = repaired[:last_complete_slide+1]
                else:
                    last_quote = repaired.rfind('"')
                    if last_quote > 0:
                        repaired = repaired[:last_quote] + '"'
            
            open_braces = repaired.count('{')
            close_braces = repaired.count('}')
            open_brackets = repaired.count('[')
            close_brackets = repaired.count(']')
            
            if open_brackets > close_brackets:
                repaired += ']' * (open_brackets - close_brackets)
            if open_braces > close_braces:
                repaired += '}' * (open_braces - close_braces)
            
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
            
            slides_match = re.search(r'"slides"\s*:\s*\[', json_str)
            if slides_match:
                slides_start = slides_match.end() - 1
                
                slide_objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', json_str[slides_start:])
                valid_slides = []
                for slide_obj in slide_objects:
                    try:
                        parsed = json.loads(slide_obj)
                        if 'title' in parsed:
                            valid_slides.append(parsed)
                    except:
                        continue
                
                if valid_slides:
                    logger.info(f"Recovered {len(valid_slides)} slides from truncated JSON")
                    return {"slides": valid_slides}
            
            logger.error(f"Could not repair JSON: {json_str[:500]}...")
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")

    _BOOK_MODE_MARKERS = ("[KITOB ASOSIDA]", "[НА ОСНОВЕ КНИГИ]", "[BOOK-BASED]")
    _BOOK_MODE_SYSTEM = (
        "You are generating academic content using a provided book excerpt as the PRIMARY SOURCE. "
        "Rules:\n"
        "1) CRITICAL — The topic may cover multiple subjects (e.g. 'Comparison of Uzbekistan and Germany law'). "
        "   The book may only cover ONE of those subjects. You MUST write ALL parts of the topic completely:\n"
        "   - For subjects FOUND in the book: use the book content as the basis.\n"
        "   - For subjects NOT found in the book (e.g. a different country, a different field): "
        "     write a COMPLETE, DETAILED section from your general knowledge. "
        "     Do NOT skip, abbreviate, or omit these sections — they are equally required.\n"
        "2) Never contradict information given in the book.\n"
        "3) Write in a natural student style — not an AI template style.\n"
        "4) Respect the requested output language.\n"
        "5) Do NOT mention that you are an AI or that you used a book."
    )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception(is_rate_limit_error),
        reraise=True
    )
    async def _make_request(self, messages: List[Dict], max_tokens: int = 4000, temperature: float = 0.5, response_format: Dict = None) -> str:
        """Make API request with retry logic using Replit AI Integrations for OpenRouter"""
        current_model = await self._get_current_model_id()
        logger.info(f"Using AI model: {current_model}")

        has_book = any(
            any(marker in msg.get("content", "") for marker in self._BOOK_MODE_MARKERS)
            for msg in messages if msg.get("role") == "user"
        )
        if has_book:
            messages = [{"role": "system", "content": self._BOOK_MODE_SYSTEM}] + list(messages)

        FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct"

        async def _do_request(model: str) -> str:
            params = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format:
                params["response_format"] = response_format
            resp = await self.client.chat.completions.create(**params)
            return resp.choices[0].message.content.strip()

        try:
            return await _do_request(current_model)
        except Exception as e:
            err_str = str(e)
            if "504" in err_str or "502" in err_str or "503" in err_str or "aborted" in err_str.lower():
                logger.warning(f"Provider error ({err_str[:120]}), retrying with fallback model: {FALLBACK_MODEL}")
                return await _do_request(FALLBACK_MODEL)
            raise

    async def generate_presentation_content(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content with AI - new structured format"""
        try:
            if language == "uz":
                prompt = self._get_presentation_prompt_uz(topic, slide_count)
            elif language == "ru":
                prompt = self._get_presentation_prompt_ru(topic, slide_count)
            else:
                prompt = self._get_presentation_prompt_en(topic, slide_count)

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            content_str = content_str.strip()
            if not content_str:
                logger.warning("Empty AI response for presentation, retrying once...")
                response = await self._make_request(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8192,
                    temperature=0.7
                )
                content_str = response.strip()
                if content_str.startswith("```json"):
                    content_str = content_str[7:]
                if content_str.startswith("```"):
                    content_str = content_str[3:]
                if content_str.endswith("```"):
                    content_str = content_str[:-3]
                content_str = content_str.strip()
                if not content_str:
                    raise ValueError("AI returned empty response after retry")
            
            content = self._parse_json_safely(content_str)
            
            if 'slides' not in content:
                logger.error("No 'slides' key in content")
                raise ValueError("Content must contain 'slides' key")
            
            for idx, slide in enumerate(content['slides']):
                if 'title' not in slide:
                    slide['title'] = f"Slayd {idx + 1}"
                if 'content' not in slide:
                    slide['content'] = ""
                    
            logger.info(f"Generated presentation with {len(content['slides'])} slides")
            
            content = self._normalize_slide_structure(content, slide_count, language)

            for slide in content.get('slides', []):
                if slide.get('layout') == 'table' and not slide.get('table_data', {}).get('rows'):
                    try:
                        table_data = await self.generate_table_data(topic, 1, language)
                        slide['table_data'] = table_data
                    except Exception as te:
                        logger.error(f"Error pre-generating table data: {te}")

            return content

        except Exception as e:
            logger.error(f"Error generating presentation content: {e}")
            raise

    def _shorten_plan_item(self, item: str) -> str:
        """Shorten a plan item to a concise single phrase (max 6 words)."""
        if not item:
            return item
        item = re.sub(r'^\d+[\.\)\-\s]+', '', item).strip()
        for sep in [',', ';', '.', ' - ', ' – ', ' — ', ':']:
            if sep in item:
                item = item.split(sep)[0].strip()
                break
        words = item.split()
        if len(words) > 6:
            item = ' '.join(words[:6])
        return item

    def _normalize_slide_structure(self, content: Dict, slide_count: int, language: str) -> Dict:
        """Ensure slides follow the mandatory structure and enforce exact slide_count.
        Structure: cover + plan + intro + N main + conclusion + references + thanks = slide_count.
        Table slides are EXTRA and do NOT count toward slide_count."""
        slides = content.get('slides', [])

        cover_slide = None
        plan_slide = None
        intro_slide = None
        main_slides = []
        conclusion_slide = None
        references_slide = None
        thanks_slide = None

        for slide in slides:
            layout = slide.get('layout', '')
            if layout == 'cover' and not cover_slide:
                cover_slide = slide
            elif layout == 'plan' and not plan_slide:
                plan_slide = slide
            elif layout == 'intro' and not intro_slide:
                intro_slide = slide
            elif layout == 'conclusion' and not conclusion_slide:
                conclusion_slide = slide
            elif layout == 'references' and not references_slide:
                references_slide = slide
            elif layout == 'thanks' and not thanks_slide:
                thanks_slide = slide
            elif layout == 'table':
                pass
            elif layout in ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']:
                main_slides.append(slide)
            else:
                main_slides.append(slide)

        title_labels = {
            'uz': {'cover': '', 'plan': 'Reja', 'intro': 'Kirish', 'conclusion': 'Xulosa', 'references': 'Foydalangan adabiyotlar', 'thanks': ''},
            'ru': {'cover': '', 'plan': 'План', 'intro': 'Введение', 'conclusion': 'Заключение', 'references': 'Литература', 'thanks': ''},
            'en': {'cover': '', 'plan': 'Agenda', 'intro': 'Introduction', 'conclusion': 'Conclusion', 'references': 'References', 'thanks': ''}
        }
        labels = title_labels.get(language, title_labels['uz'])

        target_main = max(slide_count - 6, 1)
        if slide_count == 10:
            target_main += 1
        layouts = ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']

        while len(main_slides) < target_main:
            idx = len(main_slides)
            main_slides.append({'title': '', 'content': '', 'layout': layouts[idx % 6]})

        main_slides = main_slides[:target_main]

        normalized = []

        if not cover_slide:
            cover_slide = {'title': '', 'content': '', 'layout': 'cover'}
        normalized.append(cover_slide)

        if not plan_slide:
            plan_slide = {'title': labels['plan'], 'content': '', 'layout': 'plan', 'plan_items': []}
        normalized.append(plan_slide)

        if not intro_slide:
            intro_slide = {'title': labels['intro'], 'content': '', 'layout': 'intro'}
        normalized.append(intro_slide)

        slide_counter = 0
        for i, slide in enumerate(main_slides):
            if slide.get('layout') not in layouts:
                slide['layout'] = layouts[i % len(layouts)]
            if slide.get('title'):
                slide['title'] = self._strip_leading_numbering(slide['title'])
            normalized.append(slide)
            slide_counter += 1

            table_after = 3 if slide_count == 10 else 5
            if slide_counter == table_after and (slide_count == 10 or slide_counter < len(main_slides)):
                table_title = {
                    'uz': "Tahlil jadvali",
                    'ru': "Аналитическая таблица",
                    'en': "Analysis Table"
                }
                normalized.append({
                    'title': table_title.get(language, table_title['uz']),
                    'content': '',
                    'layout': 'table',
                    'table_data': {}
                })

        if not conclusion_slide:
            conclusion_slide = {'title': labels['conclusion'], 'content': '', 'layout': 'conclusion'}
        normalized.append(conclusion_slide)

        if not references_slide:
            references_slide = {'title': labels['references'], 'content': '', 'layout': 'references', 'references': []}
        normalized.append(references_slide)

        if not thanks_slide:
            thanks_slide = {'title': labels['thanks'], 'content': '', 'layout': 'thanks'}
        normalized.append(thanks_slide)

        return {'slides': normalized}

    def _build_example_slides_json(self, topic: str, main_count: int, lang: str) -> str:
        """Build dynamic example JSON with exactly main_count main slides"""
        layouts = ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']

        uz_examples = [
            '{"title": "Sarlavha", "content": "", "layout": "two_column", "columns": [{"column_content": "Birinchi jihat haqida uchta aniq tushuntiruvchi gap. Bu ustun mustaqil mavzuni yoritadi. Har bir gap tugallangan fikr bildiradi."}, {"column_content": "Ikkinchi jihat haqida uchta alohida gap. Bu ustun boshqa mavzuni yoritadi. Har bir gap mustaqil fikrga ega."}]}',
            '{"title": "Sarlavha", "content": "Mavzuning muhim jihati haqida birinchi gap. Ikkinchi gapda statistik malumot keltirilgan. Uchinchi gapda amaliy misol berilgan. Tortinchi gapda xulosa qilingan.", "layout": "right_image"}',
            '{"title": "Sarlavha", "content": "Mavzuning boshqa jihati haqida birinchi gap. Ikkinchi gapda ilmiy malumot keltirilgan. Uchinchi gapda tahlil berilgan. Tortinchi gapda natija korsatilgan.", "layout": "left_image"}',
            '{"title": "Sarlavha", "content": "", "layout": "three_column", "columns": [{"keyword": "Birinchi", "column_content": "Birinchi tushuncha haqida yigirmaga yaqin sozdan iborat tugallangan tarif gapi."}, {"keyword": "Ikkinchi", "column_content": "Ikkinchi tushuncha haqida yigirmaga yaqin sozdan iborat alohida tarif gapi."}, {"keyword": "Uchinchi", "column_content": "Uchinchi tushuncha haqida yigirmaga yaqin sozdan iborat mustaqil tarif gapi."}]}',
            '{"title": "Sarlavha", "content": "Mavzuning ushbu qirrasi haqida birinchi aniq gap. Ikkinchi gapda statistika va dalillar keltirilgan. Uchinchi gapda amaliy ahamiyati korsatilgan.", "layout": "horizontal_image"}',
            '{"title": "Sarlavha", "content": "1. Birinchi korsatkich — 85% samaradorlik. Batafsil izoh va tahlil.\\n2. Ikkinchi malumot — 3,2 marta osish. Sabablar va oqibatlar.\\n3. Uchinchi statistika — 47 ta davlatda qollaniladi. Tarqalish sabablari.\\n4. Tortinchi fakt — 2024 yilda 15% osish kuzatilgan. Tendentsiya.\\n5. Beshinchi korsatkich — 92% ijobiy baho. Amaliy natijalar.", "layout": "text_with_numbers"}',
        ]

        ru_examples = [
            '{"title": "Заголовок", "content": "", "layout": "two_column", "columns": [{"column_content": "Три чётких пояснительных предложения о первом аспекте. Эта колонка раскрывает свою тему самостоятельно. Каждое предложение выражает законченную мысль."}, {"column_content": "Три отдельных предложения о втором аспекте. Эта колонка раскрывает другую тему. Каждое предложение самостоятельно и информативно."}]}',
            '{"title": "Заголовок", "content": "Первое предложение о важном аспекте темы. Второе предложение со статистическими данными. Третье предложение с практическим примером. Четвёртое предложение с выводом.", "layout": "right_image"}',
            '{"title": "Заголовок", "content": "Первое предложение о другом аспекте темы. Второе предложение с научными данными. Третье предложение с анализом. Четвёртое предложение с результатом.", "layout": "left_image"}',
            '{"title": "Заголовок", "content": "", "layout": "three_column", "columns": [{"keyword": "Первое", "column_content": "Описание первого понятия в одном предложении около двадцати слов."}, {"keyword": "Второе", "column_content": "Описание второго понятия в одном предложении около двадцати слов."}, {"keyword": "Третье", "column_content": "Описание третьего понятия в одном предложении около двадцати слов."}]}',
            '{"title": "Заголовок", "content": "Первое точное предложение о данном аспекте темы. Второе предложение со статистикой и фактами. Третье предложение о практическом значении.", "layout": "horizontal_image"}',
            '{"title": "Заголовок", "content": "1. Первый показатель — 85% эффективности. Подробный анализ.\\n2. Второй показатель — рост в 3,2 раза. Причины и последствия.\\n3. Третий факт — применяется в 47 странах. Распространение.\\n4. Четвёртый факт — рост 15% в 2024 году. Тенденция.\\n5. Пятый показатель — 92% положительных оценок. Результаты.", "layout": "text_with_numbers"}',
        ]

        en_examples = [
            '{"title": "Title", "content": "", "layout": "two_column", "columns": [{"column_content": "Three clear explanatory sentences about the first aspect. This column covers its own independent topic. Each sentence expresses a complete thought."}, {"column_content": "Three separate sentences about the second aspect. This column covers a different topic independently. Each sentence is self-contained and informative."}]}',
            '{"title": "Title", "content": "First sentence about an important aspect of the topic. Second sentence with statistical data and evidence. Third sentence with a practical example. Fourth sentence with a concluding thought.", "layout": "right_image"}',
            '{"title": "Title", "content": "First sentence about another aspect of the topic. Second sentence with scientific data and research. Third sentence with detailed analysis. Fourth sentence with key results.", "layout": "left_image"}',
            '{"title": "Title", "content": "", "layout": "three_column", "columns": [{"keyword": "First", "column_content": "A complete description of the first concept in about twenty words."}, {"keyword": "Second", "column_content": "A complete description of the second concept in about twenty words."}, {"keyword": "Third", "column_content": "A complete description of the third concept in about twenty words."}]}',
            '{"title": "Title", "content": "First precise sentence about this aspect of the topic. Second sentence with statistics and evidence. Third sentence about practical significance.", "layout": "horizontal_image"}',
            '{"title": "Title", "content": "1. First indicator — 85% efficiency. Detailed analysis.\\n2. Second metric — 3.2x growth. Causes and implications.\\n3. Third statistic — used in 47 countries. Reasons for spread.\\n4. Fourth fact — 15% growth in 2024. Development trend.\\n5. Fifth indicator — 92% positive rating. Practical results.", "layout": "text_with_numbers"}',
        ]

        lang_map = {'uz': uz_examples, 'ru': ru_examples, 'en': en_examples}
        examples = lang_map.get(lang, uz_examples)

        headers = {
            'uz': [
                f'{{"title": "{topic}", "content": "", "layout": "cover"}}',
                '{"title": "Reja", "content": "", "layout": "plan", "plan_items": ["1. Mavzu haqida", "2. Asosiy tushunchalar", "3. Amaliy qollanilishi", "4. Xulosa"]}',
                '{"title": "Kirish", "content": "Mavzuning ahamiyati va dolzarbligi haqida kirish matni.", "layout": "intro"}'
            ],
            'ru': [
                f'{{"title": "{topic}", "content": "", "layout": "cover"}}',
                '{"title": "План", "content": "", "layout": "plan", "plan_items": ["1. О теме", "2. Основные понятия", "3. Применение", "4. Выводы"]}',
                '{"title": "Введение", "content": "Введение о важности и актуальности темы.", "layout": "intro"}'
            ],
            'en': [
                f'{{"title": "{topic}", "content": "", "layout": "cover"}}',
                '{"title": "Agenda", "content": "", "layout": "plan", "plan_items": ["1. About the topic", "2. Key concepts", "3. Applications", "4. Conclusions"]}',
                '{"title": "Introduction", "content": "Introduction about the importance and relevance of the topic.", "layout": "intro"}'
            ]
        }

        footers = {
            'uz': [
                '{"title": "Xulosa", "content": "Mavzuning asosiy fikrlarini jamlang.", "layout": "conclusion"}',
                '{"title": "Adabiyotlar", "content": "", "layout": "references", "references": ["Manba nomi va yili", "Manba nomi va yili", "Manba nomi va yili", "Manba nomi va yili"]}',
                '{"title": "", "content": "", "layout": "thanks"}'
            ],
            'ru': [
                '{"title": "Заключение", "content": "Обобщите основные идеи темы.", "layout": "conclusion"}',
                '{"title": "Литература", "content": "", "layout": "references", "references": ["Источник 1", "Источник 2", "Источник 3", "Источник 4"]}',
                '{"title": "", "content": "", "layout": "thanks"}'
            ],
            'en': [
                '{"title": "Conclusion", "content": "Summarize the main ideas of the topic.", "layout": "conclusion"}',
                '{"title": "References", "content": "", "layout": "references", "references": ["Source 1", "Source 2", "Source 3", "Source 4"]}',
                '{"title": "", "content": "", "layout": "thanks"}'
            ]
        }

        slides = list(headers.get(lang, headers['uz']))
        for i in range(main_count):
            slides.append(examples[i % 6])
        slides.extend(footers.get(lang, footers['uz']))

        entries = ',\n        '.join(slides)
        return '{\n    "slides": [\n        ' + entries + '\n    ]\n}'

    def _get_presentation_prompt_uz(self, topic: str, slide_count: int) -> str:
        """Get Uzbek prompt for presentation generation"""
        main_count = slide_count - 6
        if main_count < 1:
            main_count = 1
        if slide_count == 10:
            main_count += 1
        example_json = self._build_example_slides_json(topic, main_count, 'uz')
        return f"""O'zbek tilida "{topic}" mavzusida professional taqdimot yarating.

STRUKTURA (jami {slide_count} slayd):
1. Muqova slayd (mavzu nomi va muallif uchun joy)
2. Reja slayd (4 ta reja punkti — har biri 2-4 so'zlik QISQA IBORA, jumlasiz, nuqtasiz)
3. Kirish slayd (~50 so'z, mavzuga umumiy kirish)
4-{3 + main_count}. Asosiy slaidlar ({main_count} ta) - har biri mavzuning turli jihatlarini yoritadi
{slide_count - 2}. Xulosa slayd (~50 so'z)
{slide_count - 1}. Adabiyotlar ro'yxati (4 ta sodda manba, har biri 5-8 so'z)
{slide_count}. Rahmat slayd ("E'tiboringiz uchun rahmat!")

ASOSIY SLAIDLAR UCHUN 6 TA SHABLON (tartib bilan takrorlanadi):
1. two_column - 2 MUSTAQIL ustun, har birida ~3 ta aniq tushuntiruvchi manoli gap
2. right_image - o'ngda rasm, chapda mavzuga mos 4 ta o'rta darajadagi gap
3. left_image - chapda rasm, o'ngda mavzuga mos 4 ta o'rta darajadagi gap
4. three_column - 3 MUSTAQIL ustun, har birida: 1 ta kalit so'z iborasi + ~20 so'zli 1 ta gap
5. horizontal_image - pastda rasm, ustida o'rtacha hajmdagi va aniq ma'lumotli 3 ta gap
6. text_with_numbers - 5 ta raqamlab joylangan aniq faktlar va raqamlardan iborat gaplar

JUDA MUHIM QOIDA - USTUNLAR UCHUN:
- two_column va three_column da har bir ustun O'Z ALOHIDA MAVZUSI bo'lishi kerak!
- Bir ustundagi gap BOSHQA ustunda davom etmasin!
- Har bir ustun TUGALLANGAN, MUSTAQIL paragraf bo'lsin!

RASM SLAYDLAR UCHUN QOIDA:
- right_image va left_image uchun aniq 4 ta gap yozing!
- horizontal_image uchun aniq 3 ta gap yozing!
- Placeholder ([...]) YOZMANG - HAQIQIY to'liq matn yozing!

Har bir slayd uchun:
- title: Slayd sarlavhasi
- content: Asosiy mazmun (FAQAT ustunli bo'lmagan slaidlar uchun)
- layout: shablon turi
- columns: MAJBURIY two_column va three_column uchun

MUHIM: Faqat JSON formatda javob bering! Jami {slide_count} ta slayd bo'lishi SHART (asosiy slaidlar soni: {main_count} ta)!
{example_json}"""

    def _get_presentation_prompt_ru(self, topic: str, slide_count: int) -> str:
        """Get Russian prompt for presentation generation"""
        main_count = slide_count - 6
        if main_count < 1:
            main_count = 1
        if slide_count == 10:
            main_count += 1
        example_json = self._build_example_slides_json(topic, main_count, 'ru')
        return f"""Создайте профессиональную презентацию на тему "{topic}" на русском языке.

СТРУКТУРА (всего {slide_count} слайдов):
1. Титульный слайд (название темы и место для автора)
2. Слайд с планом (4 пункта — каждый КРАТКАЯ ФРАЗА из 2-4 слов, без запятых и точек)
3. Введение (~50 слов, общее введение в тему)
4-{3 + main_count}. Основные слайды ({main_count} шт) - каждый освещает разные аспекты темы
{slide_count - 2}. Заключение (~50 слов)
{slide_count - 1}. Список литературы (4 простых источника, каждый 5-8 слов)
{slide_count}. Слайд благодарности ("Спасибо за внимание!")

ШАБЛОНЫ ДЛЯ ОСНОВНЫХ СЛАЙДОВ (чередуются по порядку):
1. two_column - 2 НЕЗАВИСИМЫЕ колонки, каждая содержит ~3 чётких пояснительных предложения
2. right_image - справа изображение, слева 4 предложения средней длины по теме
3. left_image - слева изображение, справа 4 предложения средней длины по теме
4. three_column - 3 НЕЗАВИСИМЫЕ колонки, каждая: ключевое слово-фраза + 1 предложение ~20 слов
5. horizontal_image - внизу изображение, сверху 3 точных информативных предложения
6. text_with_numbers - 5 пронумерованных предложений с конкретными фактами и цифрами

ОЧЕНЬ ВАЖНОЕ ПРАВИЛО - ДЛЯ КОЛОНОК:
- В two_column и three_column каждая колонка должна иметь СВОЮ ОТДЕЛЬНУЮ ТЕМУ!
- Предложение из одной колонки НЕ ДОЛЖНО продолжаться в другой!
- Каждая колонка — ЗАКОНЧЕННЫЙ, НЕЗАВИСИМЫЙ абзац!

ПРАВИЛО ДЛЯ СЛАЙДОВ С ИЗОБРАЖЕНИЯМИ:
- Для right_image и left_image — ровно 4 предложения!
- Для horizontal_image — ровно 3 предложения!
- НЕ пишите placeholder в скобках — пишите НАСТОЯЩИЙ текст!

Для каждого слайда:
- title: Заголовок слайда
- content: Основной текст (ТОЛЬКО для слайдов без колонок)
- layout: тип шаблона
- columns: ОБЯЗАТЕЛЬНО для two_column и three_column

ВАЖНО: Отвечайте ТОЛЬКО в формате JSON! Всего {slide_count} слайдов ОБЯЗАТЕЛЬНО (основных слайдов: {main_count})!
{example_json}"""

    def _get_presentation_prompt_en(self, topic: str, slide_count: int) -> str:
        """Get English prompt for presentation generation"""
        main_count = slide_count - 6
        if main_count < 1:
            main_count = 1
        if slide_count == 10:
            main_count += 1
        example_json = self._build_example_slides_json(topic, main_count, 'en')
        return f"""Create a professional presentation on "{topic}" in English.

STRUCTURE (total {slide_count} slides):
1. Cover slide (topic name and author placeholder)
2. Agenda slide (4 points — each a SHORT PHRASE of 2-4 words, no full sentences, no punctuation)
3. Introduction (~50 words, general intro to topic)
4-{3 + main_count}. Main slides ({main_count} total) - each covers different aspects
{slide_count - 2}. Conclusion (~50 words)
{slide_count - 1}. References (4 simple sources, each 5-8 words)
{slide_count}. Thank you slide ("Thank you for your attention!")

TEMPLATES FOR MAIN SLIDES (rotate in order):
1. two_column - 2 INDEPENDENT columns, each containing ~3 clear explanatory meaningful sentences
2. right_image - image on right, 4 medium-length sentences matching the topic on left
3. left_image - image on left, 4 medium-length sentences matching the topic on right
4. three_column - 3 INDEPENDENT columns, each: 1 keyword phrase + 1 sentence of ~20 words
5. horizontal_image - image at bottom, 3 precise medium-sized informative sentences on top
6. text_with_numbers - 5 numbered sentences with specific facts and figures

CRITICAL RULE - FOR COLUMNS:
- In two_column and three_column, each column must have its OWN SEPARATE TOPIC!
- A sentence from one column must NOT continue in another!
- Each column must be a COMPLETE, INDEPENDENT paragraph!

RULE FOR IMAGE SLIDES:
- For right_image and left_image — exactly 4 sentences!
- For horizontal_image — exactly 3 sentences!
- Do NOT write placeholder text in brackets — write REAL content!

For each slide:
- title: Slide title
- content: Main text (ONLY for non-column slides)
- layout: template type
- columns: REQUIRED for two_column and three_column

IMPORTANT: Respond ONLY in JSON format! Total {slide_count} slides REQUIRED (main slides: {main_count})!
{example_json}"""

    async def generate_document_content(self, topic: str, section_count: int, document_type: str, language: str) -> Dict:
        """Generate document content with AI - each section separately"""
        try:
            outline = await self._generate_document_outline(topic, section_count, document_type, language)
            
            sections = []
            for i, section_title in enumerate(outline['sections']):
                section_content = await self._generate_section_content(
                    topic, section_title, i + 1, section_count, document_type, language
                )
                sections.append({
                    "title": section_title,
                    "content": section_content
                })

            references = await self._generate_references(topic, language)
            
            # Generate table data for section 3 (mustaqil ish)
            table_data_3 = None
            if section_count >= 4:
                table_data_3 = await self.generate_table_data(topic, 3, language)

            result = {
                "title": topic,
                "sections": sections,
                "references": references
            }
            
            if table_data_3:
                result["table_data_3"] = table_data_3
            
            return result

        except Exception as e:
            logger.error(f"Error generating document content: {e}")
            raise

    @staticmethod
    def _strip_leading_numbering(title: str) -> str:
        """Remove leading numbering like '1.', '1.1', '2.3 ' from titles"""
        import re
        return re.sub(r'^\d+[\d.]*[.\s]+', '', title).strip()

    async def _generate_document_outline(self, topic: str, section_count: int, document_type: str, language: str) -> Dict:
        """Generate document outline with section titles"""
        try:
            if language == "uz":
                if document_type == "independent_work":
                    prompt = f"""O'zbek tilida "{topic}" mavzusida mustaqil ish uchun {section_count} ta bo'lim sarlavhalarini yarating.

Bo'limlar:
1. Kirish
2-{section_count-1}. Asosiy bo'limlar
{section_count}. Xulosa

MUHIM: Sarlavhalarga raqam qo'shmang (masalan "1.", "1.1", "2.3" kabi boshlamang).

JSON formatda javob bering:
{{"sections": ["Bo'lim 1 sarlavhasi", "Bo'lim 2 sarlavhasi", ...]}}"""
                else:
                    prompt = f"""O'zbek tilida "{topic}" mavzusida referat uchun {section_count} ta bo'lim sarlavhalarini yarating.

Bo'limlar:
1. Kirish
2-{section_count-1}. Asosiy bo'limlar  
{section_count}. Xulosa

MUHIM: Sarlavhalarga raqam qo'shmang (masalan "1.", "1.1", "2.3" kabi boshlamang).

JSON formatda javob bering:
{{"sections": ["Bo'lim 1 sarlavhasi", "Bo'lim 2 sarlavhasi", ...]}}"""
            elif language == "ru":
                doc_type_ru = "самостоятельной работы" if document_type == "independent_work" else "реферата"
                prompt = f"""Создайте {section_count} заголовков разделов для {doc_type_ru} на тему "{topic}" на русском языке.

Разделы:
1. Введение
2-{section_count-1}. Основные разделы
{section_count}. Заключение

ВАЖНО: Не добавляйте номера к заголовкам (не начинайте с "1.", "1.1", "2.3" и т.д.).

Ответьте в формате JSON:
{{"sections": ["Заголовок раздела 1", "Заголовок раздела 2", ...]}}"""
            else:
                doc_type_en = "independent work" if document_type == "independent_work" else "research paper"
                prompt = f"""Create {section_count} section titles for {doc_type_en} on "{topic}" in English.

Sections:
1. Introduction
2-{section_count-1}. Main sections
{section_count}. Conclusion

IMPORTANT: Do not include numbers in the titles (do not start with "1.", "1.1", "2.3", etc.).

Respond in JSON format:
{{"sections": ["Section 1 title", "Section 2 title", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            content_str = content_str.strip()

            # Robust JSON extraction — AI sometimes returns trailing prose,
            # truncated/unterminated strings, or no closing brace at all.
            outline = None
            try:
                outline = json.loads(content_str)
            except json.JSONDecodeError:
                # Try a balanced {...} block first
                m = re.search(r'\{.*\}', content_str, re.DOTALL)
                if m:
                    try:
                        outline = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        outline = None

            if outline is None:
                # Final fallback: pull section titles directly out of any
                # quoted strings that look like real titles (handles both
                # unterminated strings AND completely missing closing brace).
                titles = re.findall(r'"([^"\n]{5,200})"', content_str)
                # Drop the literal "sections" key if it was matched
                titles = [t for t in titles if t.lower() != "sections"]
                if titles and len(titles) >= 2:
                    outline = {"sections": titles[:section_count]}
                    logger.warning(
                        f"Outline JSON malformed, extracted {len(outline['sections'])} titles via fallback"
                    )
                else:
                    raise json.JSONDecodeError(
                        "Could not extract outline from AI response",
                        content_str, 0,
                    )

            outline['sections'] = [
                self._strip_leading_numbering(s) for s in outline.get('sections', [])
            ]
            return outline

        except Exception as e:
            logger.error(f"Error generating document outline: {e}")
            raise

    async def _generate_section_content(self, topic: str, section_title: str, section_num: int, total_sections: int, document_type: str, language: str) -> str:
        """Generate content for a specific section"""
        try:
            # Determine word targets based on section count (proxy for page target)
            if total_sections <= 6:  # 10-15 pages
                intro_words = "150-200"
                body_words = "280-350"
                conclusion_words = "200-250"
            elif total_sections <= 9:  # 15-20 pages
                intro_words = "200-250"
                body_words = "380-450"
                conclusion_words = "280-330"
            else:  # 20+ pages
                intro_words = "250-300"
                body_words = "500-600"
                conclusion_words = "350-450"

            common_rules = """
QOIDALAR:
- Javobni to'g'ridan-to'g'ri matn bilan boshlang, bo'lim sarlavhasini qaytarmang
- Faqat oddiy matn yozing, hech qanday maxsus belgi ishlatmang (#, @, &, *, {, }, [, ], va h.k.)
- Matnda takrorlanish bo'lmasin - har bir gap yangi ma'lumot bersin
- Markdown formatlash ishlatmang (**, *, _, __ va h.k.)
- Professional akademik til ishlating
- Faqat sof matn, ro'yxatlar yoki raqamli punktlar bo'lmasin"""

            common_rules_ru = """
ПРАВИЛА:
- Начинайте ответ сразу с текста, не повторяйте заголовок раздела
- Пишите только простой текст без специальных символов (#, @, &, *, {, }, [, ] и т.д.)
- Избегайте повторений - каждое предложение должно содержать новую информацию
- Не используйте форматирование Markdown (**, *, _, __ и т.д.)
- Используйте профессиональный академический язык
- Только чистый текст без списков и нумерации"""

            common_rules_en = """
RULES:
- Start your response directly with the text, do not repeat the section title
- Write only plain text without special characters (#, @, &, *, {, }, [, ], etc.)
- Avoid repetition - each sentence should provide new information
- Do not use Markdown formatting (**, *, _, __, etc.)
- Use professional academic language
- Only plain text without lists or numbered points"""

            if language == "uz":
                if section_num == 1:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun professional akademik kirish yozing.

ANIQ {intro_words} so'z yozing — ko'proq yozmang. Mavzuning dolzarbligi, maqsadi va ahamiyatini yoritib bering.
{common_rules}"""
                elif section_num == total_sections:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun xulosa yozing.

ANIQ {conclusion_words} so'z yozing — ko'proq yozmang. Asosiy xulosalar, natijalar va tavsiyalarni yozing.
{common_rules}"""
                else:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun chuqur akademik mazmun yarating.

ANIQ {body_words} so'z yozing — ko'proq yozmang. Mavzuni to'liq yoritib, misollar va dalillar keltiring.
{common_rules}"""

            elif language == "ru":
                if section_num == 1:
                    prompt = f"""Напишите профессиональное академическое введение для раздела "{section_title}" по теме "{topic}" на русском языке.

СТРОГО {intro_words} слов — не больше. Опишите актуальность темы, цели и значимость.
{common_rules_ru}"""
                elif section_num == total_sections:
                    prompt = f"""Напишите заключение для раздела "{section_title}" по теме "{topic}" на русском языке.

СТРОГО {conclusion_words} слов — не больше. Изложите основные выводы, результаты и рекомендации.
{common_rules_ru}"""
                else:
                    prompt = f"""Напишите глубокое академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

СТРОГО {body_words} слов — не больше. Полностью раскройте тему с примерами и аргументами.
{common_rules_ru}"""
            else:
                if section_num == 1:
                    prompt = f"""Write professional academic introduction for "{section_title}" on "{topic}" in English.

EXACTLY {intro_words} words — no more. Describe the relevance, objectives and significance of the topic.
{common_rules_en}"""
                elif section_num == total_sections:
                    prompt = f"""Write conclusion for "{section_title}" on "{topic}" in English.

EXACTLY {conclusion_words} words — no more. Present main conclusions, results and recommendations.
{common_rules_en}"""
                else:
                    prompt = f"""Write deep academic content for "{section_title}" on "{topic}" in English.

EXACTLY {body_words} words — no more. Fully cover the topic with examples and arguments.
{common_rules_en}"""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write clear, well-structured content as plain text only. Never use special characters, markdown, or formatting. Never repeat the section title at the start of your response."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.8
            )

            matn = response.strip()
            matn = matn.replace('\n\n', ' ')
            matn = matn.replace('\n', ' ')
            matn = clean_text(matn)

            return matn

        except Exception as e:
            logger.error(f"Error generating section content: {e}")
            raise

    @staticmethod
    def _expand_city_abbrevs(text: str) -> str:
        """Replace common single-letter city abbreviations with full names.

        AI models often output "T:", "M:", "B:" etc. even when instructed not to.
        This is a hard post-processing safety net applied to every reference string.
        """
        import re
        replacements = {
            # Uzbek/CIS cities — must match ". T:" / ". T." / " T:" patterns
            r'\.\s+T\s*:': '. Toshkent:',
            r'\.\s+M\s*:': '. Moskva:',
            r'\.\s+B\s*:': '. Bishkek:',
            r'\.\s+A\s*:': '. Almaty:',
            r'\.\s+K\s*:': '. Kiev:',
            r'\.\s+SPb\s*:': '. Sankt-Peterburg:',
            r'\.\s+Sp\s*:': '. Sankt-Peterburg:',
            r'\.\s+L\s*:': '. London:',
            r'\.\s+N\s*:': '. New York:',
            # Same but with period after abbreviation: "T.", "M." inside city slot
            r'\.\s+T\.\s*:': '. Toshkent:',
            r'\.\s+M\.\s*:': '. Moskva:',
            r'\.\s+B\.\s*:': '. Bishkek:',
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text)
        return text

    async def _generate_references(self, topic: str, language: str) -> List[str]:
        """Generate academic references for course work"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            prompt = f"""Create a list of 7-9 realistic academic references for a course work on the topic: "{topic}".
THE ENTIRE LIST MUST BE IN {target_lang_name.upper()} LANGUAGE.

STRICT COMPOSITION RULES:
- At least 4-5 must be BOOKS or TEXTBOOKS: Author(s). Title. City: Publisher, Year. — e.g. "Ivanov A.B. Ekonomika. Toshkent: Fan nashriyoti, 2021."
- At least 2 must be JOURNAL ARTICLES: Author(s). Article title // Journal name. Year. No.X. Pages X-X.
- Maximum 1-2 legal/regulatory documents (laws, decrees) — do NOT make these the majority
- NO duplicate authors or titles
- All years must be between 2005 and 2024
- DO NOT include category headers, numbering, or bullet points in the output
- ALWAYS write city names IN FULL — NEVER use abbreviations like "T.", "T:", "M.", "M:", "B.", "B:" etc. Write "Toshkent", "Moskva", "Bishkek", "London" in full.

Return as a JSON list:
{{"references": ["Reference 1", "Reference 2", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )
            
            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            return [self._expand_city_abbrevs(r) for r in data.get('references', [])]
            
        except Exception as e:
            logger.error(f"Error generating references: {e}")
            return []

    async def generate_slide_titles(self, topic: str, slide_count: int, language: str) -> List[str]:
        """Generate individual slide titles for the presentation"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi uchun {slide_count} ta slayd sarlavhasini yarating.

MUHIM: Sarlavhalarga raqam qo'shmang (masalan "1.", "1.1", "2.3" kabi boshlamang).

JSON formatda:
{{"titles": ["Sarlavha 1", "Sarlavha 2", ...]}}"""
            elif language == "ru":
                prompt = f"""Создайте {slide_count} заголовков слайдов для темы "{topic}".

ВАЖНО: Не добавляйте номера к заголовкам (не начинайте с "1.", "1.1", "2.3" и т.д.).

В формате JSON:
{{"titles": ["Заголовок 1", "Заголовок 2", ...]}}"""
            else:
                prompt = f"""Create {slide_count} slide titles for the topic "{topic}".

IMPORTANT: Do not include numbers in the titles (do not start with "1.", "1.1", "2.3", etc.).

In JSON format:
{{"titles": ["Title 1", "Title 2", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            titles = data.get('titles', [])
            return [self._strip_leading_numbering(t) for t in titles]

        except Exception as e:
            logger.error(f"Error generating slide titles: {e}")
            return []

    async def generate_image_prompt(self, topic: str, slide_title: str, language: str) -> str:
        """Generate detailed English prompt for image generation"""
        try:
            prompt = f"""Create a detailed, professional image generation prompt in English for:
Topic: {topic}
Slide: {slide_title}

The prompt should describe:
- Visual style (modern, professional, high-quality)
- Key visual elements related to the topic
- Color scheme
- Composition
- NO text, words, letters, numbers, labels, or watermarks in the image

Output only the image prompt, nothing else. Make it detailed and specific for best results."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.8
            )

            return response.strip()

        except Exception as e:
            logger.error(f"Error generating image prompt: {e}")
            return f"Professional presentation image about {topic} - {slide_title}, modern corporate style, high quality, 4K"

    async def generate_presentation_in_batches(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content in batches - wrapper for generate_presentation_content"""
        return await self.generate_presentation_content(topic, slide_count, language)

    async def generate_presentation_with_manual_titles(self, topic: str, manual_titles: List[str], language: str) -> Dict:
        """Generate presentation content with manually provided titles"""
        try:
            slides = []
            
            slides.append({
                'title': topic,
                'content': '',
                'layout': 'cover'
            })
            
            slides.append({
                'title': 'Reja' if language == 'uz' else ('План' if language == 'ru' else 'Agenda'),
                'content': '',
                'layout': 'plan',
                'plan_items': manual_titles[:4]
            })
            
            slides.append({
                'title': 'Kirish' if language == 'uz' else ('Введение' if language == 'ru' else 'Introduction'),
                'content': await self._generate_intro_content(topic, language),
                'layout': 'intro'
            })
            
            layouts = ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']
            for i, title in enumerate(manual_titles):
                layout = layouts[i % len(layouts)]
                content = await self._generate_slide_content(topic, title, language, layout)
                slides.append({
                    'title': title,
                    'content': content,
                    'layout': layout
                })
            
            slides.append({
                'title': 'Xulosa' if language == 'uz' else ('Заключение' if language == 'ru' else 'Conclusion'),
                'content': await self._generate_conclusion_content(topic, language),
                'layout': 'conclusion'
            })
            
            slides.append({
                'title': 'Adabiyotlar' if language == 'uz' else ('Литература' if language == 'ru' else 'References'),
                'content': '',
                'layout': 'references',
                'references': await self._generate_references(topic, language)
            })
            
            slides.append({
                'title': '',
                'content': '',
                'layout': 'thanks'
            })
            
            return {'slides': slides}
            
        except Exception as e:
            logger.error(f"Error generating presentation with manual titles: {e}")
            raise

    async def generate_references(self, topic: str, language: str) -> List[str]:
        """Public method to generate references"""
        return await self._generate_references(topic, language)

    async def generate_plan_items(self, topic: str, language: str) -> List[str]:
        """Generate 4 plan items for presentation"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi uchun 4 ta reja punktini yarating.

MUHIM: Har bir punkt 3-5 so'zdan iborat, mavzuni qisqacha tariflovchi ibora bo'lsin. Jumlasiz, nuqtasiz.
To'g'ri misol: ["Mavzuga kirish va dolzarbligi", "Asosiy tushunchalar tahlili", "Amaliy qo'llanish usullari", "Xulosalar va tavsiyalar"]
Noto'g'ri misol: ["Kirish", "Tushunchalar", "Qo'llanish", "Xulosa"]

JSON formatda:
{{"items": ["Ibora 1", "Ibora 2", "Ibora 3", "Ibora 4"]}}"""
            elif language == "ru":
                prompt = f"""Создайте 4 пункта плана для темы "{topic}".

ВАЖНО: Каждый пункт — фраза из 3-5 слов, кратко описывающая раздел. Без полных предложений, без точек.
Правильно: ["Введение и актуальность темы", "Анализ основных понятий", "Методы практического применения", "Выводы и рекомендации"]
Неправильно: ["Введение", "Понятия", "Применение", "Выводы"]

В формате JSON:
{{"items": ["Фраза 1", "Фраза 2", "Фраза 3", "Фраза 4"]}}"""
            else:
                prompt = f"""Create 4 agenda items for "{topic}".

IMPORTANT: Each item must be a descriptive phrase of 3-5 words. No full sentences, no punctuation.
Correct: ["Introduction and topic relevance", "Analysis of key concepts", "Practical application methods", "Conclusions and recommendations"]
Incorrect: ["Introduction", "Concepts", "Application", "Conclusion"]

In JSON format:
{{"items": ["Phrase 1", "Phrase 2", "Phrase 3", "Phrase 4"]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            return data.get('items', [])

        except Exception as e:
            logger.error(f"Error generating plan items: {e}")
            return []

    async def _generate_intro_content(self, topic: str, language: str) -> str:
        """Generate introduction content (~50 words)"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusiga kirish yozing. 50 so'z atrofida."""
            elif language == "ru":
                prompt = f"""Напишите введение к теме "{topic}". Около 50 слов."""
            else:
                prompt = f"""Write an introduction to "{topic}". Around 50 words."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating intro: {e}")
            return ""

    async def _generate_conclusion_content(self, topic: str, language: str) -> str:
        """Generate conclusion content (~50 words)"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusiga xulosa yozing. 50 so'z atrofida."""
            elif language == "ru":
                prompt = f"""Напишите заключение к теме "{topic}". Около 50 слов."""
            else:
                prompt = f"""Write a conclusion for "{topic}". Around 50 words."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating conclusion: {e}")
            return ""

    async def _generate_slide_content(self, topic: str, title: str, language: str, layout: str) -> str:
        """Generate content for a specific slide based on layout"""
        try:
            word_counts = {
                'two_column': 60,
                'right_image': 75,
                'left_image': 75,
                'three_column': 18,
                'horizontal_image': 50,
                'text_with_numbers': 45
            }
            word_count = word_counts.get(layout, 50)
            
            if language == "uz":
                prompt = f""""{topic}" mavzusi, "{title}" slayd uchun mazmun yozing. {word_count} so'z atrofida."""
            elif language == "ru":
                prompt = f"""Напишите содержание для слайда "{title}" по теме "{topic}". Около {word_count} слов."""
            else:
                prompt = f"""Write content for slide "{title}" on topic "{topic}". Around {word_count} words."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating slide content: {e}")
            return ""

    async def generate_course_work_content(self, topic: str, chapters: int, language: str, min_pages: int = 20, max_pages: int = 25) -> Dict:
        """Generate course work content with chapter structure and footnotes
        
        Structure:
        - Kirish (Introduction) - 2 pages
        - Bo'limlar (Chapters) with 3 subsections each
        - Xulosa (Conclusion)
        - Adabiyotlar (References)
        """
        try:
            content = {
                "title": topic,
                "chapters": [],
                "introduction": "",
                "intro_points": {},
                "conclusion": "",
                "references": []
            }
            
            # Calculate word target based on target page range.
            # Fixed overhead (title, TOC, intro, conclusion, refs): ~8 pages.
            # ~280 words per page (Times New Roman 14pt, 1.5 spacing).
            FIXED_PAGES = 8
            WORDS_PER_PAGE = 280
            total_subsections = chapters * 3
            content_pages = max(min_pages - FIXED_PAGES, 10)
            words_needed = content_pages * WORDS_PER_PAGE
            words_per_sub = words_needed // total_subsections
            low = int(words_per_sub * 0.9 // 50 * 50)
            high = int(words_per_sub * 1.1 // 50 * 50) + 50
            low = max(low, 280)
            high = max(high, low + 100)
            sub_word_target = f"{low}-{high}"

            # Generate chapter titles first
            chapter_titles = await self._generate_chapter_titles(topic, chapters, language)
            
            # Generate introduction (2 pages worth ~600 words)
            content["introduction"] = await self._generate_course_intro(topic, language)
            
            # Generate specific intro points (Subject, Object, Goal, etc.)
            content["intro_points"] = await self._generate_intro_points(topic, language)
            
            # Generate each chapter with 3 subsections
            for i, chapter_title in enumerate(chapter_titles, 1):
                chapter = {
                    "number": i,
                    "title": chapter_title,
                    "subsections": []
                }
                
                # Generate 3 subsections for each chapter
                subsection_titles = await self._generate_subsection_titles(topic, chapter_title, language)

                for j, sub_title in enumerate(subsection_titles[:3], 1):
                    sub_content = await self._generate_subsection_content(topic, chapter_title, sub_title, language, sub_word_target)
                    
                    chapter["subsections"].append({
                        "number": f"{i}.{j}",
                        "title": sub_title,
                        "content": sub_content
                    })
                
                content["chapters"].append(chapter)
            
            # Generate table data for all chapters
            for chapter_num in range(1, chapters + 1):
                content[f"table_data_{chapter_num}"] = await self.generate_table_data(topic, chapter_num, language)
            
            # Generate conclusion
            content["conclusion"] = await self._generate_course_conclusion(topic, language)
            
            # Generate references
            content["references"] = await self._generate_references(topic, language)
            
            return content
            
        except Exception as e:
            logger.error(f"Error generating course work content: {e}")
            raise

    async def _generate_chapter_titles(self, topic: str, chapters: int, language: str, century_conditional: bool = False) -> List[str]:
        """Generate chapter titles for course work"""
        try:
            # First, ensure we have the topic in the target language
            translated_topic = topic
            if language != "uz":
                translation_prompt = f"Translate this topic into {'Russian' if language == 'ru' else 'English'}: {topic}. Provide only the translated text."
                translated_topic = await self._make_request(
                    messages=[{"role": "user", "content": translation_prompt}],
                    max_tokens=100
                )
                translated_topic = translated_topic.strip()

            if century_conditional:
                century_ru = "Agar mavzuda asrlar tilga olinsa, ularni Rim raqamida yozing (masalan, XX asr). Mavzu tarix bilan bog'liq bo'lmasa, asrlarni o'zingizdan QO'SHMANG."
                century_ru_lang = "Если тема связана с историческими периодами — пишите века римскими цифрами (например, XX век). Если тема не предполагает века — НЕ добавляйте их."
                century_en = "If the topic involves historical periods, write centuries in Roman numerals (e.g., XX century). If the topic is not historical — do NOT add century references."
            else:
                century_ru = "Asrlarni ALBATTA Rim raqamida yozing (masalan, \"XX asr\", \"XIX-XX asrlar\", \"XIV asr\"), HECH QACHON arab raqamida yozmang (\"20-asr\" emas, \"XX asr\")."
                century_ru_lang = "ОБЯЗАТЕЛЬНО пишите века РИМСКИМИ цифрами (например, \"XX век\", \"XIX-XX века\", \"XIV век\"), НИКОГДА не используйте арабские цифры (НЕ \"20 век\", а \"XX век\")."
                century_en = "ALWAYS write centuries in ROMAN numerals (e.g., \"XX century\", \"XIX-XX centuries\", \"XIV century\"), NEVER in Arabic numerals (NOT \"20th century\", but \"XX century\")."

            if language == "ru":
                prompt = f"""Для темы "{translated_topic}" создайте {chapters} названий глав для курсовой работы.
Каждая глава должна охватывать разные аспекты темы. ВСЕ ДОЛЖНО БЫТЬ НА РУССКОМ ЯЗЫКЕ.
{century_ru_lang}
Не добавляйте номер главы (1., 2.) в начало названия.

Ответьте в формате JSON:
{{"chapters": ["Название главы 1", "Название главы 2", ...]}}"""
            elif language == "en":
                prompt = f"""For topic "{translated_topic}", create {chapters} chapter titles for course work.
Each chapter should cover different aspects of the topic. EVERYTHING MUST BE IN ENGLISH.
{century_en}
Do not add a chapter number (1., 2.) at the beginning of the title.

Respond in JSON format:
{{"chapters": ["Chapter 1 title", "Chapter 2 title", ...]}}"""
            else: # uz
                prompt = f""""{topic}" mavzusi uchun {chapters} ta bo'lim (chapter) sarlavhasini yarating.
Har bir bo'lim mavzuning turli jihatlarini qamrab olishi kerak. HAMMASI O'ZBEK TILIDA BO'LSIN.
{century_ru}
Sarlavha boshiga raqam (1., 2.) qo'shmang.

JSON formatda javob bering:
{{"chapters": ["Birinchi bo'lim sarlavhasi", "Ikkinchi bo'lim sarlavhasi", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )
            
            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            return data.get('chapters', [f"Bo'lim {i}" for i in range(1, chapters + 1)])
            
        except Exception as e:
            logger.error(f"Error generating chapter titles: {e}")
            return [f"Bo'lim {i}" for i in range(1, chapters + 1)]

    async def _generate_subsection_titles(self, topic: str, chapter_title: str, language: str, century_conditional: bool = False) -> List[str]:
        """Generate 3 subsection titles for a chapter"""
        try:
            # Use chapter_title directly as it should already be in the target language
            if century_conditional:
                century_uz = "Agar bob nomi yoki mavzuda asrlar tilga olinsa, Rim raqamida yozing (masalan, XX asr). Mavzu tarix bilan bog'liq bo'lmasa, asrlarni QO'SHMANG."
                century_ru_lang = "Если глава или тема связана с историческими периодами — пишите века римскими цифрами (например, XX век). Если нет — НЕ добавляйте их."
                century_en = "If the chapter or topic involves historical periods, write centuries in Roman numerals (e.g., XX century). If not — do NOT add century references."
            else:
                century_uz = "Asrlarni ALBATTA Rim raqamida yozing (masalan, \"XX asr\", \"XIV asr\"), HECH QACHON arab raqamida yozmang."
                century_ru_lang = "ОБЯЗАТЕЛЬНО пишите века РИМСКИМИ цифрами (например, \"XX век\", \"XIV век\"), НИКОГДА не используйте арабские цифры."
                century_en = "ALWAYS write centuries in ROMAN numerals (e.g., \"XX century\", \"XIV century\"), NEVER in Arabic numerals."

            if language == "ru":
                prompt = f"""Создайте 3 названия подразделов для главы "{chapter_title}" по теме. ВСЕ НА РУССКОМ ЯЗЫКЕ.
{century_ru_lang} Не добавляйте номер (1.1, 1.2) в начало названия.

В формате JSON:
{{"subsections": ["Подраздел 1", "Подраздел 2", "Подраздел 3"]}}"""
            elif language == "en":
                prompt = f"""Create 3 subsection titles for chapter "{chapter_title}". EVERYTHING IN ENGLISH.
{century_en} Do not add numbering (1.1, 1.2) at the start.

In JSON format:
{{"subsections": ["Subsection 1", "Subsection 2", "Subsection 3"]}}"""
            else: # uz
                prompt = f""""{chapter_title}" bo'limi uchun 3 ta kichik bo'lim sarlavhasini yarating. HAMMASI O'ZBEK TILIDA BO'LSIN.
{century_uz} Sarlavha boshiga raqam (1.1, 1.2) qo'shmang.

JSON formatda:
{{"subsections": ["sarlavha 1", "sarlavha 2", "sarlavha 3"]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7
            )
            
            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            return data.get('subsections', ["Kirish qismi", "Asosiy mazmun", "Yakuniy fikrlar"])
            
        except Exception as e:
            logger.error(f"Error generating subsection titles: {e}")
            return ["Kirish qismi", "Asosiy mazmun", "Yakuniy fikrlar"]

    async def _generate_subsection_content(self, topic: str, chapter_title: str, subsection_title: str, language: str, word_target: str = "380-440", century_conditional: bool = False) -> str:
        """Generate content for a subsection"""
        try:
            if century_conditional:
                century_uz_rule = "- Agar matnda asrlar tilga olinsa, ularni Rim raqamida yozing (XIV asr, XIX-XX asrlar). Mavzu tarix bilan bog'liq bo'lmasa, asrlarni O'ZINGIZDAN QO'SHMANG"
                century_ru_rule = "- Если в тексте упоминаются исторические периоды — пишите века римскими цифрами (XIV век, XIX-XX века). Если тема не историческая — НЕ добавляйте века самостоятельно"
                century_en_rule = "- If the text mentions historical periods, write centuries in Roman numerals (XIV century, XIX-XX centuries). If the topic is not historical — do NOT add century references on your own"
            else:
                century_uz_rule = "- Asrlarni ALBATTA Rim raqamida yozing (XIV asr, XIX-XX asrlar, VII asr) — HECH QACHON arab raqamida (14-asr, 19-asr) yozmang"
                century_ru_rule = "- ОБЯЗАТЕЛЬНО пишите века РИМСКИМИ цифрами (XIV век, XIX-XX века, VII век) — НИКОГДА не пишите арабскими (14 век, 19 век)"
                century_en_rule = "- ALWAYS write centuries in ROMAN numerals (XIV century, XIX-XX centuries, VII century) — NEVER in Arabic numerals (14th century, 19th century)"

            common_rules = f"""
QOIDALAR:
- Faqat oddiy matn yozing, hech qanday maxsus belgi ishlatmang
- Hech qanday markdown formatidan foydalanmang
- Har bir gap to'liq va mustaqil bo'lishi kerak
- Professional akademik uslubda yozing
{century_uz_rule}
- Matn boshida mavzu, bob yoki kichik bo'lim sarlavhasini TAKRORLAMANG — to'g'ridan to'g'ri mazmun bilan boshlang
- Matn ichiga "Foydalanilgan adabiyotlar:", "[1]", "[2]", "[3]" kabi ro'yxat yoki manba belgilarini KIRITMANG — manbalar avtomatik ravishda qo'shiladi"""

            common_rules_ru = f"""
ПРАВИЛА:
- Пишите только простой текст без специальных символов
- Не используйте markdown форматирование
- Каждое предложение должно быть полным и самостоятельным
- Пишите в профессиональном академическом стиле
{century_ru_rule}
- НЕ ПОВТОРЯЙТЕ в начале текста название темы, главы или подраздела — начинайте сразу с содержания
- НЕ ВКЛЮЧАЙТЕ в текст списки источников вида "Список литературы:", "[1]", "[2]", "[3]" — ссылки добавляются автоматически"""

            common_rules_en = f"""
RULES:
- Write only plain text without special characters
- Do not use markdown formatting
- Each sentence must be complete and independent
- Write in professional academic style
{century_en_rule}
- DO NOT repeat the topic, chapter, or subsection title at the start of the text — begin directly with the content
- DO NOT include reference lists like "References:", "[1]", "[2]", "[3]" inside the text — citations are added automatically"""

            if language == "uz":
                prompt = f"""Quyidagi kichik bo'lim uchun akademik mazmun yozing: "{subsection_title}" (umumiy mavzu: "{topic}", bob: "{chapter_title}").

KAMIDA {word_target} so'z yozing — bu MAJBURIY minimal hajm. Mavzuni juda chuqur, batafsil yoriting: tarixiy ma'lumotlar, ko'plab misollar, statistik dalillar, mualliflar fikri, qiyosiy tahlil, sabab-oqibat aloqalari, amaliy ahamiyat — barchasini keng yoriting. Qisqa yozmang.
Matnni mazmun bilan boshlang, sarlavhalarni takrorlamang.
{common_rules}"""
            elif language == "ru":
                prompt = f"""Напишите академическое содержание для подраздела: "{subsection_title}" (общая тема: "{topic}", глава: "{chapter_title}").

МИНИМУМ {word_target} слов — это ОБЯЗАТЕЛЬНЫЙ минимальный объём. Раскройте тему максимально глубоко и подробно: исторические данные, множество примеров, статистические аргументы, мнения авторов, сравнительный анализ, причинно-следственные связи, практическое значение — всё развёрнуто. Не пишите коротко.
Начинайте с содержания, не повторяйте названия.
{common_rules_ru}"""
            else:
                prompt = f"""Write academic content for the subsection: "{subsection_title}" (overall topic: "{topic}", chapter: "{chapter_title}").

AT LEAST {word_target} words — this is the MANDATORY minimum length. Cover the topic in maximum depth and detail: historical context, many examples, statistical evidence, scholarly opinions, comparative analysis, cause-and-effect relationships, practical significance — all expanded. Do not write briefly.
Begin with content directly, do not repeat titles.
{common_rules_en}"""

            # Dynamically set max_tokens from the upper end of word_target.
            # Uzbek/Russian text uses ~1.8 tokens per word on average.
            try:
                upper_words = int(word_target.split("-")[-1])
            except Exception:
                upper_words = 650
            dynamic_max_tokens = min(int(upper_words * 2.5), 8000)

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write clear, well-structured content as plain text only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=dynamic_max_tokens,
                temperature=0.8
            )
            
            matn = response.strip()
            matn = clean_text(matn)

            # Strip ANY combination of topic / chapter_title / subsection_title that the
            # AI may have prepended as a heading. Repeats stripping until no prefix matches.
            import re as _re_local

            def _normalize(s: str) -> str:
                # lowercase, strip punctuation/whitespace, collapse spaces
                s = s.lower()
                s = _re_local.sub(r"[^\w\s\-]", " ", s, flags=_re_local.UNICODE)
                s = _re_local.sub(r"\s+", " ", s).strip()
                return s

            prefixes_to_strip = [
                subsection_title,
                chapter_title,
                topic,
            ]
            # Also try without leading numbering like "1.1 ", "1. "
            extra_prefixes = []
            for p in prefixes_to_strip:
                stripped = _re_local.sub(r"^\d+(\.\d+)*\.?\s*", "", p)
                if stripped and stripped != p:
                    extra_prefixes.append(stripped)
            prefixes_to_strip.extend(extra_prefixes)

            changed = True
            max_iters = 8
            while changed and max_iters > 0:
                changed = False
                max_iters -= 1
                norm_matn = _normalize(matn)
                for prefix in prefixes_to_strip:
                    norm_prefix = _normalize(prefix)
                    if not norm_prefix:
                        continue
                    if norm_matn.startswith(norm_prefix):
                        # Find original position by counting normalized chars
                        # Simpler: find prefix word-by-word in original matn
                        words_prefix = norm_prefix.split()
                        # Walk original matn, skipping characters until we've consumed all prefix words
                        pos = 0
                        consumed = 0
                        n = len(matn)
                        while pos < n and consumed < len(words_prefix):
                            # Skip non-word chars
                            while pos < n and not (matn[pos].isalnum() or matn[pos] in "-'’ʻ"):
                                pos += 1
                            # Read a word
                            word_start = pos
                            while pos < n and (matn[pos].isalnum() or matn[pos] in "-'’ʻ"):
                                pos += 1
                            word = _normalize(matn[word_start:pos])
                            if word == words_prefix[consumed]:
                                consumed += 1
                            else:
                                break
                        if consumed == len(words_prefix):
                            # Skip trailing punctuation/space
                            while pos < n and matn[pos] in " .,;:!?—-\n\t":
                                pos += 1
                            matn = matn[pos:].strip()
                            changed = True
                            break

            # Hard fallback: strip inline reference list patterns the AI may
            # still produce despite the prompt rule. Real footnotes are added
            # by the document_service via Word footnote XML, NOT inline markers.
            # Patterns removed:
            #   "Foydalanilgan adabiyotlar: [1] ... [2] ... [3] ..."
            #   "Список литературы: [1] ... [2] ..."
            #   "References: [1] ... [2] ..."
            #   Standalone "[1]", "[2]", "[3]" markers in body text.
            ref_label_pattern = _re_local.compile(
                r"(?:Foydalanilgan\s+adabiyotlar|Adabiyotlar\s+ro['ʻ`’]?yxati|"
                r"Manbalar|Список\s+(?:использованной\s+)?литературы|"
                r"Список\s+источников|References|Bibliography)\s*[:：]\s*",
                _re_local.IGNORECASE,
            )
            # Drop the label and any following inline citation tail until the
            # paragraph end (newline) or end of string.
            matn = _re_local.sub(
                ref_label_pattern.pattern + r"[^\n]*",
                "",
                matn,
                flags=_re_local.IGNORECASE,
            )
            # Strip leftover standalone bracket markers like [1], [12], [1,2]
            matn = _re_local.sub(r"\s*\[\d+(?:\s*[,;]\s*\d+)*\]\s*", " ", matn)
            # Tidy: collapse extra spaces and stray empty lines created above.
            matn = _re_local.sub(r"[ \t]{2,}", " ", matn)
            matn = _re_local.sub(r"\n{3,}", "\n\n", matn).strip()

            return matn
            
        except Exception as e:
            logger.error(f"Error generating subsection content: {e}")
            return ""

    async def _generate_intro_points(self, topic: str, language: str) -> Dict[str, str]:
        """Generate specific introduction points: Subject, Object, Goal, Tasks, etc."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi kurs ishi uchun quyidagi 6 ta punktga juda batafsil va aynan mavzuga asoslangan akademik tarif bering. 
DIQQAT: Umumiy gaplardan qoching, har bir punkt aynan "{topic}" mavzusining ichki jihatlarini, uning ilmiy va amaliy ahamiyatini yoritib berishi shart. 

Punktlar (har biri kamida 40-50 so'zdan iborat bo'lsin):
1. Kurs ishining predmeti (Mavzuning qaysi jihatlari o'rganiladi?).
2. Kurs ishining obyekti (Mavzu qaysi soha yoki tushunchaga tegishli?).
3. Mavzuning o‘rganilganlik darajasi (Hozirgi kunda bu mavzu qanchalik o'rganilgan?).
4. Kurs ishining maqsadi (Tadqiqotdan ko'zlangan asosiy natija nima?).
5. Kurs ishining vazifalari (Maqsadga erishish uchun bajarilishi kerak bo'lgan bosqichlarni punktma-punkt yozing).
6. Kurs ishining tarkibiy tuzilishi (Kirish, bo'limlar va xulosaning qisqacha tavsifi).

JSON formatda javob bering:
{{
  "point_1": "konkret mavzu predmeti haqida chuqur tahlil...",
  "point_2": "mavzu obyekti haqida batafsil ma'lumot...",
  "point_3": "ilmiy daraja tahlili...",
  "point_4": "aniq maqsad tarifi...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "tuzilish bayoni..."
}}"""
            elif language == "ru":
                prompt = f"""Дайте подробное академическое описание следующих 6 пунктов для курсовой работы по теме "{topic}". 
ВНИМАНИЕ: Избегайте общих фраз. Каждый пункт должен быть глубоко связан именно с темой "{topic}", раскрывая её научные и практические аспекты.

Пункты (минимум 40-50 слов каждый):
1. Предмет курсовой работы (какие именно стороны темы изучаются?).
2. Объект курсовой работы (к какой области или понятию относится тема?).
3. Степень изученности темы (насколько глубоко эта тема изучена на данный момент?).
4. Цель курсовой работы (основной ожидаемый результат исследования?).
5. Задачи курсовой работы (напишите по пунктам шаги для достижения цели).
6. Структура курсовой работы (краткое описание введения, глав и заключения).

Ответьте в формате JSON:
{{
  "point_1": "глубокий анализ предмета темы...",
  "point_2": "подробное описание объекта темы...",
  "point_3": "анализ научной степени изученности...",
  "point_4": "описание конкретной цели...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "описание структуры..."
}}"""
            else:
                prompt = f"""Provide detailed academic descriptions for the following 6 points for a course work on "{topic}".
ATTENTION: Avoid general phrases. Each point must be deeply connected specifically to the topic "{topic}", revealing its scientific and practical aspects.

Points (at least 40-50 words each):
1. Subject of the course work (what specific aspects of the topic are studied?).
2. Object of the course work (what area or concept does the topic belong to?).
3. Degree of study of the topic (how well is this topic studied currently?).
4. Goal of the course work (what is the main expected result of the study?).
5. Tasks of the course work (write point by point steps to achieve the goal).
6. Structure of the course work (brief description of introduction, chapters, and conclusion).

Respond in JSON format:
{{
  "point_1": "deep analysis of the topic subject...",
  "point_2": "detailed description of the topic object...",
  "point_3": "scientific study degree analysis...",
  "point_4": "specific goal description...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "structure description..."
}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )
            
            import re as _re_json
            content_str = response.strip()
            m = _re_json.search(r'\{.*\}', content_str, _re_json.DOTALL)
            if m:
                content_str = m.group()
            return json.loads(content_str)
            
        except Exception as e:
            logger.error(f"Error generating intro points: {e}")
            return {f"point_{i}": "" for i in range(1, 7)}

    async def _generate_course_intro(self, topic: str, language: str) -> str:
        """Generate course work introduction (~300 words, concise)"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi kurs ishi uchun qisqa va lo'nda ilmiy kirish qismini yozing.
DIQQAT: Umumiy gaplardan voz keching. Kirish qismi aynan "{topic}" mavzusining mohiyatini ochib bersin.

250-300 so'z yozing. Quyidagilarni qisqacha yozing:
- Mavzuning dolzarbligi
- Tadqiqotning ilmiy va amaliy ahamiyati
- Mavzuning qisqacha nazariy asosi

Professional akademik uslubda yozing. Faqat oddiy matn, markdown ishlatmang."""
            elif language == "ru":
                prompt = f"""Напишите краткое научное введение для курсовой работы по теме: "{topic}".
ВНИМАНИЕ: Избегайте общих фраз. Введение должно раскрывать суть темы "{topic}".

250-300 слов. Кратко раскройте:
- Актуальность темы
- Научная и практическая значимость
- Краткая теоретическая основа

Профессиональный академический стиль. Только обычный текст, без markdown."""
            else:
                prompt = f"""Write a concise scientific introduction for a course work on: "{topic}".
THE ENTIRE TEXT MUST BE IN {target_lang_name.upper()} LANGUAGE.
Avoid general phrases. Focus on the essence of "{topic}".

250-300 words. Briefly cover:
- Relevance of the topic
- Scientific and practical significance
- Brief theoretical basis

Professional academic style. Plain text only, no markdown."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write concise, focused introductions. No filler."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.7
            )
            return clean_text(response.strip())

        except Exception as e:
            logger.error(f"Error generating course intro: {e}")
            return ""

    async def _generate_diploma_intro(self, topic: str, language: str) -> str:
        """Generate diploma work introduction (~300 words, concise)"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi diplom ishi uchun qisqa va lo'nda ilmiy kirish qismini yozing.
DIQQAT: Umumiy gaplardan voz keching. Kirish qismi aynan "{topic}" mavzusining mohiyatini ochib bersin.

250-300 so'z yozing. Quyidagilarni qisqacha yozing:
- Mavzuning dolzarbligi
- Tadqiqotning ilmiy va amaliy ahamiyati
- Mavzuning qisqacha nazariy asosi

Professional akademik uslubda yozing. Faqat oddiy matn, markdown ishlatmang."""
            elif language == "ru":
                prompt = f"""Напишите краткое научное введение для дипломной работы по теме: "{topic}".
ВНИМАНИЕ: Избегайте общих фраз. Введение должно раскрывать суть темы "{topic}".

250-300 слов. Кратко раскройте:
- Актуальность темы
- Научная и практическая значимость
- Краткая теоретическая основа

Профессиональный академический стиль. Только обычный текст, без markdown."""
            else:
                prompt = f"""Write a concise scientific introduction for a diploma work on: "{topic}".
THE ENTIRE TEXT MUST BE IN {target_lang_name.upper()} LANGUAGE.
Avoid general phrases. Focus on the essence of "{topic}".

250-300 words. Briefly cover:
- Relevance of the topic
- Scientific and practical significance
- Brief theoretical basis

Professional academic style. Plain text only, no markdown."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write concise, focused introductions. No filler."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.7
            )
            return clean_text(response.strip())
        except Exception as e:
            logger.error(f"Error generating diploma intro: {e}")
            return ""

    async def _generate_diploma_intro_points(self, topic: str, language: str) -> Dict[str, str]:
        """Generate introduction points for diploma work (Subject, Object, Goal, Tasks, etc.)"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi diplom ishi uchun quyidagi 6 ta punktga juda batafsil va aynan mavzuga asoslangan akademik tarif bering. 
DIQQAT: Umumiy gaplardan qoching, har bir punkt aynan "{topic}" mavzusining ichki jihatlarini, uning ilmiy va amaliy ahamiyatini yoritib berishi shart. 

Punktlar (har biri kamida 40-50 so'zdan iborat bo'lsin):
1. Diplom ishining predmeti (Mavzuning qaysi jihatlari o'rganiladi?).
2. Diplom ishining obyekti (Mavzu qaysi soha yoki tushunchaga tegishli?).
3. Mavzuning o'rganilganlik darajasi (Hozirgi kunda bu mavzu qanchalik o'rganilgan?).
4. Diplom ishining maqsadi (Tadqiqotdan ko'zlangan asosiy natija nima?).
5. Diplom ishining vazifalari (Maqsadga erishish uchun bajarilishi kerak bo'lgan bosqichlarni punktma-punkt yozing).
6. Diplom ishining tarkibiy tuzilishi (Kirish, bo'limlar va xulosaning qisqacha tavsifi).

JSON formatda javob bering:
{{
  "point_1": "konkret mavzu predmeti haqida chuqur tahlil...",
  "point_2": "mavzu obyekti haqida batafsil ma'lumot...",
  "point_3": "ilmiy daraja tahlili...",
  "point_4": "aniq maqsad tarifi...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "tuzilish bayoni..."
}}"""
            elif language == "ru":
                prompt = f"""Дайте подробное академическое описание следующих 6 пунктов для дипломной работы по теме "{topic}". 
ВНИМАНИЕ: Избегайте общих фраз. Каждый пункт должен быть глубоко связан именно с темой "{topic}".

Пункты (минимум 40-50 слов каждый):
1. Предмет дипломной работы (какие именно стороны темы изучаются?).
2. Объект дипломной работы (к какой области или понятию относится тема?).
3. Степень изученности темы (насколько глубоко эта тема изучена на данный момент?).
4. Цель дипломной работы (основной ожидаемый результат исследования?).
5. Задачи дипломной работы (напишите по пунктам шаги для достижения цели).
6. Структура дипломной работы (краткое описание введения, глав и заключения).

Ответьте в формате JSON:
{{
  "point_1": "глубокий анализ предмета темы...",
  "point_2": "подробное описание объекта темы...",
  "point_3": "анализ научной степени изученности...",
  "point_4": "описание конкретной цели...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "описание структуры..."
}}"""
            else:
                prompt = f"""Provide detailed academic descriptions for the following 6 points for a diploma work on "{topic}".
ATTENTION: Avoid general phrases. Each point must be deeply connected specifically to the topic "{topic}".

Points (at least 40-50 words each):
1. Subject of the diploma work (what specific aspects of the topic are studied?).
2. Object of the diploma work (what area or concept does the topic belong to?).
3. Degree of study of the topic (how well is this topic studied currently?).
4. Goal of the diploma work (what is the main expected result of the study?).
5. Tasks of the diploma work (write point by point steps to achieve the goal).
6. Structure of the diploma work (brief description of introduction, chapters, and conclusion).

Respond in JSON format:
{{
  "point_1": "deep analysis of the topic subject...",
  "point_2": "detailed description of the topic object...",
  "point_3": "scientific study degree analysis...",
  "point_4": "specific goal description...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "structure description..."
}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )
            import re as _re_json
            content_str = response.strip()
            m = _re_json.search(r'\{.*\}', content_str, _re_json.DOTALL)
            if m:
                content_str = m.group()
            return json.loads(content_str)
        except Exception as e:
            logger.error(f"Error generating diploma intro points: {e}")
            return {f"point_{i}": "" for i in range(1, 7)}

    async def generate_diploma_work_content(self, topic: str, chapters: int, language: str, min_pages: int = 20, max_pages: int = 25) -> Dict:
        """Generate diploma work content — same structure as course work but with diploma-specific prompts
        and per-chapter table generation."""
        try:
            content = {
                "title": topic,
                "chapters": [],
                "introduction": "",
                "intro_points": {},
                "conclusion": "",
                "references": []
            }

            # Calculate word target based on target page range.
            # Fixed overhead (title, TOC, intro, conclusion, refs): ~8 pages.
            FIXED_PAGES = 8
            WORDS_PER_PAGE = 280
            total_subsections = chapters * 3
            content_pages = max(min_pages - FIXED_PAGES, 10)
            words_needed = content_pages * WORDS_PER_PAGE
            words_per_sub = words_needed // total_subsections
            low = int(words_per_sub * 0.9 // 50 * 50)
            high = int(words_per_sub * 1.1 // 50 * 50) + 50
            low = max(low, 350)
            high = max(high, low + 100)
            dw_word_target = f"{low}-{high}"

            chapter_titles = await self._generate_chapter_titles(topic, chapters, language)

            content["introduction"] = await self._generate_diploma_intro(topic, language)
            content["intro_points"] = await self._generate_diploma_intro_points(topic, language)

            for i, chapter_title in enumerate(chapter_titles, 1):
                chapter = {
                    "number": i,
                    "title": chapter_title,
                    "subsections": []
                }
                subsection_titles = await self._generate_subsection_titles(topic, chapter_title, language)
                for j, sub_title in enumerate(subsection_titles[:3], 1):
                    sub_content = await self._generate_subsection_content(topic, chapter_title, sub_title, language, dw_word_target)
                    chapter["subsections"].append({
                        "number": f"{i}.{j}",
                        "title": sub_title,
                        "content": sub_content
                    })
                content["chapters"].append(chapter)

            # Generate table per chapter using chapter-specific title
            for i, chapter in enumerate(content["chapters"], 1):
                chapter_topic = f"{topic} — {chapter['title']}"
                content[f"table_data_{i}"] = await self.generate_table_data(chapter_topic, i, language)

            content["conclusion"] = await self._generate_course_conclusion(topic, language)
            content["references"] = await self._generate_references(topic, language)

            return content

        except Exception as e:
            logger.error(f"Error generating diploma work content: {e}")
            raise

    async def generate_dissertation_content(self, topic: str, chapters: int, language: str, min_pages: int = 60, max_pages: int = 70) -> Dict:
        """Generate master's dissertation content.
        Structure: bilingual annotation, intro (10 points), chapters (>=3), conclusion,
        references (categorized), glossary, appendices.
        Word target per subsection is calculated from target page range.
        """
        try:
            content = {
                "title": topic,
                "chapters": [],
                "introduction": "",
                "intro_points": {},
                "conclusion": "",
                "conclusion_points": [],
                "references": [],
                "glossary_terms": [],
                "appendices": [],
            }

            # Fixed sections (title, TOC, intro+points, conclusion+points, refs,
            # glossary, appendices) use ~15 pages. Annotation was removed.
            # Remaining pages are filled by chapter subsections.
            # ~250 words per page (14pt Times New Roman, 1.5 spacing).
            # Target the UPPER end of the user-selected range and add a 25%
            # buffer because LLMs typically under-deliver vs. word targets.
            FIXED_PAGES = 15
            WORDS_PER_PAGE = 250
            subsections_per_chapter = 3
            total_subsections = chapters * subsections_per_chapter

            target_pages = int(max_pages * 1.25)
            content_pages_needed = max(target_pages - FIXED_PAGES, 30)
            words_needed = content_pages_needed * WORDS_PER_PAGE
            words_per_sub = words_needed // total_subsections

            # Round to a clean "low-high" range (target..+15%)
            low = int(words_per_sub // 50 * 50)
            high = int(words_per_sub * 1.15 // 50 * 50) + 50
            low = max(low, 1200)
            high = max(high, low + 200)
            word_target = f"{low}-{high}"

            chapter_titles = await self._generate_chapter_titles(topic, chapters, language)
            content["introduction"] = await self._generate_graduation_intro(topic, language)
            content["intro_points"] = await self._generate_dissertation_intro_points(topic, language)

            for i, chapter_title in enumerate(chapter_titles, 1):
                chapter = {"number": i, "title": chapter_title, "subsections": []}
                subsection_titles = await self._generate_subsection_titles(topic, chapter_title, language)
                for j, sub_title in enumerate(subsection_titles[:subsections_per_chapter], 1):
                    sub_content = await self._generate_subsection_content(topic, chapter_title, sub_title, language, word_target)
                    chapter["subsections"].append({
                        "number": f"{i}.{j}",
                        "title": sub_title,
                        "content": sub_content
                    })
                content["chapters"].append(chapter)

            for i, chapter in enumerate(content["chapters"], 1):
                chapter_topic = f"{topic} — {chapter['title']}"
                content[f"table_data_{i}"] = await self.generate_table_data(chapter_topic, i, language)

            content["conclusion"] = await self._generate_course_conclusion(topic, language)
            content["conclusion_points"] = await self._generate_graduation_conclusion_points(topic, language)
            content["references"] = await self._generate_graduation_references(topic, language)
            content["glossary_terms"] = await self._generate_glossary_terms(topic, language)
            content["appendices"] = await self._generate_appendices(topic, language)

            return content

        except Exception as e:
            logger.error(f"Error generating dissertation content: {e}")
            raise

    async def _generate_dissertation_annotation(self, topic: str, language: str) -> tuple:
        """Generate bilingual annotation (study language + English) for dissertation."""
        try:
            native_label = {"uz": "Uzbek", "ru": "Russian", "en": "English"}.get(language, "Uzbek")
            if language == "uz":
                native_prompt = f""""{topic}" mavzusidagi magistrlik dissertatsiyasi uchun ANNOTATSIYA yozing.
150-200 so'z. Quyidagilarni qisqa ifodalang: tadqiqot maqsadi, asosiy vazifalar, qo'llanilgan metodlar, asosiy natijalar, ilmiy va amaliy ahamiyat.
Faqat oddiy matn, akademik uslub."""
            elif language == "ru":
                native_prompt = f"""Напишите АННОТАЦИЮ для магистерской диссертации по теме: "{topic}".
150-200 слов. Кратко: цель исследования, задачи, методы, основные результаты, научная и практическая значимость.
Только обычный текст, академический стиль."""
            else:
                native_prompt = f"""Write an ANNOTATION for a master's dissertation on: "{topic}".
150-200 words. Cover: research goal, tasks, methods used, main results, scientific and practical significance.
Plain academic text only."""

            english_prompt = f"""Write an ENGLISH ANNOTATION (abstract) for a master's dissertation titled: "{topic}".
150-200 words. Cover: research aim, objectives, methodology, key findings, theoretical and practical significance.
Plain academic English text only. Output ONLY the abstract text."""

            native_resp = await self._make_request(
                messages=[{"role": "system", "content": f"You write academic annotations in {native_label}."}, {"role": "user", "content": native_prompt}],
                max_tokens=900, temperature=0.7
            )
            english_resp = await self._make_request(
                messages=[{"role": "system", "content": "You write academic abstracts in English."}, {"role": "user", "content": english_prompt}],
                max_tokens=900, temperature=0.7
            )
            return clean_text(native_resp.strip()), clean_text(english_resp.strip())
        except Exception as e:
            logger.error(f"Error generating dissertation annotation: {e}")
            return "", ""

    async def _generate_dissertation_intro_points(self, topic: str, language: str) -> Dict[str, str]:
        """Generate 10 detailed introduction points for master's dissertation."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi magistrlik dissertatsiyasi uchun quyidagi 10 ta punktga batafsil akademik tarif bering.
Har bir punkt kamida 50-70 so'zdan iborat:
1. Mavzuning asoslanishi va dolzarbligi
2. Tadqiqot obyekti
3. Tadqiqot predmeti
4. Tadqiqotning maqsadi va vazifalari
5. Ilmiy yangiligi
6. Tadqiqotning asosiy masalalari va farazlari
7. Tadqiqot mavzusi bo'yicha adabiyotlar sharhi
8. Qo'llanilgan metodikaning tavsifi
9. Tadqiqot natijalarining nazariy va amaliy ahamiyati
10. Ish tuzilmasining tavsifi

JSON formatda javob bering:
{{"point_1": "...", "point_2": "...", "point_3": "...", "point_4": "...", "point_5": "...", "point_6": "...", "point_7": "...", "point_8": "...", "point_9": "...", "point_10": "..."}}"""
            elif language == "ru":
                prompt = f"""Для магистерской диссертации по теме "{topic}" дайте подробное описание 10 пунктов.
Каждый пункт минимум 50-70 слов:
1. Обоснование темы и актуальность
2. Объект исследования
3. Предмет исследования
4. Цель и задачи исследования
5. Научная новизна
6. Основные вопросы и гипотезы исследования
7. Обзор литературы по теме
8. Описание применённой методики
9. Теоретическая и практическая значимость результатов
10. Описание структуры работы

JSON: {{"point_1": "...", ..., "point_10": "..."}}"""
            else:
                prompt = f"""For a master's dissertation on "{topic}", provide detailed descriptions for 10 points.
Each at least 50-70 words:
1. Justification and relevance of the topic
2. Object of research
3. Subject of research
4. Goals and tasks of research
5. Scientific novelty
6. Main research questions and hypotheses
7. Literature review on the topic
8. Description of methodology used
9. Theoretical and practical significance of results
10. Description of work structure

JSON: {{"point_1": "...", ..., "point_10": "..."}}"""
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2800, temperature=0.7
            )
            import re as _re_json
            content_str = response.strip()
            m = _re_json.search(r'\{.*\}', content_str, _re_json.DOTALL)
            if m:
                content_str = m.group()
            return json.loads(content_str)
        except Exception as e:
            logger.error(f"Error generating dissertation intro points: {e}")
            return {f"point_{i}": "" for i in range(1, 11)}

    @staticmethod
    def _int_to_roman(n: int) -> str:
        """Convert integer to Roman numeral string."""
        vals = [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),
                (50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
        result = ''
        for val, sym in vals:
            while n >= val:
                result += sym
                n -= val
        return result

    async def generate_graduation_work_content(self, topic: str, chapters: int, language: str, min_pages: int = 40, max_pages: int = 50, manual_plan: list = None) -> Dict:
        """Generate graduation qualifying work (bitiruv malakaviy ishi) content.
        Structure: intro, intro_points, chapters (with subsections), conclusion_points,
        references (categorized), glossary_terms, appendices.
        manual_plan: optional list of dicts [{"title": ..., "subsections": [...]}] from user input.
        """
        try:
            content = {
                "title": topic,
                "chapters": [],
                "introduction": "",
                "intro_points": {},
                "conclusion": "",
                "conclusion_points": [],
                "references": [],
                "glossary_terms": [],
                "appendices": [],
            }

            # Fixed overhead (title, TOC, intro+points, conclusion, refs, glossary, appendices): ~15 pages.
            FIXED_PAGES = 15
            WORDS_PER_PAGE = 280
            total_subsections = chapters * 3
            content_pages = max(min_pages - FIXED_PAGES, 15)
            words_needed = content_pages * WORDS_PER_PAGE
            words_per_sub = words_needed // total_subsections
            low = int(words_per_sub * 0.9 // 50 * 50)
            high = int(words_per_sub * 1.1 // 50 * 50) + 50
            low = max(low, 400)
            high = max(high, low + 150)
            word_target = f"{low}-{high}"

            # ── Step 1: Get chapter + subsection titles (manual or AI) ───────────
            if manual_plan:
                chapter_titles = [ch["title"] for ch in manual_plan]
                all_subsection_titles = [ch.get("subsections", [])[:3] for ch in manual_plan]
            else:
                chapter_titles = await self._generate_chapter_titles(topic, chapters, language, century_conditional=True)
                all_subsection_titles = []
                for chapter_title in chapter_titles:
                    sub_titles = await self._generate_subsection_titles(topic, chapter_title, language, century_conditional=True)
                    all_subsection_titles.append(sub_titles[:3])

            # ── Step 2: Generate introduction ────────────────────────────────────
            content["introduction"] = await self._generate_graduation_intro(topic, language)
            content["intro_points"] = await self._generate_graduation_intro_points(topic, language)

            # ── Step 3: Generate subsection content ──────────────────────────────
            for i, (chapter_title, sub_titles) in enumerate(zip(chapter_titles, all_subsection_titles), 1):
                chapter = {"number": i, "title": chapter_title, "subsections": []}
                for j, sub_title in enumerate(sub_titles, 1):
                    sub_content = await self._generate_subsection_content(
                        topic, chapter_title, sub_title, language, word_target,
                        century_conditional=True
                    )
                    chapter["subsections"].append({
                        "number": f"{i}.{j}",
                        "title": sub_title,
                        "content": sub_content
                    })
                content["chapters"].append(chapter)

            for i, chapter in enumerate(content["chapters"], 1):
                chapter_topic = f"{topic} — {chapter['title']}"
                content[f"table_data_{i}"] = await self.generate_table_data(chapter_topic, i, language)

            content["conclusion"] = await self._generate_course_conclusion(topic, language)
            content["conclusion_points"] = await self._generate_graduation_conclusion_points(topic, language)
            content["references"] = await self._generate_graduation_references(topic, language)
            content["glossary_terms"] = await self._generate_glossary_terms(topic, language)
            content["appendices"] = await self._generate_appendices(topic, language)

            return content

        except Exception as e:
            logger.error(f"Error generating graduation work content: {e}")
            raise

    async def _generate_graduation_intro(self, topic: str, language: str) -> str:
        """Generate graduation work introduction covering relevance, goals, structure."""
        try:
            target_lang = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi bitiruv malakaviy ishi uchun ilmiy kirish qismini yozing.
300-400 so'z. Quyidagilarni qamrab oling:
- Mavzuning dolzarbligi va zamonaviy ahamiyati
- Tadqiqotning ilmiy va amaliy ahamiyati
- Mavzuning nazariy asoslari
Professional akademik uslub. Faqat oddiy matn."""
            elif language == "ru":
                prompt = f"""Напишите введение для выпускной квалификационной работы по теме: "{topic}".
300-400 слов. Охватите:
- Актуальность и современное значение темы
- Научная и практическая значимость
- Теоретические основы
Профессиональный академический стиль. Только обычный текст."""
            else:
                prompt = f"""Write an introduction for a graduation qualifying work on: "{topic}".
THE ENTIRE TEXT MUST BE IN {target_lang.upper()} LANGUAGE.
300-400 words. Cover: relevance, scientific significance, theoretical basis.
Professional academic style. Plain text only."""
            response = await self._make_request(
                messages=[{"role": "system", "content": "You are an academic writer. Write focused scientific introductions."}, {"role": "user", "content": prompt}],
                max_tokens=1500, temperature=0.7
            )
            return clean_text(response.strip())
        except Exception as e:
            logger.error(f"Error generating graduation intro: {e}")
            return ""

    async def _generate_graduation_intro_points(self, topic: str, language: str) -> Dict[str, str]:
        """Generate 8 detailed introduction points for graduation work."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi bitiruv malakaviy ishi uchun quyidagi 8 ta punktga batafsil akademik tarif bering.
Har bir punkt kamida 40-50 so'zdan iborat bo'lsin:
1. Tadqiqotning dolzarbligi
2. Tadqiqot obyekti
3. Tadqiqot predmeti
4. Tadqiqotning maqsadi
5. Tadqiqot vazifalari (bandlarda yozing)
6. Tadqiqot metodlari
7. Ishning ilmiy yangiligi
8. Ishning tarkibiy tuzilishi

JSON formatda javob bering:
{{"point_1": "...", "point_2": "...", "point_3": "...", "point_4": "...", "point_5": "1. ...\\n2. ...", "point_6": "...", "point_7": "...", "point_8": "..."}}"""
            elif language == "ru":
                prompt = f"""Для выпускной квалификационной работы по теме "{topic}" дайте подробное описание 8 пунктов.
Каждый пункт минимум 40-50 слов:
1. Актуальность исследования
2. Объект исследования
3. Предмет исследования
4. Цель исследования
5. Задачи исследования (по пунктам)
6. Методы исследования
7. Научная новизна работы
8. Структура работы

JSON формат:
{{"point_1": "...", "point_2": "...", "point_3": "...", "point_4": "...", "point_5": "1. ...\\n2. ...", "point_6": "...", "point_7": "...", "point_8": "..."}}"""
            else:
                prompt = f"""For a graduation qualifying work on "{topic}", provide detailed descriptions for 8 points.
Each point at least 40-50 words:
1. Relevance of research
2. Object of research
3. Subject of research
4. Goal of research
5. Tasks of research (in numbered points)
6. Research methods
7. Scientific novelty
8. Structure of work

JSON format:
{{"point_1": "...", "point_2": "...", "point_3": "...", "point_4": "...", "point_5": "1. ...\\n2. ...", "point_6": "...", "point_7": "...", "point_8": "..."}}"""
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000, temperature=0.7
            )
            import re as _re_json
            content_str = response.strip()
            m = _re_json.search(r'\{.*\}', content_str, _re_json.DOTALL)
            if m:
                content_str = m.group()
            return json.loads(content_str)
        except Exception as e:
            logger.error(f"Error generating graduation intro points: {e}")
            return {f"point_{i}": "" for i in range(1, 9)}

    async def _generate_graduation_conclusion_points(self, topic: str, language: str) -> list:
        """Generate numbered conclusion + recommendations for graduation work."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi bitiruv malakaviy ishi uchun xulosa va takliflar yozing.
8-10 ta raqamlangan xulosa bandi (har biri 2-3 gap). Keyin 4-5 ta tavsiya (taklif).
JSON formatda: {{"conclusions": ["1. ...", "2. ...", ...], "recommendations": ["1. ...", "2. ...", ...]}}"""
            elif language == "ru":
                prompt = f"""Для ВКР по теме "{topic}" напишите выводы и рекомендации.
8-10 пронумерованных выводов (каждый 2-3 предложения). Затем 4-5 рекомендаций.
JSON: {{"conclusions": ["1. ...", "2. ...", ...], "recommendations": ["1. ...", "2. ...", ...]}}"""
            else:
                prompt = f"""For graduation work on "{topic}", write conclusions and recommendations.
8-10 numbered conclusions (each 2-3 sentences). Then 4-5 recommendations.
JSON: {{"conclusions": ["1. ...", "2. ...", ...], "recommendations": ["1. ...", "2. ...", ...]}}"""
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500, temperature=0.7
            )
            cs = response.strip()
            for p in ["```json", "```"]:
                if cs.startswith(p): cs = cs[len(p):]
            if cs.endswith("```"): cs = cs[:-3]
            data = json.loads(cs.strip())
            result = data.get("conclusions", []) + [""] + data.get("recommendations", [])
            return result
        except Exception as e:
            logger.error(f"Error generating graduation conclusion points: {e}")
            return []

    async def _generate_graduation_references(self, topic: str, language: str) -> list:
        """Generate categorized references list for graduation work."""
        try:
            city_rule_uz = "Shahar nomini TO'LIQ yozing — hech qachon qisqartma ishlatmang. \"T:\", \"T.\", \"B:\", \"B.\" emas, balki \"Toshkent:\", \"Bishkek:\", \"Moskva:\" deb yozing."
            city_rule_ru = "Название города пишите ПОЛНОСТЬЮ — никаких сокращений. Не \"М.:\", \"М.\", \"Т.:\", а полностью: \"Москва:\", \"Ташкент:\", \"Бишкек:\"."
            city_rule_en = "Write city names IN FULL — never abbreviate. Not \"M.\", \"T.\", \"L.\" but \"Moscow\", \"Tashkent\", \"London\"."

            if language == "uz":
                prompt = f""""{topic}" mavzusidagi bitiruv malakaviy ishi uchun foydalanilgan adabiyotlar ro'yxatini tuzib bering.
Quyidagi toifalar bo'yicha taqsimlang (har toifada kamida 3-5 manba):
1. Me'yoriy-huquqiy hujjatlar
2. Darsliklar va o'quv qo'llanmalar
3. Ilmiy maqolalar va dissertatsiyalar
4. Internet manbalar

MUHIM: {city_rule_uz}

JSON formatda: {{"legal": ["..."], "textbooks": ["..."], "articles": ["..."], "internet": ["..."]}}"""
            elif language == "ru":
                prompt = f"""Составьте список литературы для ВКР по теме "{topic}".
Категории (минимум 3-5 источников в каждой):
1. Нормативно-правовые акты
2. Учебники и учебные пособия
3. Научные статьи и диссертации
4. Интернет-источники

ВАЖНО: {city_rule_ru}

JSON: {{"legal": ["..."], "textbooks": ["..."], "articles": ["..."], "internet": ["..."]}}"""
            else:
                prompt = f"""Create a categorized reference list for graduation work on "{topic}".
Categories (minimum 3-5 sources each):
1. Legal documents and regulations
2. Textbooks and manuals
3. Research articles and dissertations
4. Internet sources

IMPORTANT: {city_rule_en}

JSON: {{"legal": ["..."], "textbooks": ["..."], "articles": ["..."], "internet": ["..."]}}"""
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500, temperature=0.7
            )
            cs = response.strip()
            for p in ["```json", "```"]:
                if cs.startswith(p): cs = cs[len(p):]
            if cs.endswith("```"): cs = cs[:-3]
            data = json.loads(cs.strip())
            refs = []
            labels = {
                "uz": {"legal": "Me'yoriy-huquqiy hujjatlar", "textbooks": "Darsliklar va o'quv qo'llanmalar", "articles": "Ilmiy maqolalar", "internet": "Internet manbalar"},
                "ru": {"legal": "Нормативно-правовые акты", "textbooks": "Учебники и пособия", "articles": "Научные статьи", "internet": "Интернет-источники"},
                "en": {"legal": "Legal documents", "textbooks": "Textbooks", "articles": "Research articles", "internet": "Internet sources"},
            }.get(language, {})
            # Put textbooks and articles FIRST so footnote cycling starts with
            # academic sources, not legal/regulatory documents.
            # Legal docs and internet sources go last (they appear in bibliography
            # but are rarely the best footnote for a content section).
            for key in ["textbooks", "articles", "internet", "legal"]:
                items = data.get(key, [])
                if items:
                    refs.append(f"__CATEGORY__{labels.get(key, key)}")
                    refs.extend(self._expand_city_abbrevs(i) for i in items)
            return refs
        except Exception as e:
            logger.error(f"Error generating graduation references: {e}")
            return await self._generate_references(topic, language)

    async def _generate_glossary_terms(self, topic: str, language: str) -> list:
        """Generate glossary terms for graduation work."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi bitiruv malakaviy ishida ishlatiladigan 12-15 ta asosiy ilmiy va texnik atamalarning izohli lug'atini tuzing.
JSON: {{"terms": [{{"term": "...", "definition": "..."}}]}}"""
            elif language == "ru":
                prompt = f"""Составьте глоссарий из 12-15 основных терминов для ВКР по теме "{topic}".
JSON: {{"terms": [{{"term": "...", "definition": "..."}}]}}"""
            else:
                prompt = f"""Create a glossary of 12-15 key terms for a graduation work on "{topic}".
JSON: {{"terms": [{{"term": "...", "definition": "..."}}]}}"""
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500, temperature=0.7
            )
            cs = response.strip()
            for p in ["```json", "```"]:
                if cs.startswith(p): cs = cs[len(p):]
            if cs.endswith("```"): cs = cs[:-3]
            data = json.loads(cs.strip())
            return data.get("terms", [])
        except Exception as e:
            logger.error(f"Error generating glossary terms: {e}")
            return []

    async def _generate_appendices(self, topic: str, language: str) -> list:
        """Generate appendix descriptions for graduation work."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi bitiruv malakaviy ishi uchun 3-4 ta ilova (appendix) tavsifini yozing.
Har bir ilova uchun sarlavha va qisqacha tavsif bering.
JSON: {{"appendices": [{{"title": "A-ilova. ...", "description": "..."}}]}}"""
            elif language == "ru":
                prompt = f"""Для ВКР по теме "{topic}" опишите 3-4 приложения.
Для каждого приложения — заголовок и краткое описание.
JSON: {{"appendices": [{{"title": "Приложение А. ...", "description": "..."}}]}}"""
            else:
                prompt = f"""For a graduation work on "{topic}", describe 3-4 appendices.
For each — title and brief description.
JSON: {{"appendices": [{{"title": "Appendix A. ...", "description": "..."}}]}}"""
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800, temperature=0.7
            )
            cs = response.strip()
            for p in ["```json", "```"]:
                if cs.startswith(p): cs = cs[len(p):]
            if cs.endswith("```"): cs = cs[:-3]
            data = json.loads(cs.strip())
            return data.get("appendices", [])
        except Exception as e:
            logger.error(f"Error generating appendices: {e}")
            return []

    async def _generate_course_conclusion(self, topic: str, language: str) -> str:
        """Generate course work conclusion (~400 words)"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi kurs ishi uchun xulosa yozing.

400-500 so'z. Quyidagilarni qamrab oling:
- Asosiy topilmalar va natijalar
- Tadqiqot xulosalari
- Amaliy tavsiyalar
- Kelajakda tadqiq qilish yo'nalishlari

Professional akademik uslubda yozing."""
            else:
                prompt = f"""Write a scientific conclusion for a course work on the topic: "{topic}".
THE ENTIRE TEXT MUST BE IN {target_lang_name.upper()} LANGUAGE. 

400-500 words. Cover:
- Main findings and results
- Research conclusions
- Practical recommendations
- Directions for future research

Professional academic style."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer specializing in course work conclusions."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.7
            )
            
            return clean_text(response.strip())
            
        except Exception as e:
            logger.error(f"Error generating course conclusion: {e}")
            return ""

    async def _generate_footnote(self, topic: str, context: str, language: str) -> str:
        """Generate a footnote reference for a subsection"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi, "{context}" konteksti uchun bitta akademik snoska (footnote) yarating.

Masalan:
Karimov I.A. "Yuksak ma'naviyat – yengilmas kuch". Toshkent: Ma'naviyat, 2008. 45-bet.

Faqat bitta manba yarating. Real ko'rinishda bo'lsin."""
            elif language == "ru":
                prompt = f"""Создайте одну академическую сноску для темы "{topic}", контекст "{context}".

Пример:
Иванов А.Б. "Современные технологии". Москва: Наука, 2020. С. 45.

Создайте только одну ссылку. Должна выглядеть реалистично."""
            else:
                prompt = f"""Create one academic footnote for topic "{topic}", context "{context}".

Example:
Smith, J. "Modern Technologies". New York: Academic Press, 2020. p. 45.

Create only one reference. Should look realistic."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.8
            )
            
            return clean_text(response.strip())
            
        except Exception as e:
            logger.error(f"Error generating footnote: {e}")
            return ""

    async def generate_table_data(self, topic: str, section_num: int, language: str) -> dict:
        """Generate a table for the topic using JSON format for reliable parsing."""
        try:
            # Kitob rejimida topic ichida kitob mazmuni ham bo'ladi — ajratib olamiz
            clean_topic = topic
            book_excerpt = ""
            for marker in self._BOOK_MODE_MARKERS:
                if marker in topic:
                    # Mavzuni (birinchi qator) ajrat
                    clean_topic = topic.split("\n")[0].strip()
                    # Kitob mazmunini ajrat
                    bc_idx = topic.find("BOOK CONTENT:")
                    if bc_idx != -1:
                        book_excerpt = topic[bc_idx + len("BOOK CONTENT:"):].strip()[:8000]
                    break

            json_template = '{{"headers": ["Ustun 1", "Ustun 2", "Ustun 3", "Ustun 4"], "rows": [["...","...","...","..."],["...","...","...","..."],["...","...","...","..."],["...","...","...","..."],["...","...","...","..."],["...","...","...","..."]], "description": "Jadval tavsifi"}}'

            if book_excerpt:
                # Kitob mazmunidan jadval yasash
                if language == "uz":
                    prompt = (
                        f"Quyidagi kitob mazmunidan '{clean_topic}' mavzusiga oid jadval yaratib ber. "
                        f"4 ta ustun, 6 ta qator (sarlavha qatori hisoblanmaydi). "
                        f"Ustun sarlavhalarini mavzuga mos ravishda o'zing tanla. "
                        f"Kitob ASOSIY MANBA. Har bir katakda mazmunli ma'lumot yoz. "
                        f"Faqat JSON formatda javob ber:\n{json_template}\n\nKITOB MAZMUNI:\n{book_excerpt}"
                    )
                elif language == "ru":
                    prompt = (
                        f"На основе книги создай таблицу по теме '{clean_topic}'. "
                        f"4 столбца, 6 строк (без учёта заголовка). "
                        f"Заголовки столбцов выбери сам. В каждой ячейке содержательная информация. "
                        f"Только в JSON формате:\n{json_template}\n\nСОДЕРЖАНИЕ КНИГИ:\n{book_excerpt}"
                    )
                else:
                    prompt = (
                        f"Based on the book content, create a table about '{clean_topic}'. "
                        f"4 columns, 6 rows (excluding header). "
                        f"Choose column headers based on the topic. Each cell: meaningful content. "
                        f"Respond only in JSON:\n{json_template}\n\nBOOK CONTENT:\n{book_excerpt}"
                    )
            else:
                # Oddiy rejim — mavzu bo'yicha jadval
                if language == "uz":
                    prompt = (
                        f'"{clean_topic}" mavzusi bo\'yicha jadval yaratib ber. '
                        f"4 ta ustun, 6 ta qator (sarlavha qatori hisoblanmaydi). "
                        f"Ustun sarlavhalarini mavzuga mos ravishda o'zing tanla. "
                        f"Har bir katakda mazmunli ma'lumot yoz. "
                        f"Faqat JSON formatda javob ber:\n{json_template}"
                    )
                elif language == "ru":
                    prompt = (
                        f'Создай таблицу по теме "{clean_topic}". '
                        f"4 столбца, 6 строк (без учёта заголовка). "
                        f"Заголовки столбцов выбери сам. В каждой ячейке содержательная информация. "
                        f"Только в JSON формате:\n{json_template}"
                    )
                else:
                    prompt = (
                        f'Create a table about "{clean_topic}". '
                        f"4 columns, 6 rows (excluding header). "
                        f"Choose column headers based on the topic. Each cell: meaningful content. "
                        f"Respond only in JSON:\n{json_template}"
                    )

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "Respond with valid JSON only. No markdown, no extra text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.5
            )
            
            content = response.strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            content = content.strip()
            
            result = self._parse_json_safely(content)
            
            headers = result.get('headers', [])
            rows = result.get('rows', [])
            description = result.get('description', '')
            
            if not headers or len(headers) < 2:
                headers = ["Omil", "Xususiyati", "Ta'siri", "Natija"]
            # Trim to max 4 columns
            if len(headers) > 4:
                headers = headers[:4]
            # Trim to max 6 rows, pad if fewer
            rows = [r[:len(headers)] for r in rows[:6]]
            if not rows:
                rows = [["—"] * len(headers)]
            if not description:
                description = f"Ushbu jadvalda {topic} mavzusiga oid asosiy ko'rsatkichlar keltirilgan."

            logger.info(f"Table generated: {len(headers)} headers, {len(rows)} rows")
            return {"headers": headers, "rows": rows, "description": description}
            
        except Exception as e:
            logger.error(f"Error generating table data: {e}")
            return {
                "headers": ["Omil", "Xususiyati", "Ta'siri", "Natija"],
                "rows": [
                    ["Asosiy omil", "Muhim xususiyat", "Sezilarli ta'sir", "Ijobiy"],
                    ["Ikkinchi omil", "Muhim jihat", "O'rta darajada", "Barqaror"],
                    ["Uchinchi omil", "Asosiy belgi", "Yuqori ta'sir", "Samarali"],
                    ["To'rtinchi omil", "Muhim ko'rsatkich", "Sezilarli o'zgarish", "Yaxshi"],
                    ["Beshinchi omil", "Asosiy jihat", "O'rta ta'sir", "Muvaffaqiyatli"]
                ],
                "description": f"Ushbu jadvalda {topic} mavzusiga oid asosiy ko'rsatkichlar keltirilgan."
            }

    async def _web_search(self, query: str, max_results: int = 5) -> str:
        """Search the web and return results as text."""
        try:
            import asyncio
            from duckduckgo_search import DDGS
            results = await asyncio.to_thread(DDGS().text, query, max_results=max_results)
            if not results:
                return ""
            search_text = ""
            for r in results:
                title = r.get('title', '')
                body = r.get('body', '')
                search_text += f"{title}: {body}\n"
            logger.info(f"Web search for '{query}': found {len(results)} results")
            return search_text
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return ""

    async def generate_stats_table(self, topic: str, language: str) -> dict:
        """Generate a statistics table using real-time web search data."""
        try:
            from datetime import datetime
            current_year = datetime.now().year
            prev_year = current_year - 1

            search_query = f"{topic} latest statistics data numbers {current_year}"
            search_results = await self._web_search(search_query, max_results=8)
            
            if not search_results:
                search_query2 = f"{topic} statistics facts figures {prev_year} {current_year}"
                search_results = await self._web_search(search_query2, max_results=5)
            
            if not search_results:
                search_query3 = f"{topic} статистика данные цифры {current_year}"
                search_results = await self._web_search(search_query3, max_results=5)

            web_context = ""
            if search_results:
                web_context = f"\n\nBUGUN {current_year}-YIL. INTERNETDAN TOPILGAN ENG SO'NGI MA'LUMOTLAR:\n{search_results}\n\nMUHIM: Yuqoridagi internet ma'lumotlaridan foydalanib haqiqiy raqamlarni jadvalga kiritgin. Yillarni ham internetdagi eng so'nggi yillarga mos qil. Eski yillarni (2022, 2023) emas, eng yangi topilgan yillarni ishlat!"
            else:
                web_context = f"\n\nBugun {current_year}-yil. Eng so'nggi mavjud statistik ma'lumotlarni ishlat."

            if language == "uz":
                prompt = f""""{topic}" mavzusi bo'yicha faqat raqamlar, statistika va formulalardan iborat mavzuga ENG MOS jadvalni yarat.
{web_context}

MUHIM QOIDALAR:
- Ustun soni va qator sonini o'zing belgilagin — mavzuga qancha mos bo'lsa shuncha
- Har bir katakda faqat raqam, foiz, formula yoki qisqa statistik ma'lumot bo'lsin
- Uzun gaplar yozma
- Internetdan topilgan HAQIQIY raqamlarni ishlat
- Ustun sarlavhalarida yillarni internetdagi eng so'nggi ma'lumotlarga mos qil (masalan {prev_year} va {current_year})

Faqat JSON formatda javob ber:
{{"headers": ["Ko'rsatkich", "Yil/davr", "O'zgarish"], "rows": [["ma'lumot","ma'lumot","ma'lumot"], ["ma'lumot","ma'lumot","ma'lumot"]], "description": "Jadval haqida tushuntirish"}}"""

            elif language == "ru":
                prompt = f"""Создай НАИБОЛЕЕ ПОДХОДЯЩУЮ таблицу по теме "{topic}" только с числами, статистикой и формулами.
{web_context}

ВАЖНЫЕ ПРАВИЛА:
- Количество строк и столбцов выбираешь сам — сколько нужно для темы
- Каждая ячейка должна содержать только число, процент, формулу
- Без длинных предложений
- Используй РЕАЛЬНЫЕ цифры из интернет-данных
- В заголовках столбцов используй самые свежие годы из найденных данных (например {prev_year} и {current_year})

Ответ только в JSON формате:
{{"headers": ["Показатель", "Год/период", "Изменение"], "rows": [["данные","данные","данные"], ["данные","данные","данные"]], "description": "Пояснение"}}"""

            else:
                prompt = f"""Create the MOST APPROPRIATE table about "{topic}" containing only numbers, statistics and formulas.
{web_context}

IMPORTANT RULES:
- You freely choose the number of columns and rows — whatever fits the topic best
- Each cell must contain only a number, percentage, or formula
- No long sentences
- Use REAL figures from the internet data provided
- Use the most recent years found in the data for column headers (e.g. {prev_year} and {current_year})

Respond only in JSON format:
{{"headers": ["Indicator", "Year/period", "Change"], "rows": [["data","data","data"], ["data","data","data"]], "description": "Explanation"}}"""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": f"Today is {current_year}. You must respond with valid JSON only. Use ONLY real numbers and statistics from the provided web search data. Column headers for years must reflect the most recent data available - do NOT default to old years like 2022-2023. Use actual current data."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            content = response.strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            content = content.strip()
            
            result = self._parse_json_safely(content)
            
            headers = result.get('headers', [])
            rows = result.get('rows', [])
            description = result.get('description', '')
            
            if not headers or len(headers) < 2:
                headers = ["Ko'rsatkich", str(prev_year), str(current_year), "O'zgarish"]
            if not rows:
                rows = [["—"] * len(headers)]
            if not description:
                description = f"Ushbu jadvalda {topic} mavzusiga oid statistik ko'rsatkichlar keltirilgan."
            
            logger.info(f"Stats table generated with web data: {len(headers)} headers, {len(rows)} rows, search_found={bool(search_results)}")
            return {"headers": headers, "rows": rows, "description": description}
            
        except Exception as e:
            logger.error(f"Error generating stats table: {e}")
            from datetime import datetime
            cy = datetime.now().year
            py = cy - 1
            return {
                "headers": ["Ko'rsatkich", str(py), str(cy), "O'zgarish"],
                "rows": [
                    ["Umumiy hajm", "1250", "1480", "+18.4%"],
                    ["Samaradorlik", "72%", "85%", "+13%"],
                    ["O'sish sur'ati", "3.2%", "4.7%", "+1.5%"],
                    ["Xarajat", "450 mln", "520 mln", "+15.6%"],
                    ["Foyda", "180 mln", "230 mln", "+27.8%"]
                ],
                "description": f"Ushbu jadvalda {topic} mavzusiga oid statistik ko'rsatkichlar keltirilgan."
            }

    async def generate_presentation_table_data(self, topic: str, language: str) -> dict:
        """Generate 6-row (1 header + 5 data) x 4-column table for presentation slides.
        Uses simple pipe-delimited format for reliable AI parsing."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi bo'yicha 5 qatorli, 4 ustunli jadval tuz.

Jadval mavzuga to'liq mos bo'lsin. Har bir katak qisqa va mazmunli bo'lsin (1-5 so'z).

Faqat quyidagi formatda javob ber:
USTUNLAR: Ustun1 | Ustun2 | Ustun3 | Ustun4
QATOR1: matn | matn | matn | matn
QATOR2: matn | matn | matn | matn
QATOR3: matn | matn | matn | matn
QATOR4: matn | matn | matn | matn
QATOR5: matn | matn | matn | matn"""

            elif language == "ru":
                prompt = f"""Составь таблицу из 5 строк и 4 столбцов по теме "{topic}".

Таблица должна полностью соответствовать теме. Каждая ячейка — краткий содержательный текст (1-5 слов).

Ответ только в формате:
СТОЛБЦЫ: Столбец1 | Столбец2 | Столбец3 | Столбец4
СТРОКА1: текст | текст | текст | текст
СТРОКА2: текст | текст | текст | текст
СТРОКА3: текст | текст | текст | текст
СТРОКА4: текст | текст | текст | текст
СТРОКА5: текст | текст | текст | текст"""

            else:
                prompt = f"""Create a 5-row, 4-column table for the topic "{topic}".

Table must be fully relevant to the topic. Each cell should be brief and informative (1-5 words).

Respond only in this format:
COLUMNS: Column1 | Column2 | Column3 | Column4
ROW1: text | text | text | text
ROW2: text | text | text | text
ROW3: text | text | text | text
ROW4: text | text | text | text
ROW5: text | text | text | text"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.7
            )

            lines = response.strip().split('\n')
            headers = []
            rows = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.upper().startswith('USTUNLAR:') or line.upper().startswith('СТОЛБЦЫ:') or line.upper().startswith('COLUMNS:'):
                    parts = line.split(':', 1)[1].strip()
                    headers = [h.strip() for h in parts.split('|')]
                elif ':' in line:
                    parts = line.split(':', 1)[1].strip()
                    row = [c.strip() for c in parts.split('|')]
                    if len(row) >= 2:
                        rows.append(row[:4])

            if not headers or len(headers) < 2:
                if language == "ru":
                    headers = ["Показатель", "Значение", "Результат", "Примечание"]
                elif language == "en":
                    headers = ["Indicator", "Value", "Result", "Note"]
                else:
                    headers = ["Ko'rsatkich", "Qiymat", "Natija", "Izoh"]

            while len(rows) < 5:
                rows.append(["—", "—", "—", "—"])

            return {"headers": headers[:4], "rows": rows[:5]}

        except Exception as e:
            logger.error(f"Error generating presentation table data: {e}")
            if language == "ru":
                return {
                    "headers": ["Показатель", "2023", "2024", "Изменение"],
                    "rows": [["—"] * 4] * 5
                }
            elif language == "en":
                return {
                    "headers": ["Indicator", "2023", "2024", "Change"],
                    "rows": [["—"] * 4] * 5
                }
            else:
                return {
                    "headers": ["Ko'rsatkich", "2023", "2024", "O'zgarish"],
                    "rows": [["—"] * 4] * 5
                }

    async def generate_thesis_content(self, topic: str, language: str) -> Dict:
        """Generate thesis content with trilingual annotation/keywords/intro and rest in selected language"""
        try:
            target_lang = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            
            prompt = f"""Create a professional academic thesis (tezis) on topic: "{topic}".

            CRITICAL LANGUAGE RULE:
            - Annotation and Keywords must be written in THREE languages: Uzbek, then Russian, then English.
            - Each language block has: annotation (~100 words) + 10 keywords in that same language.
            - Introduction is in {target_lang} ONLY (not trilingual).
            - ALL OTHER SECTIONS (literature_review, main_intro, analysis, conclusion, references) must be written ONLY in {target_lang}.
            
            STRUCTURE:
            1. Topic title translated into 3 languages: Uzbek, Russian, English.
            2. Annotation + Keywords in 3 languages (each pair together):
               - Uzbek: Annotation (~100 words) followed by 10 keywords in Uzbek
               - Russian: Annotation (~100 words) followed by 10 keywords in Russian
               - English: Annotation (~100 words) followed by 10 keywords in English
            3. Introduction - ~100 words in {target_lang} ONLY (not trilingual). Include ONE footnote mark [1].
            4. Literature Review (in {target_lang} only) - ~400-500 words. Analyze what has been written about this topic in academic literature. For EACH of the 5-6 references, write a separate paragraph (60-80 words) explaining what that specific author/source contributes to the topic. Mention the author name and key findings from their work. Include ONE footnote mark [2] in this section.
            5. Main Part Introduction (in {target_lang} only) - ~100 words introducing the analysis and main discussion points.
            6. Main Part (in {target_lang} only) - A continuous, cohesive academic text (~800-1000 words) analyzing the topic comprehensively. Write as flowing paragraphs (4-5 paragraphs), NOT as bullet points or numbered lists. Each paragraph should smoothly transition into the next. Include footnote marks [3] and [4] naturally within the text.
            7. Conclusion (in {target_lang} only) - ~400 words providing final findings, summary and recommendations. Include ONE footnote mark [6] in this section.
            8. References - 6 real academic sources with actual authors, titles, publishers and years. These MUST match the sources discussed in the Literature Review section.
            
            RULES:
            - Professional academic tone throughout.
            - Total content must be around 5-6 pages (~2000-2500 words total).
            - No markdown formatting except bullets in main part.
            - Use plain text for content.
            - Footnote marks: Exactly 4 total: [1] in intro, [2] in literature review, [3] and [4] in main part. Plus [5] will be in table analysis and [6] in conclusion.
            - References must be realistic academic sources and must match the literature review.
            - YOU MUST RETURN ONLY VALID JSON.
            
            Respond in this EXACT JSON format:
            {{
                "topic_uz": "Topic title in Uzbek...",
                "topic_ru": "Topic title in Russian...",
                "topic_en": "Topic title in English...",
                "annotation_uz": "100 words annotation in Uzbek...",
                "keywords_uz": ["kalit1", "kalit2", ..., "kalit10"],
                "annotation_ru": "100 words annotation in Russian...",
                "keywords_ru": ["ключ1", "ключ2", ..., "ключ10"],
                "annotation_en": "100 words annotation in English...",
                "keywords_en": ["key1", "key2", ..., "key10"],
                "introduction": "100 words introduction in {target_lang} with [1]...",
                "literature_review": "400-500 words in {target_lang} analyzing each source with [2]...",
                "main_intro": "100 words in {target_lang} introducing the main analysis...",
                "analysis": "800-1000 words continuous academic text in {target_lang} with [3] and [4] footnotes...",
                "conclusion": "400 words in {target_lang} of final summary with [6]...",
                "references": ["Author. Title. City: Publisher, Year.", ...]
            }}"""

            messages = [
                {"role": "system", "content": "You are an academic researcher writing a thesis. You must output a valid JSON object following the provided structure strictly. Do not include any thought process (COT), just the JSON."},
                {"role": "user", "content": prompt}
            ]
            content_str = await self._make_request(
                messages=messages,
                max_tokens=8000,
                temperature=0.4,
                response_format={"type": "json_object"}
            )
            
            if content_str.startswith("```json"): content_str = content_str[7:]
            if content_str.startswith("```"): content_str = content_str[3:]
            if content_str.endswith("```"): content_str = content_str[:-3]
            
            result = self._parse_json_safely(content_str.strip())

            is_book_mode = any(marker in topic for marker in self._BOOK_MODE_MARKERS)
            
            table1 = await self.generate_table_data(topic, 1, language)
            if is_book_mode:
                table2 = await self.generate_table_data(topic, 2, language)
            else:
                table2 = await self.generate_stats_table(topic, language)
            
            table1_analysis = await self._generate_table_analysis(topic, table1, language)
            table2_analysis = await self._generate_table_analysis(topic, table2, language)
            
            logger.info(f"Thesis table1: {len(table1.get('headers', []))} cols, {len(table1.get('rows', []))} rows")
            logger.info(f"Thesis table2: {len(table2.get('headers', []))} cols, {len(table2.get('rows', []))} rows")
            
            result['table'] = table1
            result['table2'] = table2
            result['table_explanation'] = table1_analysis
            result['table2_explanation'] = table2_analysis
            
            return result
        except Exception as e:
            logger.error(f"Error generating thesis content: {e}")
            raise

    async def _generate_table_analysis(self, topic: str, table_data: dict, language: str) -> str:
        """Generate analysis text by looking at actual table data."""
        try:
            headers = table_data.get('headers', [])
            rows = table_data.get('rows', [])
            
            table_text = " | ".join(headers) + "\n"
            for row in rows:
                table_text += " | ".join(str(c) for c in row) + "\n"
            
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi quyidagi jadvalni ko'rib chiq va 150-200 so'zli to'liq tahlil yoz.

Jadval:
{table_text}

Jadvalda nimalar ko'rsatilgan, qanday tendentsiyalar bor, qaysi ko'rsatkichlar muhim - bularni batafsil tahlil qil.

Faqat JSON formatda javob ber:
{{"analysis": "150-200 so'zli jadval tahlili..."}}"""
            elif language == "ru":
                prompt = f"""Проанализируй следующую таблицу по теме "{topic}" и напиши полный анализ на 150-200 слов.

Таблица:
{table_text}

Объясни что показывает таблица, какие тенденции видны, какие показатели важны.

Ответ только в JSON формате:
{{"analysis": "150-200 слов анализа таблицы..."}}"""
            else:
                prompt = f"""Analyze the following table about "{topic}" and write a comprehensive 150-200 word analysis.

Table:
{table_text}

Explain what the table shows, what trends are visible, which indicators are important.

Respond only in JSON format:
{{"analysis": "150-200 word table analysis..."}}"""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You must respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.5
            )
            
            content = response.strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            
            result = self._parse_json_safely(content.strip())
            return result.get('analysis', '')
            
        except Exception as e:
            logger.error(f"Error generating table analysis: {e}")
            return f"Ushbu jadvalda {topic} mavzusiga oid asosiy ko'rsatkichlar va ularning tahlili keltirilgan."

    async def generate_presentation_table_data_old(self, topic: str, language: str) -> dict:
        """Generate 5-row 4-column table for presentation slides (no description)"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi bo'yicha 5 qatorli, 4 ustunli jadval tuz.

Jadval mavzuga to'liq mos bo'lsin. Har bir katak qisqa va mazmunli matn bilan to'ldirilsin (1-3 so'z).

Javobni quyidagi formatda ber:
USTUNLAR: Ustun1 | Ustun2 | Ustun3 | Ustun4
QATOR1: matn | matn | matn | matn
QATOR2: matn | matn | matn | matn
QATOR3: matn | matn | matn | matn
QATOR4: matn | matn | matn | matn
QATOR5: matn | matn | matn | matn"""
            elif language == "ru":
                prompt = f"""Составь таблицу из 5 строк и 4 столбцов по теме "{topic}".

Таблица должна соответствовать теме. Каждая ячейка заполнена кратким текстом (1-3 слова).

Ответ в формате:
СТОЛБЦЫ: Столбец1 | Столбец2 | Столбец3 | Столбец4
СТРОКА1: текст | текст | текст | текст
СТРОКА2: текст | текст | текст | текст
СТРОКА3: текст | текст | текст | текст
СТРОКА4: текст | текст | текст | текст
СТРОКА5: текст | текст | текст | текст"""

            else:
                prompt = f"""Create a 5-row, 4-column table for topic "{topic}".

Table must be relevant to the topic. Each cell filled with brief text (1-3 words).

Format:
COLUMNS: Column1 | Column2 | Column3 | Column4
ROW1: text | text | text | text
ROW2: text | text | text | text
ROW3: text | text | text | text
ROW4: text | text | text | text
ROW5: text | text | text | text"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.7
            )
            
            lines = response.strip().split('\n')
            headers = []
            rows = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('USTUNLAR:') or line.startswith('СТОЛБЦЫ:') or line.startswith('COLUMNS:'):
                    parts = line.split(':', 1)[1].strip()
                    headers = [h.strip() for h in parts.split('|')]
                elif line.startswith('QATOR') or line.startswith('СТРОКА') or line.startswith('ROW'):
                    parts = line.split(':', 1)[1].strip() if ':' in line else line
                    row = [c.strip() for c in parts.split('|')]
                    if len(row) >= 4:
                        rows.append(row[:4])
            
            if not headers or len(headers) < 4:
                headers = ["Ko'rsatkich", "2023", "2024", "O'zgarish"]
            
            while len(rows) < 5:
                rows.append(["—", "—", "—", "—"])
            
            return {"headers": headers[:4], "rows": rows[:5]}
            
        except Exception as e:
            logger.error(f"Error generating presentation table data: {e}")
            return {
                "headers": ["Ko'rsatkich", "2023", "2024", "O'zgarish"],
                "rows": [
                    ["Birinchi", "100", "120", "+20%"],
                    ["Ikkinchi", "50", "65", "+30%"],
                    ["Uchinchi", "200", "180", "-10%"],
                    ["To'rtinchi", "75", "90", "+20%"],
                    ["Beshinchi", "150", "175", "+17%"]
                ]
            }

    async def translate_topic(self, topic: str, target_language: str) -> str:
        """Translate topic to the target language using AI"""
        try:
            lang_names = {"uz": "Uzbek", "ru": "Russian", "en": "English"}
            target_name = lang_names.get(target_language, "Uzbek")
            response = await self._make_request(
                messages=[
                    {"role": "system", "content": f"You are a translator. Translate the given academic topic to {target_name}. Return only the translated text, nothing else."},
                    {"role": "user", "content": topic}
                ],
                max_tokens=200,
                temperature=0.3
            )
            translated = response.strip()
            if translated:
                logger.info(f"Topic translated to {target_language}: {translated}")
                return translated
            return topic
        except Exception as e:
            logger.error(f"Error translating topic: {e}")
            return topic

    async def generate_article_content(self, topic: str, min_pages: int, max_pages: int, language: str) -> dict:
        """Generate a full IMRAD-structured academic article as JSON"""
        try:
            if language == "uz":
                prompt = f"""Sen tajribali akademik yozuvchisan. "{topic}" mavzusida {min_pages}-{max_pages} varoqlik ilmiy maqola yoz.

JADVAL BO'YICHA QOIDA: "table" maydonida mavzuga ENG MOS va ENG FOYDALI jadvalni o'zing belgilagancha yaratgin. Ustun soni, qator soni va sarlavhalar — hammasi erkin. Barcha kataklar haqiqiy, mazmunli ma'lumotlar bilan to'ldirilsin. Bo'sh yoki "..." qoldirma.

IMRAD tuzilmasiga qat'iy rioya qil. Faqat JSON formatda javob ber:

{{
  "title": "Maqola sarlavhasi",
  "abstract": "Annotatsiya (150-200 so'z): muammo, maqsad, metod, asosiy natija va xulosa.",
  "keywords": ["kalit so'z 1", "kalit so'z 2", "kalit so'z 3", "kalit so'z 4", "kalit so'z 5"],
  "introduction": "Kirish (200-300 so'z): mavzuning dolzarbligi, muammo ifodasi, tadqiqot maqsadi va vazifalari, tadqiqot ob'ekti va predmeti.",
  "literature_review": "Adabiyotlar sharhi (200-300 so'z): sohaga oid avvalgi tadqiqotlar tahlili, kamchiliklar va bo'shliqlar.",
  "methodology": "Metodologiya (150-200 so'z): tadqiqot usullari, ma'lumot to'plash usullari, tahlil metodlari.",
  "results_and_discussion": "Natijalar va muhokama (300-400 so'z): olingan natijalar, jadval tahlili, statistik ko'rsatkichlar va ularning izohlanishi.",
  "table": {{
    "headers": ["Ustun 1", "Ustun 2", "Ustun 3"],
    "rows": [
      ["Qator 1 ma'lumot", "ma'lumot", "ma'lumot"],
      ["Qator 2 ma'lumot", "ma'lumot", "ma'lumot"]
    ],
    "caption": "Jadval 1. {topic} bo'yicha tahlil"
  }},
  "conclusion": "Xulosa (150-200 so'z): tadqiqot natijalari xulosasi, ilmiy yangilik, muhim topilmalar.",
  "recommendations": "Amaliy takliflar (100-150 so'z): sohaga, davlat siyosatiga yoki keyingi tadqiqotlarga takliflar.",
  "references": [
    "1. Muallif A.B. Kitob nomi. — Toshkent: Nashriyot, 2022. — 250 b.",
    "2. Muallif C.D. Maqola nomi // Jurnal nomi. — 2023. — №2. — B. 45-62.",
    "3. Muallif E.F. Kitob. — M.: Nauka, 2021. — 180 s.",
    "4. Author G.H. Article title // Journal. — 2023. — Vol.5. — P. 12-28.",
    "5. Author I.J. Book title. — New York: Publisher, 2022. — 320 p.",
    "6. Muallif K.L. Maqola // Jurnal. — 2024. — №1. — B. 10-25.",
    "7. Author M.N. Research paper // Conference. — 2023. — P. 5-15."
  ]
}}

Faqat JSON qaytargin, boshqa hech narsa yozma."""
            elif language == "ru":
                prompt = f"""Ты опытный академический писатель. Напиши научную статью по теме "{topic}" объёмом {min_pages}-{max_pages} страниц.

ПРАВИЛО ДЛЯ ТАБЛИЦЫ: В поле "table" создай НАИБОЛЕЕ ПОДХОДЯЩУЮ и ПОЛЕЗНУЮ таблицу для данной темы. Количество строк, столбцов и их заголовки выбираешь сам — никаких ограничений. Все ячейки должны быть заполнены реальными, содержательными данными. Не оставляй пустых или "..." значений.

Строго придерживайся структуры IMRAD. Отвечай только в формате JSON:

{{
  "title": "Заголовок статьи",
  "abstract": "Аннотация (150-200 слов): проблема, цель, метод, основные результаты и вывод.",
  "keywords": ["ключевое слово 1", "ключевое слово 2", "ключевое слово 3", "ключевое слово 4", "ключевое слово 5"],
  "introduction": "Введение (200-300 слов): актуальность темы, постановка проблемы, цель и задачи исследования, объект и предмет.",
  "literature_review": "Обзор литературы (200-300 слов): анализ предыдущих исследований, выявленные пробелы.",
  "methodology": "Методология (150-200 слов): методы исследования, сбор данных, методы анализа.",
  "results_and_discussion": "Результаты и обсуждение (300-400 слов): полученные результаты, анализ таблицы, статистические показатели.",
  "table": {{
    "headers": ["Столбец 1", "Столбец 2", "Столбец 3"],
    "rows": [
      ["Данные строки 1", "данные", "данные"],
      ["Данные строки 2", "данные", "данные"]
    ],
    "caption": "Таблица 1. Анализ по теме {topic}"
  }},
  "conclusion": "Заключение (150-200 слов): выводы, научная новизна, ключевые результаты.",
  "recommendations": "Практические рекомендации (100-150 слов): предложения для отрасли, государственной политики или будущих исследований.",
  "references": [
    "1. Автор А.Б. Название книги. — М.: Издательство, 2022. — 250 с.",
    "2. Автор В.Г. Название статьи // Журнал. — 2023. — №2. — С. 45-62.",
    "3. Author C.D. Book title. — New York: Publisher, 2021. — 180 p.",
    "4. Автор Д.Е. Монография. — Ташкент: Наука, 2023. — 300 с.",
    "5. Author E.F. Article // Journal. — 2023. — Vol.5. — P. 12-28.",
    "6. Автор Ж.З. Статья // Сборник. — 2024. — С. 10-25.",
    "7. Author G.H. Research. — London: Press, 2022. — P. 5-15."
  ]
}}

Верни только JSON, ничего больше."""
            else:
                prompt = f"""You are an experienced academic writer. Write a scientific article on the topic "{topic}" of {min_pages}-{max_pages} pages.

TABLE RULE: In the "table" field, create the MOST APPROPRIATE and INFORMATIVE table for this topic. You freely choose the number of columns, rows, and headers — no constraints. Fill every cell with real, meaningful data. Do not leave empty or "..." values.

Strictly follow the IMRAD structure. Respond only in JSON format:

{{
  "title": "Article title",
  "abstract": "Abstract (150-200 words): problem, objective, method, main results, and conclusion.",
  "keywords": ["keyword 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5"],
  "introduction": "Introduction (200-300 words): topic relevance, problem statement, research objectives, object and subject of study.",
  "literature_review": "Literature Review (200-300 words): analysis of prior research, identified gaps.",
  "methodology": "Methodology (150-200 words): research methods, data collection, analysis methods.",
  "results_and_discussion": "Results and Discussion (300-400 words): findings, table analysis, statistical indicators and their interpretation.",
  "table": {{
    "headers": ["Column 1", "Column 2", "Column 3"],
    "rows": [
      ["Row 1 data", "data", "data"],
      ["Row 2 data", "data", "data"]
    ],
    "caption": "Table 1. Analysis of {topic}"
  }},
  "conclusion": "Conclusion (150-200 words): summary of findings, scientific novelty, key results.",
  "recommendations": "Practical Recommendations (100-150 words): suggestions for industry, policy, or future research.",
  "references": [
    "1. Author A.B. Book title. — New York: Publisher, 2022. — 250 p.",
    "2. Author C.D. Article title // Journal. — 2023. — Vol.3, №2. — P. 45-62.",
    "3. Author E.F. Monograph. — London: Press, 2021. — 180 p.",
    "4. Author G.H. Research paper // Conference. — 2023. — P. 5-15.",
    "5. Author I.J. Book. — Chicago: Publisher, 2022. — 320 p.",
    "6. Author K.L. Article // Journal. — 2024. — Vol.6. — P. 10-25.",
    "7. Author M.N. Study. — Boston: Academic, 2023. — P. 33-48."
  ]
}}

Return only JSON, nothing else."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Respond with valid JSON only. No markdown, no extra text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=6000,
                temperature=0.7
            )

            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            result = self._parse_json_safely(content)

            required = ["title", "abstract", "keywords", "introduction", "literature_review",
                        "methodology", "results_and_discussion", "table", "conclusion", "references"]
            for key in required:
                if key not in result:
                    result[key] = "" if key != "keywords" else []
                    if key == "table":
                        result[key] = {"headers": [], "rows": [], "caption": ""}
                    if key == "references":
                        result[key] = []

            logger.info(f"Article content generated for topic: {topic}")
            return result

        except Exception as e:
            logger.error(f"Error generating article content: {e}")

    async def generate_mahsus_ishlanma_content(self, topic: str, step_count: int, language: str) -> dict:
        """Generate content for mahsus ishlanma (special project) document."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusida mahsus ishlanma uchun mazmun yarat.

Quyidagi bo'limlar uchun matn yoz:
1. maqsad: Ishdan maqsad (2-3 jumlada)
2. tushunchalar: Mavzu bo'yicha qisqacha tushunchalar (3-5 jumlada)
3. amaliy_qadamlar: {step_count} ta amaliy qadam (har biri title va tavsif bilan, tavsif 3-5 jumlada)
4. xulosa: Xulosa (2-3 jumlada)
5. adabiyotlar: 5 ta foydalanilgan adabiyot ro'yxati

JSON formatida:
{{
  "maqsad": "...",
  "tushunchalar": "...",
  "amaliy_qadamlar": [
    {{"qadam_nomi": "Qadam 1 nomi", "qadam_tavsifi": "Qadam tavsifi..."}},
    ...
  ],
  "xulosa": "...",
  "adabiyotlar": ["1. ...", "2. ...", ...]
}}"""
            elif language == "ru":
                prompt = f"""Создай содержание для специальной разработки на тему "{topic}".

Напиши текст для следующих разделов:
1. maqsad: Цель работы (2-3 предложения)
2. tushunchalar: Краткие понятия по теме (3-5 предложений)
3. amaliy_qadamlar: {step_count} практических шагов (каждый с названием и описанием, 3-5 предложений)
4. xulosa: Заключение (2-3 предложения)
5. adabiyotlar: 5 использованных источников

В JSON формате:
{{
  "maqsad": "...",
  "tushunchalar": "...",
  "amaliy_qadamlar": [
    {{"qadam_nomi": "Шаг 1", "qadam_tavsifi": "Описание..."}},
    ...
  ],
  "xulosa": "...",
  "adabiyotlar": ["1. ...", "2. ...", ...]
}}"""
            else:
                prompt = f"""Create content for a special project on the topic "{topic}".

Write text for the following sections:
1. maqsad: Purpose of the work (2-3 sentences)
2. tushunchalar: Brief concepts on the topic (3-5 sentences)
3. amaliy_qadamlar: {step_count} practical steps (each with title and description, 3-5 sentences)
4. xulosa: Conclusion (2-3 sentences)
5. adabiyotlar: 5 references used

In JSON format:
{{
  "maqsad": "...",
  "tushunchalar": "...",
  "amaliy_qadamlar": [
    {{"qadam_nomi": "Step 1", "qadam_tavsifi": "Description..."}},
    ...
  ],
  "xulosa": "...",
  "adabiyotlar": ["1. ...", "2. ...", ...]
}}"""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "Respond with valid JSON only. No markdown, no extra text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]

            data = json.loads(content_str.strip())
            return data

        except Exception as e:
            logger.error(f"Error generating mahsus ishlanma content: {e}")
            raise

    async def generate_section_formulas(self, section_title: str, topic: str, lang: str) -> dict:
        """Generate formulas, explanations and a practical example for a document section."""
        lang_map = {"uz": "o'zbek", "ru": "русский", "en": "English"}
        lang_name = lang_map.get(lang, "o'zbek")
        prompt = (
            f"You are an academic assistant. Generate mathematical/scientific formulas SPECIFICALLY for the section "
            f'"{section_title}" of a document about "{topic}".\n'
            f"IMPORTANT: These formulas must be UNIQUE and SPECIFIC to THIS section only. "
            f"Do NOT use generic or universal formulas that could appear in any section. "
            f"Each formula must directly relate to '{section_title}' — not to the general topic.\n"
            f"Respond ONLY in {lang_name} language.\n"
            f"Return a JSON object with this exact structure:\n"
            f'{{"formulas": [{{"name": "Formula nomi", "formula": "F = ma", "latex": "F = ma", "explanation": "Qisqa izoh"}}], '
            f'"example": {{"task": "Masala matni (berilganlar va topilsin)", '
            f'"steps": [{{"text": "Berilganlar: ..."}}, {{"latex": "\\\\omega = \\\\frac{{2\\\\pi n}}{{60}}"}}, {{"text": "Natija: ..."}}]}}}}\n'
            f"Provide 1-3 relevant formulas. Keep explanations short (1-2 sentences each).\n"
            f"The 'latex' field in formulas AND in example steps must be valid LaTeX math (without $ delimiters).\n"
            f"Example: '\\\\frac{{8\\\\pi G}}{{c^4}}' for fractions, 'x^{{2}}' for superscripts, '\\\\sqrt{{x}}' for roots.\n"
            f"CRITICAL RULES for example steps:\n"
            f"- Use {{\"text\": \"...\"}} ONLY for plain language sentences (e.g. 'Berilganlar: n=50', 'Natija: 0.75').\n"
            f"- Use {{\"latex\": \"...\"}} for ALL lines containing math symbols (=, \\\\frac, \\\\sqrt, ^, _, \\\\times, etc.).\n"
            f"- NEVER put backslashes or LaTeX commands inside a 'text' field.\n"
            f"- In 'latex' fields do NOT use \\\\text{{...}} with non-Latin characters; use variable names only."
        )
        try:
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.7,
            )
            content_str = response.strip()
            for prefix in ("```json", "```"):
                if content_str.startswith(prefix):
                    content_str = content_str[len(prefix):]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            return json.loads(content_str.strip())
        except Exception as e:
            logger.error(f"Error generating formulas for '{section_title}': {e}")
            return {"formulas": [], "example": {"task": "", "solution": ""}}

    async def generate_section_statistics(self, section_title: str, topic: str, lang: str) -> str:
        """Generate 2-3 statistics/facts for a document section."""
        lang_map = {"uz": "o'zbek", "ru": "русский", "en": "English"}
        lang_name = lang_map.get(lang, "o'zbek")
        prompt = (
            f'Write 2-3 specific statistical facts or research findings about "{section_title}" '
            f'in the context of "{topic}". '
            f"Respond ONLY in {lang_name} language. "
            f"Output ONLY the bullet points — no introduction, no title, no preamble. "
            f"Each fact on its own line starting with '• '. "
            f"Each bullet must be SHORT — max 15 words. Include numbers or percentages. Max 3 bullets total."
        )
        try:
            return await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.4,
            )
        except Exception as e:
            logger.error(f"Error generating statistics for '{section_title}': {e}")
            return ""

    async def generate_comparison_table(self, section_title: str, topic: str, lang: str) -> dict:
        """Generate a 4-column comparison table for a document section."""
        lang_map = {"uz": "o'zbek", "ru": "русский", "en": "English"}
        lang_name = lang_map.get(lang, "o'zbek")
        prompt = (
            f"Create a 4-column comparison/summary table for the section \"{section_title}\" "
            f'about "{topic}". Respond in {lang_name}.\n'
            f"The table must fit on half an A4 page. "
            f"Headers: 1-3 words each. Cell values: 1-2 short sentences max (10-20 words). "
            f"No lengthy paragraphs — keep each cell concise and informative.\n"
            f"Return ONLY JSON: "
            f'{{"headers": ["Col1","Col2","Col3","Col4"], "rows": [["a","b","c","d"], ...]}}\n'
            f"Provide exactly 4 header columns and exactly 3 data rows."
        )
        try:
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3,
            )
            content_str = response.strip()
            for prefix in ("```json", "```"):
                if content_str.startswith(prefix):
                    content_str = content_str[len(prefix):]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            return json.loads(content_str.strip())
        except Exception as e:
            logger.error(f"Error generating comparison table for '{section_title}': {e}")
            return {}

    async def generate_glossary(self, topic: str, lang: str) -> list:
        """Generate a glossary of 8-12 key terms for a document topic."""
        lang_map = {"uz": "o'zbek", "ru": "русский", "en": "English"}
        lang_name = lang_map.get(lang, "o'zbek")
        prompt = (
            f'Generate a glossary of 8-10 key academic terms for the topic "{topic}". '
            f"Respond in {lang_name}.\n"
            f'Return ONLY JSON array: [{{"term": "Atama", "definition": "Ta\'rif"}}]'
        )
        try:
            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700,
                temperature=0.3,
            )
            content_str = response.strip()
            for prefix in ("```json", "```"):
                if content_str.startswith(prefix):
                    content_str = content_str[len(prefix):]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            return json.loads(content_str.strip())
        except Exception as e:
            logger.error(f"Error generating glossary for '{topic}': {e}")
            return []


    async def generate_bridge_sentence(
        self,
        block_type: str,
        section_title: str,
        topic: str,
        lang: str,
    ) -> str:
        """Generate a single varied transitional sentence connecting document blocks.

        block_type values: before_image1, before_image2, before_formulas,
                           before_table, before_statistics
        """
        lang_map = {"uz": "o'zbek", "ru": "русский", "en": "English"}
        lang_name = lang_map.get(lang, "o'zbek")

        block_desc = {
            "before_image1": (
                "a scientific/technical infographic image (diagrams, mechanisms, formulas visualized) "
                "that illustrates the section"
            ),
            "before_image2": (
                "a realistic scene image showing people working with or applying the concepts "
                "of the section (scientists, economists, engineers, etc.)"
            ),
            "before_formulas": (
                "mathematical or scientific formulas relevant to the section"
            ),
            "before_table": (
                "a comparison table summarizing key indicators of the section"
            ),
            "before_statistics": (
                "statistical facts and research data related to the section"
            ),
        }.get(block_type, "the following content")

        prompt = (
            f"You are an academic writer. Write ONE short transitional sentence in {lang_name} "
            f"that naturally leads from the body text of the section \"{section_title}\" "
            f"(topic: \"{topic}\") to {block_desc}.\n"
            f"Requirements:\n"
            f"- Exactly 1 sentence, max 20 words\n"
            f"- Must vary in wording — do not use cliché openings like 'Quyida keltirilgan' or 'Следующее'\n"
            f"- Must feel like a natural continuation of academic text\n"
            f"- End with a colon (:)\n"
            f"Output ONLY the sentence. No quotes, no explanation."
        )
        try:
            result = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.9,
            )
            sentence = result.strip().strip('"').strip("'")
            if not sentence.endswith(":"):
                sentence = sentence.rstrip(".") + ":"
            return sentence
        except Exception as e:
            logger.error(f"Error generating bridge sentence ({block_type}): {e}")
            fallbacks = {
                "uz": {
                    "before_image1": f"\"{section_title}\" bo'limining ilmiy-texnik ko'rinishi:",
                    "before_image2": f"Ushbu tushunchalar amaliyotda quyidagicha namoyon bo'ladi:",
                    "before_formulas": f"\"{section_title}\" bo'limiga xos asosiy formulalar:",
                    "before_table": f"Asosiy ko'rsatkichlarni quyidagi jadval orqali taqqoslash mumkin:",
                    "before_statistics": f"Mavzuning dolzarbligini quyidagi raqamlar tasdiqlaydi:",
                },
                "ru": {
                    "before_image1": f"Научно-техническая визуализация раздела «{section_title}»:",
                    "before_image2": "Практическое применение данных концепций выглядит следующим образом:",
                    "before_formulas": f"Ключевые формулы, характерные для раздела «{section_title}»:",
                    "before_table": "Сравнение основных показателей представлено в таблице ниже:",
                    "before_statistics": "Актуальность темы подтверждается следующими данными:",
                },
                "en": {
                    "before_image1": f"The scientific visualization of \"{section_title}\" is shown below:",
                    "before_image2": "The practical application of these concepts is illustrated here:",
                    "before_formulas": f"The key formulas specific to \"{section_title}\" are presented below:",
                    "before_table": "The following table compares the main indicators:",
                    "before_statistics": "The following data confirms the relevance of this topic:",
                },
            }
            return fallbacks.get(lang, fallbacks["uz"]).get(block_type, ":")


_ai_service_instance: "AIService | None" = None


def get_ai_service() -> "AIService":
    """Return the shared AIService singleton (creates once, reuses forever)."""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
        logger.info("AIService singleton created")
    return _ai_service_instance


async def generate_test_questions(topic: str, count: int, language: str) -> list:
    """Generate multiple-choice test questions via AI.

    Returns a list of dicts:
      {"question": str, "options": [A, B, C, D], "correct_index": int, "explanation": str}
    """
    service = get_ai_service()
    lang_map = {"uz": "o'zbek", "ru": "русский", "en": "English"}
    lang_name = lang_map.get(language, "o'zbek")
    prompt = (
        f"You are an expert teacher. Generate {count} multiple-choice test questions about \"{topic}\".\n"
        f"Respond ONLY in {lang_name} language.\n"
        f"Each question must have exactly 4 options and one correct answer.\n"
        f"Return ONLY a valid JSON array (no markdown, no explanation):\n"
        f'[{{"question":"Savol matni?","options":["A variant","B variant","C variant","D variant"],'
        f'"correct_index":0,"explanation":"Qisqa izoh"}}]\n'
        f"correct_index is 0-based (0=A, 1=B, 2=C, 3=D).\n"
        f"Make questions diverse and cover different aspects of the topic."
    )
    try:
        response = await service._make_request(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(200 * count, 4000),
            temperature=0.7,
        )
        content = response.strip()
        for prefix in ("```json", "```"):
            if content.startswith(prefix):
                content = content[len(prefix):]
        if content.endswith("```"):
            content = content[:-3]
        questions = json.loads(content.strip())
        if isinstance(questions, list):
            return questions[:count]
        return []
    except Exception as e:
        logger.error(f"Error generating test questions for '{topic}': {e}")
        return []


async def close_ai_service() -> None:
    """Close the singleton's HTTP client on bot shutdown."""
    global _ai_service_instance
    if _ai_service_instance is not None:
        try:
            await _ai_service_instance.client.close()
        except Exception:
            pass
        _ai_service_instance = None
        logger.info("AIService singleton closed")
