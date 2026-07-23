import logging
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from . import config
from .pipeline import generate_presentation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Menga taqdimot mavzusini yozing (masalan: \"Fotosintez jarayoni\" yoki "
        "\"O'zbekiston iqtisodiyoti 2025\"), men sizga dizayni mavzuga mos, sifat nazoratidan "
        "o'tgan .pptx tayyorlab beraman."
    )


async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text.strip()
    if not topic:
        await update.message.reply_text("Iltimos, mavzuni matn sifatida yuboring.")
        return

    status_msg = await update.message.reply_text(
        f"⚙️ \"{topic}\" mavzusida taqdimot tayyorlanmoqda...\n\n"
        "⏳ 1/4 — Kontent va dizayn rejalashtirilimoqda (Claude Sonnet)..."
    )

    import asyncio
    from .pipeline import generate_brief_with_validation, canvas_validation_and_fix, build_presentation, run_visual_qa_and_fix
    from .renderer import build_presentation as _build

    try:
        # 1 — Brief
        loop = asyncio.get_event_loop()
        brief = await loop.run_in_executor(None, generate_brief_with_validation, topic)
        await status_msg.edit_text(
            f"⚙️ \"{topic}\" mavzusida taqdimot tayyorlanmoqda...\n\n"
            f"✅ 1/4 — Brief tayyor ({len(brief.slides)} slayd)\n"
            "⏳ 2/4 — Strukturaviy tekshiruv..."
        )

        # 2 — Strukturaviy tekshiruv
        brief = await loop.run_in_executor(None, canvas_validation_and_fix, brief, topic)
        await status_msg.edit_text(
            f"⚙️ \"{topic}\" mavzusida taqdimot tayyorlanmoqda...\n\n"
            f"✅ 1/4 — Brief tayyor ({len(brief.slides)} slayd)\n"
            "✅ 2/4 — Strukturaviy tekshiruv o'tdi\n"
            "⏳ 3/4 — Slaydlar chizilmoqda (python-pptx)..."
        )

        # 3 — Render
        pptx_path = await loop.run_in_executor(None, _build, brief)
        await status_msg.edit_text(
            f"⚙️ \"{topic}\" mavzusida taqdimot tayyorlanmoqda...\n\n"
            f"✅ 1/4 — Brief tayyor ({len(brief.slides)} slayd)\n"
            "✅ 2/4 — Strukturaviy tekshiruv o'tdi\n"
            "✅ 3/4 — Slaydlar chizildi\n"
            "⏳ 4/4 — Vizual QA va tuzatish (LibreOffice + Vision AI)..."
        )

        # 4 — Vizual QA
        final_path = await loop.run_in_executor(None, run_visual_qa_and_fix, pptx_path, brief, topic)

    except Exception as e:
        log.exception("Taqdimot generatsiyasida xato")
        await status_msg.edit_text(
            f"Kechirasiz, taqdimotni yaratishda xatolik yuz berdi:\n`{e}`\n"
            "Iltimos, birozdan so'ng qayta urinib ko'ring.",
            parse_mode="Markdown",
        )
        return

    await status_msg.edit_text(
        f"✅ \"{topic}\" — taqdimot tayyor!\n\n"
        f"📊 {len(brief.slides)} slayd | Vizual QA o'tdi | Yuborilmoqda..."
    )
    with open(final_path, "rb") as f:
        await update.message.reply_document(document=f, filename=os.path.basename(final_path))


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment o'zgaruvchisi topilmadi")

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_topic))

    log.info("Bot ishga tushdi (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
