import os
import logging
import aiohttp
import asyncio
import base64
import httpx
from typing import Optional, Dict
from together import Together
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class TogetherImageService:
    """Service for generating images using Together AI FLUX models"""
    
    def __init__(self):
        self.api_key = os.getenv("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError("TOGETHER_API_KEY environment variable is required")
        self.client = Together(api_key=self.api_key)
        self.model = "black-forest-labs/FLUX.1-schnell"
        
        self.ai_client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY") or "dummy-key",
            base_url=os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
        )
        # GPT-4o - rasm promptlari uchun (kuchliroq versiya)
        self.ai_model = "openai/gpt-4o"
    
    async def _generate_image_prompt(self, topic: str, slide_title: str) -> str:
        """Generate a context-aware English image prompt using topic + slide title."""
        try:
            prompt_request = (
                f"Generate a short, specific English image prompt for a presentation slide.\n\n"
                f"Presentation topic: \"{topic}\"\n"
                f"Slide section: \"{slide_title}\"\n\n"
                f"Rules:\n"
                f"1. The image MUST visually represent BOTH the main topic AND the slide section together.\n"
                f"2. Be very specific — mention real objects, places, or scenes directly related to \"{topic}\".\n"
                f"3. Maximum 25 words.\n"
                f"4. NO text, letters, numbers, or signs in the image.\n"
                f"5. Professional photography or realistic illustration style.\n\n"
                f"Output ONLY the prompt, nothing else."
            )

            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt_request}],
                max_tokens=120,
                temperature=0.7
            )

            generated_prompt = response.choices[0].message.content.strip()
            generated_prompt = generated_prompt.strip('"').strip("'")

            logger.info(f"Image prompt generated: {generated_prompt}")
            return generated_prompt

        except Exception as e:
            logger.error(f"Error generating image prompt: {e}")
            return f"Professional photograph related to {topic}, {slide_title}, realistic style, no text"
    
    async def generate_image(self, prompt: str, aspect_ratio: str = "16:9", steps: int = 4) -> Optional[str]:
        """Generate image using Together AI FLUX model
        
        Args:
            prompt: English description of the image (detailed, high quality)
            aspect_ratio: Image aspect ratio (16:9 for slides, 21:9 for panoramic)
            steps: Number of generation steps (4 for fast, more for quality)
        
        Returns:
            Path to downloaded image or None if failed
        """
        try:
            # Defence in depth: block NSFW / extremist prompts before they
            # reach Together's billable API.
            try:
                from utils.security import sanitize_image_prompt
                cleaned = sanitize_image_prompt(prompt)
                if cleaned is None:
                    logger.warning("Image prompt rejected by sanitizer; skipping generation")
                    return None
                prompt = cleaned
            except Exception as _ex:
                logger.warning(f"Image prompt sanitizer unavailable: {_ex}")

            logger.info(f"Generating image with prompt: {prompt[:100]}...")

            # Wrap the SDK call with a hard timeout (Together can hang on transient
            # backend issues) and a small retry loop for 429/5xx-style errors.
            async def _call():
                return await asyncio.to_thread(
                    self.client.images.generate,
                    prompt=prompt,
                    model=self.model,
                    steps=steps,
                    n=1,
                )

            last_exc = None
            response = None
            for attempt in range(3):
                try:
                    response = await asyncio.wait_for(_call(), timeout=60)
                    break
                except (asyncio.TimeoutError, Exception) as ex:
                    last_exc = ex
                    msg = str(ex).lower()
                    transient = isinstance(ex, asyncio.TimeoutError) or any(
                        s in msg for s in ("429", "rate", "timeout", "503", "502", "504", "temporar")
                    )
                    if not transient or attempt == 2:
                        raise
                    backoff = 1.5 * (2 ** attempt)
                    logger.warning(f"Together image transient error (attempt {attempt+1}): {ex}; retrying in {backoff}s")
                    await asyncio.sleep(backoff)
            if response is None:
                raise last_exc or RuntimeError("Together image generation failed")
            
            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                if image_url:
                    filename = f"together_image_{hash(prompt) % 100000}.png"
                    image_path = await self._download_image(image_url, filename)
                    if image_path:
                        logger.info(f"Image generated and saved: {image_path}")
                        return image_path
                    
                if response.data[0].b64_json:
                    import base64
                    filename = f"together_image_{hash(prompt) % 100000}.png"
                    filepath = os.path.join("temp", filename)
                    os.makedirs("temp", exist_ok=True)
                    
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(response.data[0].b64_json))
                    
                    logger.info(f"Image generated from base64: {filepath}")
                    return filepath
            
            logger.error("No image data in response")
            return None
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
    
    async def generate_slide_image(self, topic: str, slide_title: str, language: str, text_overlay: str = None) -> Optional[str]:
        """Generate image for presentation slide using DeepSeek-generated prompt
        
        Args:
            topic: Main presentation topic
            slide_title: Title of current slide
            language: Language (uz, ru, en)
            text_overlay: Ignored - no text in images
        
        Returns:
            Path to generated image
        """
        prompt = await self._generate_image_prompt(topic, slide_title)
        return await self.generate_image(prompt, aspect_ratio="16:9")
    
    async def generate_cover_image(self, topic: str, language: str) -> Optional[str]:
        """Generate beautiful cover image matching topic using FLUX.2-pro (no text in image)
        
        Args:
            topic: Presentation topic
            language: Language for context
        
        Returns:
            Path to generated image
        """
        try:
            # Create prompt for beautiful topic-related image WITHOUT any text
            prompt = f"""Stunning professional photograph related to "{topic}".
Beautiful high-quality image with perfect lighting and composition.
Modern, clean aesthetic suitable for professional presentation cover.
Vibrant colors, sharp focus, professional photography style.
NO TEXT, NO WORDS, NO LETTERS in the image - purely visual.
The image should clearly represent the theme of {topic}.
Corporate presentation quality, inspiring and engaging visual."""

            pro_model = "black-forest-labs/FLUX.2-pro"
            logger.info(f"Generating beautiful cover image for topic using FLUX.2-pro...")
            
            response = await asyncio.to_thread(
                self.client.images.generate,
                prompt=prompt,
                model=pro_model,
                n=1
            )
            
            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                if image_url:
                    filename = f"cover_image_{hash(topic) % 100000}.png"
                    image_path = await self._download_image(image_url, filename)
                    if image_path:
                        logger.info(f"Cover image generated: {image_path}")
                        return image_path
                
                if response.data[0].b64_json:
                    filename = f"cover_image_{hash(topic) % 100000}.png"
                    filepath = os.path.join("temp", filename)
                    os.makedirs("temp", exist_ok=True)
                    
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(response.data[0].b64_json))
                    
                    return filepath
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating cover image: {e}")
            # Fallback to regular image generation
            prompt = await self._generate_image_prompt(topic, topic)
            return await self.generate_image(prompt, aspect_ratio="1:1")
    
    async def generate_panoramic_image(self, topic: str, slide_title: str, language: str) -> Optional[str]:
        """Generate panoramic image using DeepSeek-generated prompt
        
        Args:
            topic: Presentation topic
            slide_title: Slide title for context
            language: Language (ignored - no text)
        
        Returns:
            Path to generated image
        """
        prompt = await self._generate_image_prompt(topic, slide_title)
        return await self.generate_image(prompt, aspect_ratio="16:9")
    
    async def _download_image(self, image_url: str, filename: str) -> Optional[str]:
        """Download image from URL with timeout + small retry loop."""
        os.makedirs("temp", exist_ok=True)
        filepath = os.path.join("temp", filename)
        timeout = aiohttp.ClientTimeout(total=45, connect=10)
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(image_url) as response:
                        if response.status == 200:
                            content = await response.read()
                            with open(filepath, "wb") as f:
                                f.write(content)
                            return filepath
                        logger.error(f"Image download HTTP {response.status} (attempt {attempt+1})")
                        if response.status < 500:
                            return None
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logger.warning(f"Image download error attempt {attempt+1}: {e}")
            except Exception as e:
                logger.error(f"Image download fatal: {e}")
                return None
            if attempt < 2:
                await asyncio.sleep(1.5 * (2 ** attempt))
        return None
    
    async def generate_flux_pro_image(
        self,
        topic: str,
        subsection_title: str,
        language: str = 'uz',
        image_type: str = 'infographic',
    ) -> tuple:
        """Generate high-quality image using Together AI FLUX 2 Pro for course work.

        Args:
            topic: Main course work topic
            subsection_title: Title of subsection
            language: Language (uz, ru, en)
            image_type: 'infographic' (technical diagrams, formulas, mechanisms)
                        or 'scene' (people applying the concepts)

        Returns:
            Tuple of (image_path, image_prompt) or (None, None) if failed
        """
        try:
            image_prompt = await self._generate_course_work_image_prompt(
                topic, subsection_title, language, image_type=image_type
            )

            pro_model = "black-forest-labs/FLUX.2-pro"
            logger.info(f"Generating {image_type} image with Together AI {pro_model}...")

            response = await asyncio.to_thread(
                self.client.images.generate,
                prompt=image_prompt,
                model=pro_model,
                n=1
            )

            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                if image_url:
                    filename = f"course_work_{image_type}_{hash(subsection_title) % 100000}.png"
                    image_path = await self._download_image(image_url, filename)
                    if image_path:
                        logger.info(f"Course work {image_type} image generated: {image_path}")
                        return image_path, image_prompt

                if response.data[0].b64_json:
                    filename = f"course_work_{image_type}_{hash(subsection_title) % 100000}.png"
                    filepath = os.path.join("temp", filename)
                    os.makedirs("temp", exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(response.data[0].b64_json))
                    logger.info(f"Course work {image_type} image from base64: {filepath}")
                    return filepath, image_prompt

            logger.error("No image data in Together AI response")
            return None, None

        except Exception as e:
            logger.error(f"Error generating course work {image_type} image: {e}")
            return None, None
    
    async def generate_infographic_prompt(
        self,
        topic: str,
        subsection_title: str,
        language: str = 'uz',
        image_type: str = 'infographic',
    ) -> str:
        """Generate a focused English image prompt for FLUX.2-pro.

        image_type='infographic': technical/scientific visualization (diagrams, mechanisms,
            chemical structures, mathematical graphs) — NO people.
        image_type='scene': realistic scene with people applying the topic concepts
            (scientists, economists, engineers, students in context).
        """
        if image_type == 'infographic':
            style_instruction = (
                f"TYPE: Scientific/technical infographic illustration.\n"
                f"- Show diagrams, mechanisms, chemical structures, mathematical graphs, "
                f"technical schematics, or process flowcharts directly related to '{subsection_title}'\n"
                f"- Style: clean vector infographic, blueprint, or scientific diagram — high detail\n"
                f"- NO people, NO faces, NO human figures\n"
                f"- NO text overlays, NO labels, NO watermarks, NO formulas written as text\n"
                f"- Visualize CONCEPTS as shapes, arrows, structures — not as written symbols\n"
                f"- Colors: professional blue/white/gray palette, bright and clear"
            )
            fallback = (
                f"Scientific technical infographic diagram about '{subsection_title}' related to '{topic}', "
                f"clean vector illustration, mechanisms and structures, blue palette, no people, "
                f"no text, no letters, high quality"
            )
        else:
            style_instruction = (
                f"TYPE: Realistic scene with people.\n"
                f"- Show professionals or students actively working with or applying the concepts of '{subsection_title}'\n"
                f"- Examples: scientists in a lab, economists at a market, engineers at a factory, "
                f"programmers at computers, doctors with patients — choose what fits the topic\n"
                f"- Style: photorealistic or high-quality editorial illustration\n"
                f"- Scene must feel authentic and directly relevant to '{topic}'\n"
                f"- NO text overlays, NO watermarks, NO written formulas\n"
                f"- Bright, well-lit, professional environment"
            )
            fallback = (
                f"Realistic scene of professionals working with '{subsection_title}' concepts related to '{topic}', "
                f"people in a professional environment, photorealistic, bright lighting, "
                f"no text, no watermarks, high quality"
            )

        prompt_request = (
            f"You are an expert at writing image prompts for AI image generators.\n"
            f"Academic document topic: \"{topic}\"\n"
            f"Section title: \"{subsection_title}\"\n\n"
            f"Write a single English image prompt (50-70 words) for this specific image:\n\n"
            f"{style_instruction}\n\n"
            f"Output ONLY the English prompt. No explanations, no quotes."
        )

        try:
            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt_request}],
                max_tokens=150,
                temperature=0.7
            )
            generated_prompt = response.choices[0].message.content.strip()
            generated_prompt = generated_prompt.strip('"').strip("'")
            logger.info(f"{image_type} prompt for '{subsection_title}': {generated_prompt}")
            return generated_prompt
        except Exception as e:
            logger.error(f"Error generating {image_type} prompt: {e}")
            return fallback

    async def _generate_course_work_image_prompt(
        self,
        topic: str,
        subsection_title: str,
        language: str = 'uz',
        image_type: str = 'infographic',
    ) -> str:
        """Generate image prompt for course work (delegates to generate_infographic_prompt)."""
        return await self.generate_infographic_prompt(topic, subsection_title, language, image_type=image_type)
    
    async def generate_image_description(self, topic: str, subsection_title: str, language: str = 'uz', image_path: str = None) -> str:
        """Generate detailed description text by analyzing the actual generated image with vision AI"""
        try:
            # If we have an image path, use vision to analyze it
            if image_path and os.path.exists(image_path):
                return await self._analyze_image_with_vision(image_path, topic, subsection_title, language)
            
            # Fallback to text-based description
            if language == 'uz':
                prompt = f"""{topic} mavzusidagi {subsection_title} bo'limi uchun rasm tavsifini yozing.
6-8 ta gap yozing (120-150 so'z). Ilmiy uslubda, akademik til."""
            elif language == 'ru':
                prompt = f"""Напишите описание изображения для раздела "{subsection_title}" по теме "{topic}".
6-8 предложений (120-150 слов). Научный стиль."""
            else:
                prompt = f"""Write an image description for "{subsection_title}" on topic "{topic}".
6-8 sentences (120-150 words). Scientific style."""
            
            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7
            )
            
            description = response.choices[0].message.content.strip()
            
            # Remove last 2 sentences
            sentences = description.split('.')
            sentences = [s.strip() for s in sentences if s.strip()]
            if len(sentences) > 2:
                sentences = sentences[:-2]
            description = '. '.join(sentences) + '.'
            
            logger.info(f"Generated image description: {description[:50]}...")
            return description
            
        except Exception as e:
            logger.error(f"Error generating image description: {e}")
            if language == 'uz':
                return f"Ushbu rasmda {subsection_title} mavzusining asosiy elementlari ko'rsatilgan."
            elif language == 'ru':
                return f"На данном изображении представлены основные элементы темы {subsection_title}."
            else:
                return f"This image illustrates the main elements of {subsection_title}."
    
    async def _analyze_image_with_vision(self, image_path: str, topic: str, subsection_title: str, language: str) -> str:
        """Analyze actual image using vision AI and generate accurate description"""
        try:
            import base64
            
            # Read and encode the image
            with open(image_path, "rb") as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # Determine image type
            if image_path.endswith('.png'):
                mime_type = "image/png"
            else:
                mime_type = "image/jpeg"
            
            # Create vision prompt based on language
            if language == 'uz':
                vision_prompt = f"""Ushbu rasmni ko'rib chiqing va "{topic}" mavzusi bo'yicha tavsif yozing.

Qoidalar:
1. 6-8 ta gap yozing (120-150 so'z)
2. Rasmda ANIQ nima tasvirlanganini yozing
3. Ko'rgan narsalaringizni batafsil tavsiflang
4. Ilmiy uslubda, akademik til
5. Faqat tavsif matnini yozing

"Ushbu rasmda..." bilan boshlang."""
            elif language == 'ru':
                vision_prompt = f"""Проанализируйте это изображение и напишите описание по теме "{topic}".

Правила:
1. 6-8 предложений (120-150 слов)
2. Опишите ТОЧНО что изображено на картинке
3. Подробно опишите все что видите
4. Научный стиль, академический язык
5. Только текст описания

Начните с "На данном изображении..."."""
            else:
                vision_prompt = f"""Analyze this image and write a description for the topic "{topic}".

Rules:
1. 6-8 sentences (120-150 words)
2. Describe EXACTLY what is shown in the image
3. Describe everything you see in detail
4. Scientific style, academic language
5. Only description text

Start with "This image shows..."."""
            
            # Use vision-capable model (GPT-4o mini has vision)
            response = await self.ai_client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}
                    ]
                }],
                max_tokens=400,
                temperature=0.7
            )
            
            description = response.choices[0].message.content.strip()
            
            # Remove last 2 sentences
            sentences = description.split('.')
            sentences = [s.strip() for s in sentences if s.strip()]
            if len(sentences) > 2:
                sentences = sentences[:-2]
            description = '. '.join(sentences) + '.'
            
            logger.info(f"Vision analysis completed for image: {image_path[:30]}...")
            return description
            
        except Exception as e:
            logger.error(f"Error in vision analysis: {e}")
            # Fallback to basic description
            if language == 'uz':
                return f"Ushbu rasmda {subsection_title} mavzusining asosiy elementlari ko'rsatilgan."
            elif language == 'ru':
                return f"На данном изображении представлены основные элементы темы {subsection_title}."
            else:
                return f"This image illustrates the main elements of {subsection_title}."


_together_service_instance: "TogetherImageService | None" = None


def get_together_service() -> "TogetherImageService":
    """Return the shared TogetherImageService singleton."""
    global _together_service_instance
    if _together_service_instance is None:
        _together_service_instance = TogetherImageService()
        logger.info("TogetherImageService singleton created")
    return _together_service_instance


async def close_together_service() -> None:
    """Close the singleton's HTTP clients on bot shutdown."""
    global _together_service_instance
    if _together_service_instance is not None:
        try:
            await _together_service_instance.ai_client.close()
        except Exception:
            pass
        _together_service_instance = None
        logger.info("TogetherImageService singleton closed")
