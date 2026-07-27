import re
from typing import Any, List, Optional, Literal
from pydantic import BaseModel, field_validator

Role = Literal["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]
ROLE_ORDER = ["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]


class VisualElement(BaseModel):
    """Slayddagi bitta vizual element."""
    type: Literal["rect", "text", "circle", "image", "chart"]
    x: float
    y: float
    w: Optional[float] = None
    h: Optional[float] = None
    # rect / circle rangi
    fill: Optional[str] = None
    radius: bool = False
    # matn
    text: Optional[str] = None
    size: float = 14
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None
    align: Literal["left", "center", "right"] = "left"
    font: str = "Calibri"
    # circle
    d: Optional[float] = None
    # image
    prompt: Optional[str] = None
    # chart
    chart_type: Optional[Literal["bar", "column", "line", "pie", "donut"]] = None
    chart_title: Optional[str] = None
    caption: Optional[str] = None   # diagramma ostida ko'rsatiladigan izoh matni
    categories: Optional[List[str]] = None
    series: Optional[List[Any]] = None   # [{"name": str, "values": [float, ...]}]


class Theme(BaseModel):
    primary: str
    accent: str
    light: str
    heading_font: str = "Calibri"
    body_font: str = "Calibri"


class SlideCanvas(BaseModel):
    background: str
    elements: List[VisualElement]


class Slide(BaseModel):
    index: int
    role: Role
    title: str
    key_text: str

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
    if slide.role not in ("detail", "comparison"):
        return True
    return bool(GROUNDING_PATTERN.search(slide.all_text()))
