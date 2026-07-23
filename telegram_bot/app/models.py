import re
from typing import List, Optional, Literal
from pydantic import BaseModel, field_validator

Role = Literal["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]
ROLE_ORDER = ["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]


class VisualElement(BaseModel):
    """Slayddagi bitta vizual element — AI koordinat va ranglarni o'zi belgilaydi."""
    type: Literal["rect", "text", "circle", "image"]
    x: float                                    # chap chegara (dyuym, 0–13.333)
    y: float                                    # yuqori chegara (dyuym, 0–7.5)
    # rect / text / image
    w: Optional[float] = None                  # kenglik
    h: Optional[float] = None                  # balandlik
    # shakl rangi (rect, circle)
    fill: Optional[str] = None                 # hex, # belgisisiz, masalan "1A1A2E"
    radius: bool = False                       # yumaloq burchak (faqat rect)
    # matn maydonlari
    text: Optional[str] = None
    size: float = 14                           # punkt
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None               # matn rangi hex
    align: Literal["left", "center", "right"] = "left"
    font: str = "Calibri"
    # aylana
    d: Optional[float] = None                 # diametr (faqat circle)
    # rasm generatsiyasi
    prompt: Optional[str] = None              # Together AI uchun inglizcha tavsif


class Theme(BaseModel):
    """Butun taqdimot bo'yicha izchil rang va shrift palitrasI."""
    primary: str      # asosiy to'q rang, hex
    accent: str       # yorqin highlight rang, hex
    light: str        # açiq/oq tona, hex
    heading_font: str = "Calibri"
    body_font: str = "Calibri"


class SlideCanvas(BaseModel):
    """AI tomonidan erkin loyihalangan slayd kanvasi."""
    background: str                # fon rangi hex
    elements: List[VisualElement]  # elementlar pastdan yuqoriga chiziladi


class Slide(BaseModel):
    index: int
    role: Role
    title: str      # QA uchun sarlavha matni
    key_text: str   # QA uchun asosiy mazmun qisqacha

    canvas: SlideCanvas

    def all_text(self) -> str:
        parts = [self.title, self.key_text]
        for el in (self.canvas.elements or []):
            if el.type == "text" and el.text:
                parts.append(el.text)
        return " ".join([p for p in parts if p])


class Brief(BaseModel):
    topic: str
    theme: Theme
    slides: List[Slide]

    @field_validator("slides")
    @classmethod
    def check_roles(cls, slides: List[Slide]):
        if not slides:
            raise ValueError("Slaydlar ro'yxati bo'sh")
        if slides[0].role != "hook":
            raise ValueError("Birinchi slayd role='hook' bo'lishi shart")
        if slides[-1].role != "synthesis":
            raise ValueError("Oxirgi slayd role='synthesis' bo'lishi shart")
        last_rank = -1
        for s in slides:
            rank = ROLE_ORDER.index(s.role)
            if rank < last_rank:
                raise ValueError(
                    f"Role tartibi buzilgan: slayd {s.index} ({s.role}) oldingi roledan orqada"
                )
            last_rank = rank
        return slides


GROUNDING_PATTERN = re.compile(r"\d|(?:[A-ZЎҚҲЁ][a-zʻ'']+\s+[A-ZЎҚҲЁ][a-zʻ'']+)")


def grounding_check(slide: Slide) -> bool:
    """detail/comparison slaydlarida kamida bitta raqam yoki atoqli ot bor-yo'qligini tekshiradi."""
    if slide.role not in ("detail", "comparison"):
        return True
    return bool(GROUNDING_PATTERN.search(slide.all_text()))
