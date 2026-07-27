"""
Document generation queue service.

Heavy document types (kurs ishi, diplom ishi, dissertatsiya, bitiruv ishi)
are serialised through a single asyncio queue so that only ONE heavy document
is generated at a time, preventing OOM spikes on the production server.

Light documents (presentation, referat, tezis, maqola, mustaqil ish, …)
bypass the queue entirely and are generated immediately.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

HEAVY_DOC_TYPES = {"course_work", "diploma_work", "dissertatsiya", "bitiruv_ishi"}

# Estimated generation time in seconds per document type (used for progress bar)
_EST_SECONDS: dict[str, int] = {
    "course_work":   360,
    "diploma_work":  540,
    "dissertatsiya": 720,
    "bitiruv_ishi":  480,
}

# ── Localisable strings ───────────────────────────────────────────────────────
_L: dict[str, dict[str, str]] = {
    "queue_added": {
        "uz": "📂 Hujjat navbatga qo'shildi",
        "ru": "📂 Документ добавлен в очередь",
        "en": "📂 Document added to queue",
    },
    "queue_pos": {
        "uz": "📋 Navbatdagi o'rningiz",
        "ru": "📋 Ваша позиция в очереди",
        "en": "📋 Your queue position",
    },
    "ahead": {
        "uz": "🔄 Oldingizda",
        "ru": "🔄 Перед вами",
        "en": "🔄 Before you",
    },
    "docs_word": {
        "uz": "ta hujjat",
        "ru": "документ(ов)",
        "en": "document(s)",
    },
    "waited": {
        "uz": "⏳ Kutdingiz",
        "ru": "⏳ Ожидаете",
        "en": "⏳ Waited",
    },
    "generating": {
        "uz": "⚡ Hujjatingiz tayyorlanmoqda!",
        "ru": "⚡ Ваш документ готовится!",
        "en": "⚡ Your document is being generated!",
    },
    "elapsed": {
        "uz": "⏱ O'tgan vaqt",
        "ru": "⏱ Прошло",
        "en": "⏱ Elapsed",
    },
    "starting_now": {
        "uz": "✨ Sizning navbatingiz keldi! Generatsiya boshlanmoqda...",
        "ru": "✨ Ваша очередь подошла! Генерация начинается...",
        "en": "✨ It's your turn! Generation starting...",
    },
}

_DOC_NAMES: dict[str, dict[str, str]] = {
    "course_work":   {"uz": "Kurs ishi",       "ru": "Курсовая работа",   "en": "Course Work"},
    "diploma_work":  {"uz": "Diplom ishi",      "ru": "Дипломная работа",  "en": "Diploma Work"},
    "dissertatsiya": {"uz": "Dissertatsiya",    "ru": "Диссертация",       "en": "Dissertation"},
    "bitiruv_ishi":  {"uz": "Bitiruv ishi",     "ru": "Выпускная работа",  "en": "Graduation Work"},
}

# ── Rotating fun facts ─────────────────────────────────────────────────────────
_FACTS: dict[str, list[str]] = {
    "uz": [
        "📚 Birinchi dissertatsiya 1500-yillarda Italiyada yoqlangan va 3 soat davom etgan!",
        "✍️ Akademik yozuvda har bir fikr: tezis → dalil → xulosa shaklida bo'lishi kerak.",
        "📖 O'zbekistonda har yili 15 000 dan ortiq ilmiy maqola chop etiladi.",
        "🎓 Bitiruv ishi o'rtacha 4 oylik izlanishni talab qiladi.",
        "📝 Adabiyotlar tahlili kurs ishining eng muhim qismi — u 30-40% hajmni egallaydi.",
        "🔬 Metodologiya bo'limida kamida 2 ta tadqiqot usuli ko'rsatilishi tavsiya etiladi.",
        "💡 Yaxshi sarlavha: mavzu + usul + natijani aks ettirishi kerak.",
        "📊 Jadval va grafiklar diplomingizni 40% ga tushunarliroq qiladi.",
        "🏛️ Oksford universiteti 1096-yilda tashkil topgan — dunyodagi eng qadimiy universitetlardan biri.",
        "📌 Har 1000 ta talabadan faqat 150 tasi magistraturada tahsil oladi.",
        "⏱️ O'rtacha kurs ishi yozish 80–120 soat vaqt talab qiladi.",
        "🌍 Dunyoda har yili 4 milliondan ortiq ilmiy maqola nashr etiladi.",
        "📋 Referatlarda kirish qismi umumiy hajmning 10–15% ini tashkil qilishi kerak.",
        "🧠 Miya vizual ma'lumotni matndan 6 marta tezroq eslab qoladi!",
        "✅ Plagiatdan himoya uchun parafraz eng samarali usul hisoblanadi.",
        "📄 Har bir bob kamida 3 ta kichik bo'limdan iborat bo'lishi tavsiya etiladi.",
        "🔑 Kalit so'zlar 5–7 ta bo'lsa, maqola ko'proq topiladi.",
        "📈 Grafik va diagrammalar matnni 40% ga aniqroq qiladi.",
        "🗂️ Adabiyotlar ro'yxati alifbo tartibida yoki iqtibos tartibida berilishi mumkin.",
        "💬 Ilmiy matnda 'men' o'rniga passiv shakl ishlatish tavsiya etiladi.",
        "🌟 IELTS Writing Task 2 da 250 so'z 40 daqiqada yoziladi — bu o'rtacha 6 so'z/daqiqa!",
        "📔 Eng uzun dissertatsiya 1500 betga yetgan — u Frankfurt universitetida himoya qilingan.",
    ],
    "ru": [
        "📚 Первая диссертация была защищена в Италии в 1500-х годах и длилась 3 часа!",
        "✍️ В академическом письме: тезис → доказательство → вывод — основа каждого аргумента.",
        "📖 В России ежегодно публикуется более 50 000 научных статей.",
        "🎓 Средняя дипломная работа требует 4 месяца исследований.",
        "📝 Обзор литературы занимает 30–40% объёма и считается самой сложной частью.",
        "🔬 В методологии рекомендуется указать не менее 2 методов исследования.",
        "💡 Хорошее название отражает: тему + метод + результат.",
        "📊 Таблицы и графики делают дипломную работу на 40% понятнее.",
        "🏛️ Болонский университет (1088 г.) — старейший в мире.",
        "📌 Только 15% студентов продолжают обучение в магистратуре.",
        "⏱️ Написание курсовой работы занимает в среднем 80–120 часов.",
        "🌍 В мире ежегодно публикуется более 4 миллионов научных статей.",
        "📋 Введение реферата должно составлять 10–15% общего объёма.",
        "🧠 Мозг запоминает визуальную информацию в 6 раз лучше текстовой.",
        "✅ Перефразирование — лучший способ защиты от плагиата.",
        "📄 Каждая глава должна содержать не менее 3 подразделов.",
        "🔑 Оптимальное количество ключевых слов — 5–7.",
        "📈 Диаграммы повышают понимание материала на 40%.",
        "🗂️ Список литературы может быть алфавитным или по порядку цитирования.",
        "💬 В научном тексте избегайте местоимения «я» — используйте пассивный залог.",
        "🌟 Самая длинная диссертация — 1500 страниц, защищена во Франкфурте.",
        "📔 В среднем для PhD нужно прочитать 200+ научных работ.",
    ],
    "en": [
        "📚 The first dissertation was defended in Italy in the 1500s and lasted 3 hours!",
        "✍️ Every academic argument needs a claim, evidence, and conclusion.",
        "📖 Over 4 million scientific articles are published worldwide every year.",
        "🎓 An average thesis requires 4 months of dedicated research.",
        "📝 The literature review is the hardest part, covering 30–40% of the work.",
        "🔬 Good methodology sections describe at least 2 research methods.",
        "💡 A great title reflects: topic + method + outcome.",
        "📊 Visuals and tables make academic work 40% easier to understand.",
        "🏛️ The University of Bologna (1088) is the world's oldest university.",
        "📌 Only 15% of undergraduates continue to graduate school.",
        "⏱️ Writing a term paper takes an average of 80–120 hours.",
        "🌍 Harvard Library holds over 20 million books — the largest academic collection.",
        "📋 Your introduction should be 10–15% of the total paper length.",
        "🧠 The brain retains visual information 6× better than plain text.",
        "✅ Paraphrasing is the best technique to avoid plagiarism.",
        "📄 Each chapter should have at least 3 subsections.",
        "🔑 The ideal number of keywords per paper is 5–7.",
        "📈 Charts and graphs improve comprehension by up to 40%.",
        "🗂️ References can be ordered alphabetically or by citation order.",
        "💬 Use passive voice in academic writing instead of 'I' or 'we'.",
        "🌟 The longest dissertation ever — 1,500 pages, defended in Frankfurt.",
        "📔 A typical PhD requires reading 200+ academic papers.",
    ],
}

_SPINNERS = ["◐", "◓", "◑", "◒"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _t(key: str, lang: str) -> str:
    d = _L.get(key, {})
    return d.get(lang) or d.get("uz", key)


def _fmt_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    if m > 0:
        return f"{m} daq {s:02d} sek"
    return f"{s} sek"


def _progress_bar(elapsed: float, estimated: float, width: int = 10) -> str:
    ratio = min(elapsed / max(estimated, 1), 0.92)
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(ratio * 100)
    return f"[{bar}] {pct}%"


# ── Core dataclass ────────────────────────────────────────────────────────────
@dataclass
class HeavyDocTask:
    task_id: str
    coro_factory: Callable[[], Coroutine]
    user_telegram_id: int
    chat_id: int
    lang: str
    doc_type: str
    topic: str
    bot: Any
    done_event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: float = field(default_factory=time.time)


# ── Queue ─────────────────────────────────────────────────────────────────────
class DocumentQueue:
    """Single-worker asyncio queue for heavy document generation."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pending: list[str] = []        # task_ids waiting (not yet started)
        self._lock = asyncio.Lock()
        self._active_task_id: Optional[str] = None
        self._active_start: Optional[float] = None

    def start(self) -> None:
        # Self-restarting supervisor — if the worker task ever dies for any
        # reason, the supervisor restarts it after a short delay so the queue
        # never permanently stops processing.
        async def _supervisor():
            while True:
                worker_task = asyncio.create_task(self._worker())
                try:
                    await worker_task
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Queue: worker crashed, restarting in 2s: {e}", exc_info=True)
                    await asyncio.sleep(2)
        asyncio.create_task(_supervisor())

    async def enqueue(self, task: HeavyDocTask) -> int:
        """Add task; returns 1-based position (1 = next to run)."""
        async with self._lock:
            self._pending.append(task.task_id)
            await self._queue.put(task)
            return len(self._pending)

    def position_of(self, task_id: str) -> int:
        try:
            return self._pending.index(task_id) + 1
        except ValueError:
            return 0

    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def active_task_id(self) -> Optional[str]:
        return self._active_task_id

    async def _worker(self) -> None:
        # Outer loop never dies — even an unexpected exception in the inner
        # body is logged and the worker keeps draining the queue. Pending
        # tasks are guaranteed to either run or have done_event fired so users
        # are never left staring at a dangling animated status message.
        while True:
            try:
                task: HeavyDocTask = await self._queue.get()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Queue: error pulling task: {e}", exc_info=True)
                await asyncio.sleep(1)
                continue

            async with self._lock:
                if task.task_id in self._pending:
                    self._pending.remove(task.task_id)
                self._active_task_id = task.task_id
                self._active_start = time.time()
            try:
                logger.info(f"Queue: starting {task.doc_type} for user {task.user_telegram_id}")
                await task.coro_factory()
            except asyncio.CancelledError:
                # Worker is being shut down — mark task done so animation exits
                task.done_event.set()
                raise
            except Exception as e:
                logger.error(f"Queue worker error ({task.doc_type}): {e}", exc_info=True)
            finally:
                # ALWAYS fire done_event so the animated status loop exits even
                # if the user's coro_factory raised an unexpected error.
                if not task.done_event.is_set():
                    task.done_event.set()
                async with self._lock:
                    self._active_task_id = None
                    self._active_start = None
                try:
                    self._queue.task_done()
                except ValueError:
                    pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_queue_instance: Optional[DocumentQueue] = None


def get_doc_queue() -> DocumentQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = DocumentQueue()
    return _queue_instance


# ── Initial status text (sent before animation loop starts) ───────────────────
def build_initial_status_text(lang: str, doc_type: str, topic: str, position: int) -> str:
    L = lang if lang in ("uz", "ru", "en") else "uz"
    topic_short = topic[:45] + ("…" if len(topic) > 45 else "")
    doc_name = _DOC_NAMES.get(doc_type, {}).get(L, doc_type)
    fact = random.choice(_FACTS.get(L, _FACTS["uz"]))
    if position <= 1:
        bar = _progress_bar(0, _EST_SECONDS.get(doc_type, 480))
        return (
            f"{_t('generating', L)}\n"
            f"📄 <b>{doc_name}:</b> {topic_short}\n\n"
            f"{bar}\n"
            f"{_t('elapsed', L)}: <b>0 sek</b>\n\n"
            f"{fact}"
        )
    ahead = position - 1
    return (
        f"{_t('queue_added', L)}\n"
        f"📄 <b>{topic_short}</b>\n\n"
        f"◐ {_t('queue_pos', L)}: <b>{position}</b>\n"
        f"{_t('ahead', L)}: <b>{ahead}</b> {_t('docs_word', L)}\n"
        f"{_t('waited', L)}: <b>0 sek</b>\n\n"
        f"{fact}"
    )


# ── Animated status loop ──────────────────────────────────────────────────────
async def run_animated_status(
    bot: Any,
    chat_id: int,
    msg_id: int,
    task_id: str,
    lang: str,
    doc_type: str,
    topic: str,
    queue: DocumentQueue,
    done_event: asyncio.Event,
) -> None:
    """
    Background task: edits the waiting message every ~14 s with animated
    progress, queue position, elapsed time and a rotating fun fact.
    Exits when done_event is set (generation finished or failed).
    """
    L = lang if lang in ("uz", "ru", "en") else "uz"
    facts = list(_FACTS.get(L, _FACTS["uz"]))
    random.shuffle(facts)
    estimated = _EST_SECONDS.get(doc_type, 480)
    start = time.time()
    fact_idx = 0
    spin_idx = 0
    was_in_queue = queue.position_of(task_id) > 0
    transition_announced = not was_in_queue

    try:
        while not done_event.is_set():
            try:
                await asyncio.wait_for(done_event.wait(), timeout=14)
                break  # done_event fired
            except asyncio.TimeoutError:
                pass

            if done_event.is_set():
                break

            elapsed = time.time() - start
            fact = facts[fact_idx % len(facts)]
            fact_idx += 1
            spin = _SPINNERS[spin_idx % len(_SPINNERS)]
            spin_idx += 1

            topic_short = topic[:45] + ("…" if len(topic) > 45 else "")
            doc_name = _DOC_NAMES.get(doc_type, {}).get(L, doc_type)

            is_active = queue.active_task_id == task_id
            pos = queue.position_of(task_id)

            # First time we transition from queue → active, send a one-shot ping
            if is_active and not transition_announced:
                transition_announced = True
                try:
                    await bot.send_message(chat_id=chat_id, text=_t("starting_now", L))
                except Exception:
                    pass

            if is_active:
                bar = _progress_bar(elapsed, estimated)
                text = (
                    f"{_t('generating', L)}\n"
                    f"📄 <b>{doc_name}:</b> {topic_short}\n\n"
                    f"{bar}\n"
                    f"{_t('elapsed', L)}: <b>{_fmt_time(elapsed)}</b>\n\n"
                    f"{fact}"
                )
            elif pos > 0:
                ahead = pos - 1
                text = (
                    f"{_t('queue_added', L)}\n"
                    f"📄 <b>{topic_short}</b>\n\n"
                    f"{spin} {_t('queue_pos', L)}: <b>{pos}</b>\n"
                    f"{_t('ahead', L)}: <b>{ahead}</b> {_t('docs_word', L)}\n"
                    f"{_t('waited', L)}: <b>{_fmt_time(elapsed)}</b>\n\n"
                    f"{fact}"
                )
            else:
                bar = _progress_bar(elapsed, estimated)
                text = (
                    f"{_t('generating', L)}\n"
                    f"📄 <b>{topic_short}</b>\n\n"
                    f"{bar}\n"
                    f"{_t('elapsed', L)}: <b>{_fmt_time(elapsed)}</b>\n\n"
                    f"{fact}"
                )

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    parse_mode="HTML",
                )
            except Exception:
                pass  # message deleted or text unchanged — ignore

    except asyncio.CancelledError:
        pass
