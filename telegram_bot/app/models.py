import re
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator

Role = Literal["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]

# Har role uchun ruxsat etilgan layout_type'lar (mantiqiy shablon tanlash qoidasi)
ALLOWED_LAYOUTS_BY_ROLE = {
    "hook": {"title_dark"},
    "context": {"icon_row_list", "stat_callout", "image_half_bleed", "definition_spotlight"},
    "breakdown": {
        "three_card_grid", "four_card_grid", "agenda_numbered", "timeline_process",
        "bar_chart", "xy_chart",
    },
    "detail": {
        "two_card_compare", "image_half_bleed", "icon_row_list", "stat_callout",
        "quote_callout", "math_formula", "bar_chart", "xy_chart",
    },
    "comparison": {
        "comparison_table", "two_card_compare", "stat_row_triple",
        "bar_chart", "xy_chart",
    },
    "application": {
        "image_half_bleed", "stat_callout", "timeline_process", "mini_case_study",
        "bar_chart", "math_formula",
    },
    "synthesis": {"conclusion_dark"},
}

ROLE_ORDER = ["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]


class Palette(BaseModel):
    primary: str
    secondary: str
    accent: str


class FontPair(BaseModel):
    heading: str = "Calibri"
    body: str = "Calibri"


class CardItem(BaseModel):
    heading: str
    body: str
    example: Optional[str] = None


class ChartPoint(BaseModel):
    """XY diagrammasi yoki bar chart uchun bitta ma'lumot nuqtasi."""
    label: str               # X o'qi yoki bar nomi
    value: float             # Y qiymati


class ChartData(BaseModel):
    """bar_chart va xy_chart layoutlari uchun diagramma ma'lumotlari."""
    x_label: str             # X o'qi sarlavhasi
    y_label: str             # Y o'qi sarlavhasi
    unit: str = ""           # Y birlik (masalan: %, mln, °C)
    points: List[ChartPoint] # Ma'lumot nuqtalari (kamida 3 ta)


class MathBlock(BaseModel):
    """math_formula layouti uchun bitta formula bloki."""
    formula: str             # Formulaning matn ko'rinishi, masalan: "E = mc²"
    description: str         # Formulaning izohi (1-2 jumla)


class Slide(BaseModel):
    index: int
    role: Role
    layout_type: str
    title: Optional[str] = None
    hook_line: Optional[str] = None
    subtitle: Optional[str] = None
    body: Optional[str] = None
    items: Optional[List[CardItem]] = None
    image_prompt: Optional[str] = None
    key_takeaways: Optional[List[str]] = None
    closing_thought: Optional[str] = None
    # Yangi diagramma/formula maydonlari
    chart_data: Optional[ChartData] = None
    math_blocks: Optional[List[MathBlock]] = None

    def all_text(self) -> str:
        parts = [self.title, self.hook_line, self.subtitle, self.body, self.closing_thought]
        if self.items:
            for it in self.items:
                parts += [it.heading, it.body, it.example]
        if self.key_takeaways:
            parts += self.key_takeaways
        if self.math_blocks:
            for mb in self.math_blocks:
                parts += [mb.formula, mb.description]
        return " ".join([p for p in parts if p])


class Brief(BaseModel):
    topic: str
    palette: Palette
    font_pair: FontPair
    motif: Literal["icon_circle", "numbered_badge", "rounded_frame"] = "numbered_badge"
    slides: List[Slide]

    @field_validator("slides")
    @classmethod
    def check_roles_and_layouts(cls, slides: List[Slide]):
        if not slides:
            raise ValueError("Slaydlar ro'yxati bo'sh")

        # 1) role ketma-ketligi orqaga qaytmasligi kerak
        last_rank = -1
        for s in slides:
            rank = ROLE_ORDER.index(s.role)
            if rank < last_rank:
                raise ValueError(f"Role tartibi buzilgan: slayd {s.index} ({s.role}) oldingi rolelardan orqada")
            last_rank = rank

        # 2) hook faqat birinchi, synthesis faqat oxirgi slaydda
        if slides[0].role != "hook":
            raise ValueError("Birinchi slayd role='hook' bo'lishi shart")
        if slides[-1].role != "synthesis":
            raise ValueError("Oxirgi slayd role='synthesis' bo'lishi shart")

        # 3) har slayd uchun layout_type shu role'ga ruxsat etilganmi
        for s in slides:
            allowed = ALLOWED_LAYOUTS_BY_ROLE.get(s.role, set())
            if s.layout_type not in allowed:
                raise ValueError(
                    f"Slayd {s.index}: layout_type='{s.layout_type}' role='{s.role}' uchun ruxsat etilmagan "
                    f"(ruxsat etilganlar: {sorted(allowed)})"
                )

        # 4) ketma-ket ikki slayd bir xil layout ishlatmasin
        for i in range(1, len(slides)):
            if slides[i].layout_type == slides[i - 1].layout_type:
                raise ValueError(
                    f"Slayd {slides[i].index}: oldingi slayd bilan bir xil layout_type ('{slides[i].layout_type}') qaytarilgan"
                )

        return slides


GROUNDING_PATTERN = re.compile(r"\d|(?:[A-ZЎҚҲЁ][a-zʻ'']+\s+[A-ZЎҚҲЁ][a-zʻ'']+)")


def grounding_check(slide: Slide) -> bool:
    """Slaydda kamida bitta raqam yoki atoqli ot (2 so'zli, bosh harfli ibora) borligini tekshiradi.
    Faqat detail/comparison rolelariga qo'llaniladi."""
    if slide.role not in ("detail", "comparison"):
        return True
    text = slide.all_text()
    return bool(GROUNDING_PATTERN.search(text))
