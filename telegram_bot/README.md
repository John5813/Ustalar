# Taqdimot generator — Telegram bot

Mavzu yuborilganda: OpenRouter mazmun+dizaynni JSON tarzida rejalashtiradi → qat'iy qoidalar bilan
tekshiriladi (validatsiya, mantiqiy ketma-ketlik, faktik asoslilik) → Together AI kerakli slaydlarga
rasm yaratadi → python-pptx orqali qo'lda chiziladi (standart shablonlar ishlatilmaydi) → LibreOffice
orqali rasmga aylantirilib, vision-model "ko'zi bilan" tekshiriladi → muammo topilsa tegishli slayd
qayta yoziladi va qayta chiziladi (max `MAX_QA_RETRIES` marta) → tayyor `.pptx` Telegram'ga yuboriladi.

## Papka strukturasi

```
telegram_ppt_bot/
├── main.py                # kirish nuqtasi
├── requirements.txt
├── .env.example
├── replit.nix             # LibreOffice + poppler tizim paketlari (Replit uchun)
└── app/
    ├── config.py           # environment o'zgaruvchilar
    ├── models.py           # pydantic sxema + validatsiya qoidalari (role tartibi, layout cheklovlari, grounding)
    ├── llm_client.py       # OpenRouter: brief generatsiyasi + bitta slaydni qayta yozish
    ├── image_client.py     # Together AI rasm generatsiyasi
    ├── layouts.py          # python-pptx bilan har layout_type'ni "qo'lda" chizuvchi funksiyalar
    ├── renderer.py         # brief -> to'liq .pptx
    ├── qa.py               # pptx->JPG (LibreOffice+poppler) + vision-model tekshiruvi
    ├── pipeline.py         # to'liq oqim: generatsiya -> validatsiya -> render -> QA -> tuzatish
    └── bot.py              # Telegram handlerlar
```

## O'rnatish (Replit)

1. Loyihani Replit'ga yuklang (zip'ni import qiling yoki fayllarni ko'chiring).
2. **Secrets** panelidan (`.env` emas!) quyidagilarni kiriting:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENROUTER_API_KEY`
   - `TOGETHER_API_KEY`
3. `replit.nix` fayli LibreOffice va poppler-utils'ni avtomatik o'rnatadi (vizual QA uchun shart).
   Agar Replit muhitingiz `replit.nix`ni qo'llab-quvvatlamasa, muqobil sifatida Nix/Docker
   konfiguratsiyasida `libreoffice` va `poppler-utils` paketlarini qo'lda qo'shing.
4. Kutubxonalarni o'rnating:
   ```
   pip install -r requirements.txt
   ```
5. Ishga tushiring:
   ```
   python main.py
   ```

## Mahalliy (lokal) test

```
cp .env.example .env   # va haqiqiy kalitlarni kiriting
pip install -r requirements.txt
python main.py
```

## Nima uchun shunday qurilgan (arxitektura qarorlari)

- **JSON-brief + qattiq render funksiyalari, lekin "erkin" LLM-kod yozish emas.** To'liq "LLM o'z pptxgenjs
  kodini yozadi va bajaradi" darajasidagi erkinlik nazariy jihatdan mumkin, lekin ishlab chiqarish (production)
  muhitida ishonchsiz va xavfli (ixtiyoriy kod bajarish). Shu sababli: LLM **nima chizishni tanlaydi**
  (palette, layout_type, matn), kod esa **qanday chizishni** boshqaradi (aniq koordinata, shrift, kontrast).
  Bu ikkalasini birlashtiradi — dizayn xilma-xilligi ham, vizual barqarorlik ham saqlanadi.
- **Vision-QA tsikli haqiqiy.** `qa.py` slaydlarni chinakam rasmga aylantirib, vision-modelga ko'rsatadi va
  javobini o'qiydi — bu "LLM natijani ko'radi va tuzatadi" talabini bajaradi, faqat butun kodni emas,
  balki slayd **matni/mazmunini** qayta yozish orqali (xavfsizroq va tezroq yondashuv).
- **Silent fallback yo'q.** `pipeline.py`da har xato `log.error`/`log.warning` orqali chiqariladi —
  oldingi tizimdagi asosiy muammo ("xato yutilib, doim bir xil natija chiqishi") shu tarzda oldini olingan.

## Hozircha qo'llab-quvvatlanadigan layout'lar (15 ta)

`title_dark`, `conclusion_dark`, `agenda_numbered`, `two_card_compare`, `three_card_grid`,
`four_card_grid`, `comparison_table`, `icon_row_list`, `stat_callout`, `stat_row_triple`,
`timeline_process`, `image_half_bleed`, `quote_callout`, `definition_spotlight`, `mini_case_study`.

To'liq 22 talik ro'yxat (`before_after`, `pyramid_hierarchy`, `pros_cons_split`,
`numbered_process_grid`, `map_or_diagram_frame`, `image_full_bleed_caption`,
`two_card_compare_vertical`) texnik topshiriqda tasvirlangan — `app/layouts.py`ga xuddi
mavjudlar kabi yangi funksiya qo'shib, `LAYOUT_REGISTRY` va `models.py`dagi
`ALLOWED_LAYOUTS_BY_ROLE`ga kiritish orqali kengaytiriladi.

## Cheklovlar / keyingi qadamlar

- Vision-QA LibreOffice/poppler talab qiladi — agar Replit muhitida o'rnatib bo'lmasa, `qa.py`
  xatoni loglab, QA'siz mavjud faylni qaytaradi (bot yiqilmaydi, lekin sifat nazorati o'tkazib yuboriladi).
- `MAX_QA_RETRIES` ko'paytirilsa sifat oshadi, lekin javob vaqti va API xarajati ham oshadi — muvozanatni
  o'zingiz sozlang (`.env`dagi `MAX_QA_RETRIES`).
- Hozir bitta foydalanuvchi so'rovini ketma-ket qayta ishlaydi (sinxron). Ko'p foydalanuvchi bir vaqtda
  ishlatsa, navbat/queue yoki background worker (masalan Celery/RQ) qo'shish tavsiya etiladi.
