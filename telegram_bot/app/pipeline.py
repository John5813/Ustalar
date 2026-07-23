import logging

from pydantic import ValidationError

from . import config, llm_client, qa
from .models import Brief, Slide, grounding_check
from .renderer import build_presentation

log = logging.getLogger("pipeline")


# ─────────────────────────────────────────── Kanvas validatsiyasi

def canvas_check(slide: Slide) -> tuple[bool, str]:
    """Slayd kanvasining minimal to'liqligini tekshiradi."""
    elements = slide.canvas.elements or []

    if len(elements) < 3:
        return False, (
            f"Slayd {slide.index}: elementlar soni juda kam ({len(elements)}). "
            "Kamida 4–6 ta element bilan boy vizual kompozitsiya yaraT."
        )

    text_elements = [e for e in elements if e.type == "text" and e.text and e.text.strip()]
    if not text_elements:
        return False, (
            f"Slayd {slide.index}: slaydda hech qanday matn yo'q. "
            "Kamida sarlavha va tavsif matnini qo'sh."
        )

    if not slide.title or not slide.title.strip():
        return False, f"Slayd {slide.index}: 'title' maydoni bo'sh."

    return True, ""


def canvas_validation_and_fix(brief: Brief, topic: str, max_attempts: int = 2) -> Brief:
    """Har slaydni tekshiradi, muammoli slaydlarni qayta loyihalaydi."""
    for attempt in range(max_attempts):
        any_issue = False
        for i, slide in enumerate(brief.slides):
            ok, problem = canvas_check(slide)
            if not ok:
                any_issue = True
                log.warning("Kanvas muammo (slayd %s, urinish %s): %s", slide.index, attempt + 1, problem)
                try:
                    fixed = llm_client.regenerate_slide(topic, slide.model_dump(), problem)
                    merged = {**slide.model_dump(), **fixed}
                    brief.slides[i] = Slide.model_validate(merged)
                    ok2, problem2 = canvas_check(brief.slides[i])
                    if not ok2:
                        log.error("Tuzatishdan keyin ham muammo (slayd %s): %s", slide.index, problem2)
                except Exception as e:
                    log.error("Kanvas tuzatishda xato (slayd %s): %s", slide.index, e)

        if not any_issue:
            log.info("Kanvas tekshiruv: hamma slayd to'liq (urinish %s)", attempt + 1)
            break

    return brief


# ─────────────────────────────────────────── Brief generatsiyasi

def generate_brief_with_validation(topic: str, max_attempts: int = 3) -> Brief:
    """LLM'dan JSON so'raydi, pydantic orqali qat'iy tekshiradi. Silent fallback YO'Q."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = llm_client.generate_brief(topic)
            brief = Brief.model_validate(raw)

            # Grounding-check: detail/comparison slaydlarida aniq fakt bormi
            for i, s in enumerate(brief.slides):
                if not grounding_check(s):
                    log.warning("Grounding-check muvaffaqiyatsiz: slayd %s, qayta yozilmoqda", s.index)
                    fixed = llm_client.regenerate_slide(
                        topic, s.model_dump(),
                        "Bu slaydda aniq raqam, sana yoki atoqli ot yo'q. "
                        "Aniq fakt/misol qo'shib, vizual kompozitsiyani ham yangilab qayta yoz."
                    )
                    merged = {**s.model_dump(), **fixed}
                    brief.slides[i] = Slide.model_validate(merged)

            return brief

        except ValidationError as e:
            last_error = e
            log.error("Brief validatsiya xatosi (urinish %s/%s): %s", attempt, max_attempts, e)
        except Exception as e:
            last_error = e
            log.error("Brief generatsiyasida xato (urinish %s/%s): %s", attempt, max_attempts, e)

    raise RuntimeError(
        f"Brief generatsiya {max_attempts} urinishdan keyin muvaffaqiyatsiz: {last_error}"
    )


# ─────────────────────────────────────────── Vizual QA

def run_visual_qa_and_fix(pptx_path: str, brief: Brief, topic: str) -> str:
    """Slaydlarni rasmga aylantirib, vision model tekshiradi.
    Muammo topilsa tegishli slaydni qayta loyihalaydi."""
    current_path = pptx_path
    current_brief = brief

    for round_no in range(config.MAX_QA_RETRIES):
        try:
            images = qa.pptx_to_images(current_path)
        except Exception as e:
            log.error("QA rasmga aylantirishda xato (LibreOffice/poppler o'rnatilganmi?): %s", e)
            break

        if not images or len(images) != len(current_brief.slides):
            log.warning("QA rasm soni slayd soniga mos kelmadi (%s vs %s), QA bekor",
                        len(images or []), len(current_brief.slides))
            break

        any_issue = False
        for img_path, slide in zip(images, current_brief.slides):
            context = (
                f"role={slide.role}, title={slide.title}, "
                f"elements={len(slide.canvas.elements)}"
            )
            result = qa.check_slide_image(img_path, context)
            if not result.get("ok", True):
                any_issue = True
                issue = result.get("issue", "aniqlanmagan muammo")
                log.info("Vizual QA muammo (slayd %s): %s", slide.index, issue)
                try:
                    fixed = llm_client.regenerate_slide(topic, slide.model_dump(), issue)
                    idx = current_brief.slides.index(slide)
                    merged = {**slide.model_dump(), **fixed}
                    current_brief.slides[idx] = Slide.model_validate(merged)
                    # Kanvas minimal tekshiruv
                    ok, problem = canvas_check(current_brief.slides[idx])
                    if not ok:
                        log.warning("Vizual tuzatishdan keyin kanvas muammo: %s", problem)
                except Exception as e:
                    log.error("Slayd qayta loyihalashda xato: %s", e)

        if not any_issue:
            log.info("Vizual QA: barcha slayd qabul qilindi (round %s)", round_no + 1)
            break

        current_path = build_presentation(current_brief)

    return current_path


# ─────────────────────────────────────────── To'liq pipeline

def generate_presentation(topic: str) -> str:
    log.info("1/4 — Brief generatsiyasi: '%s'", topic)
    brief = generate_brief_with_validation(topic)

    log.info("2/4 — Kanvas validatsiyasi: %s slayd", len(brief.slides))
    brief = canvas_validation_and_fix(brief, topic)

    log.info("3/4 — PPTX render")
    pptx_path = build_presentation(brief)

    log.info("4/4 — Vizual QA va tuzatish")
    final_path = run_visual_qa_and_fix(pptx_path, brief, topic)

    log.info("Taqdimot tayyor: %s", final_path)
    return final_path
