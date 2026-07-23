import logging

from pydantic import ValidationError

from . import config, llm_client, qa
from .models import Brief, Slide, grounding_check
from .renderer import build_presentation

log = logging.getLogger("pipeline")

# Har layout uchun majburiy maydonlar
_NEEDS_ITEMS = {
    "icon_row_list", "agenda_numbered", "three_card_grid", "four_card_grid",
    "two_card_compare", "comparison_table", "stat_row_triple", "stat_callout",
    "timeline_process", "mini_case_study",
}
_NEEDS_BODY = {"quote_callout", "definition_spotlight", "image_half_bleed", "stat_callout"}
_NEEDS_IMAGE_PROMPT = {"image_half_bleed"}
_NEEDS_CHART_DATA = {"bar_chart", "xy_chart"}
_NEEDS_MATH_BLOCKS = {"math_formula"}
_MIN_ITEMS = {
    "two_card_compare": 2, "mini_case_study": 2,
    "stat_callout": 1, "stat_row_triple": 3,
    "four_card_grid": 4, "three_card_grid": 3,
}


def structural_check(slide: Slide) -> tuple[bool, str]:
    """Slayd strukturaviy to'liqligini tekshiradi. (ok, muammo tavsifi)"""
    layout = slide.layout_type

    if layout in _NEEDS_ITEMS:
        min_count = _MIN_ITEMS.get(layout, 3)
        actual = len(slide.items or [])
        if actual < min_count:
            return False, (
                f"'{layout}' layoutida 'items' kamida {min_count} ta bo'lishi shart, "
                f"hozir {actual} ta. Kamida {min_count} ta {{heading, body}} element qo'sh."
            )

    if layout in _NEEDS_BODY:
        if not (slide.body and slide.body.strip()):
            return False, (
                f"'{layout}' layoutida 'body' maydoni bo'sh yoki null. "
                f"Mazmunli matn yoz (kamida 20 so'z)."
            )

    if layout in _NEEDS_IMAGE_PROMPT:
        if not (slide.image_prompt and slide.image_prompt.strip()):
            return False, (
                f"'{layout}' layoutida 'image_prompt' bo'sh. "
                f"Inglizcha foto-real rasm tavsifi yoz (10-20 so'z)."
            )

    if layout in _NEEDS_CHART_DATA:
        if not slide.chart_data:
            return False, (
                f"'{layout}' layoutida 'chart_data' maydoni yo'q. "
                f"chart_data ni x_label, y_label, unit va kamida 3 ta points bilan to'ldir."
            )
        points = slide.chart_data.points or []
        if len(points) < 3:
            return False, (
                f"'{layout}' layoutida chart_data.points kamida 3 ta bo'lishi shart "
                f"(hozir {len(points)} ta). Ko'proq qiymat qo'sh."
            )

    if layout in _NEEDS_MATH_BLOCKS:
        blocks = slide.math_blocks or []
        if len(blocks) < 2:
            return False, (
                f"'{layout}' layoutida 'math_blocks' kamida 2 ta bo'lishi shart "
                f"(hozir {len(blocks)} ta). Kamida 2 ta {{formula, description}} blok qo'sh."
            )

    return True, ""


def structural_validation_and_fix(brief: Brief, topic: str, max_attempts: int = 2) -> Brief:
    """Har slaydni strukturaviy jihatdan tekshiradi va muammoli slaydlarni qayta yozadi."""
    for attempt in range(max_attempts):
        any_issue = False
        for i, slide in enumerate(brief.slides):
            ok, problem = structural_check(slide)
            if not ok:
                any_issue = True
                log.warning("Strukturaviy muammo (slayd %s, urinish %s): %s", slide.index, attempt + 1, problem)
                try:
                    fixed = llm_client.regenerate_slide(topic, slide.model_dump(), problem)
                    merged = {**slide.model_dump(), **fixed}
                    brief.slides[i] = Slide.model_validate(merged)
                    # Tuzatilgandan keyin qayta tekshir
                    ok2, problem2 = structural_check(brief.slides[i])
                    if not ok2:
                        log.error("Tuzatishdan keyin ham muammo qoldi (slayd %s): %s", slide.index, problem2)
                except Exception as e:
                    log.error("Strukturaviy tuzatishda xato (slayd %s): %s", slide.index, e)

        if not any_issue:
            log.info("Strukturaviy tekshiruv: hamma slayd to'liq (urinish %s)", attempt + 1)
            break

    return brief


def generate_brief_with_validation(topic: str, max_attempts: int = 3) -> Brief:
    """LLM'dan JSON so'raydi, pydantic orqali qat'iy tekshiradi.
    Xato bo'lsa XATONI LOGGA CHIQARIB qayta so'raydi (silent fallback YO'Q)."""
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
                        "Bu slaydda aniq raqam, sana yoki atoqli ot yo'q. Aniq fakt/misol qo'shib qayta yoz."
                    )
                    merged = {**s.model_dump(), **fixed}
                    brief.slides[i] = Slide.model_validate(merged)

            return brief

        except ValidationError as e:
            last_error = e
            log.error("Brief validatsiya xatosi (urinish %s/%s): %s", attempt, max_attempts, e)
        except Exception as e:
            last_error = e
            log.error("Brief generatsiyasida kutilmagan xato (urinish %s/%s): %s", attempt, max_attempts, e)

    raise RuntimeError(f"Brief generatsiya {max_attempts} urinishdan keyin ham muvaffaqiyatsiz: {last_error}")


def run_visual_qa_and_fix(pptx_path: str, brief: Brief, topic: str) -> str:
    """Slaydlarni skrinshotga aylantirib, vision model orqali tekshiradi.
    Muammo topilsa tegishli slaydni qayta yozib, PPTX'ni qayta quradi (MAX_QA_RETRIES marta)."""
    current_path = pptx_path
    current_brief = brief

    for round_no in range(config.MAX_QA_RETRIES):
        try:
            images = qa.pptx_to_images(current_path)
        except Exception as e:
            log.error("QA uchun rasmga aylantirishda xato (LibreOffice/poppler o'rnatilganmi?): %s", e)
            break

        if not images or len(images) != len(current_brief.slides):
            log.warning("QA rasm soni slayd soniga mos kelmadi, QA bekor qilindi")
            break

        any_issue = False
        for img_path, slide in zip(images, current_brief.slides):
            context = f"role={slide.role}, layout={slide.layout_type}, title={slide.title}"
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
                    # Strukturaviy jihatdan ham tekshir
                    ok, problem = structural_check(current_brief.slides[idx])
                    if not ok:
                        log.warning("Vizual tuzatishdan keyin strukturaviy muammo: %s", problem)
                except Exception as e:
                    log.error("Slayd qayta yozishda xato: %s", e)

        if not any_issue:
            log.info("Vizual QA: barcha slayd qabul qilindi (round %s)", round_no + 1)
            break

        current_path = build_presentation(current_brief)

    return current_path


def generate_presentation(topic: str) -> str:
    log.info("1/4 — Brief generatsiyasi boshlanmoqda: '%s'", topic)
    brief = generate_brief_with_validation(topic)

    log.info("2/4 — Strukturaviy tekshiruv: %s slayd", len(brief.slides))
    brief = structural_validation_and_fix(brief, topic)

    log.info("3/4 — PPTX render qilinmoqda")
    pptx_path = build_presentation(brief)

    log.info("4/4 — Vizual QA va tuzatish")
    final_path = run_visual_qa_and_fix(pptx_path, brief, topic)

    log.info("Taqdimot tayyor: %s", final_path)
    return final_path
