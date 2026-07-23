"""
Erkin kanvas renderer — AI tomonidan tasvirlangan elementlarni python-pptx orqali chizadi.
Hech qanday qattiq qolip (template) yo'q: AI koordinat, rang va tuzilmani o'zi belgilaydi.
"""
import logging
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

log = logging.getLogger("layouts")

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

ALIGN_MAP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


def _hex(hex_str: str) -> RGBColor:
    h = (hex_str or "000000").lstrip("#").strip()
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) != 6:
        return RGBColor(0, 0, 0)
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def render_canvas(slide, s, image_paths: dict):
    """
    s — Slide modeli.
    image_paths — {element_id: local_path} image elementlari uchun.
    """
    # Fon rangi
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = _hex(s.canvas.background)

    for el in s.canvas.elements:
        try:
            if el.type == "rect":
                _draw_rect(slide, el)
            elif el.type == "text":
                _draw_text(slide, el)
            elif el.type == "circle":
                _draw_circle(slide, el)
            elif el.type == "image":
                img_path = image_paths.get(id(el))
                if img_path:
                    _draw_image(slide, el, img_path)
        except Exception as exc:
            log.warning("Element chizishda xato (%s, slayd %s): %s", el.type, s.index, exc)


# ─────────────────────────────────────────────────────────── rect

def _draw_rect(slide, el):
    w = _clamp(el.w or 1.0, 0.05, 13.333)
    h = _clamp(el.h or 1.0, 0.05, 7.5)
    x = _clamp(el.x, -2.0, 13.333)   # biroz tashqarida bo'lishiga ruxsat (dizayn uchun)
    y = _clamp(el.y, -2.0, 7.5)

    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if el.radius else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    if el.fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _hex(el.fill)
    else:
        shp.fill.background()
    shp.line.fill.background()


# ─────────────────────────────────────────────────────────── text

def _draw_text(slide, el):
    w = _clamp(el.w or 5.0, 0.5, 13.333)
    h = _clamp(el.h or 1.0, 0.2, 7.5)
    x = _clamp(el.x, 0.0, 13.0)
    y = _clamp(el.y, 0.0, 7.3)

    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0

    p = tf.paragraphs[0]
    p.alignment = ALIGN_MAP.get(el.align or "left", PP_ALIGN.LEFT)

    run = p.add_run()
    run.text = el.text or ""
    run.font.size = Pt(_clamp(el.size or 14, 8, 72))
    run.font.bold = el.bold
    run.font.italic = el.italic
    run.font.name = el.font or "Calibri"
    if el.color:
        run.font.color.rgb = _hex(el.color)


# ─────────────────────────────────────────────────────────── circle

def _draw_circle(slide, el):
    d = _clamp(el.d or 1.0, 0.1, 10.0)
    x = _clamp(el.x, -3.0, 13.0)   # dekorativ aylonalar qisman tashqarida bo'lishi mumkin
    y = _clamp(el.y, -3.0, 7.5)

    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    shp.shadow.inherit = False
    if el.fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _hex(el.fill)
    else:
        shp.fill.background()
    shp.line.fill.background()


# ─────────────────────────────────────────────────────────── image

def _draw_image(slide, el, img_path: str):
    w = _clamp(el.w or 5.0, 0.5, 13.333)
    h = _clamp(el.h or 4.0, 0.5, 7.5)
    x = _clamp(el.x, 0.0, 13.0)
    y = _clamp(el.y, 0.0, 7.0)
    slide.shapes.add_picture(img_path, Inches(x), Inches(y), Inches(w), Inches(h))
