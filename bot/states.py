from aiogram.fsm.state import State, StatesGroup

class DocumentStates(StatesGroup):
    waiting_for_edit_file = State()
    waiting_for_source_selection = State()
    waiting_for_book_file = State()
    waiting_for_book_topic = State()
    waiting_for_book_url = State()
    waiting_for_payment = State()
    waiting_for_doc_language = State()
    waiting_for_topic = State()
    waiting_for_author_name = State()
    waiting_for_university = State()
    waiting_for_faculty = State()
    waiting_for_group = State()
    waiting_for_slide_count = State()
    waiting_for_page_count = State()
    waiting_for_course_work_pages = State()
    waiting_for_diploma_work_pages = State()
    waiting_for_graduation_work_pages = State()
    waiting_for_gw_outline_choice = State()
    waiting_for_gw_plan_text = State()
    waiting_for_dissertation_pages = State()
    waiting_for_extras_choice = State()
    waiting_for_outline_choice = State()
    waiting_for_manual_outline = State()
    waiting_for_outline_confirmation = State()
    waiting_for_template = State()
    waiting_for_plan_slide_choice = State()
    waiting_for_references_choice = State()
    waiting_for_icon_choice = State()

class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_custom_amount = State()
    waiting_for_screenshot = State()

class SettingsStates(StatesGroup):
    waiting_for_promocode = State()

class AdminStates(StatesGroup):
    reviewing_payment = State()
    waiting_for_channel_id = State()
    waiting_for_channel_username = State()
    waiting_for_channel_title = State()
    waiting_for_promocode = State()
    waiting_for_deactivate_promocode = State()
    waiting_for_broadcast_message = State()
    waiting_for_broadcast_target = State()
    waiting_for_new_price = State()
    waiting_for_sample_file = State()
    waiting_for_sample_title = State()
    waiting_for_sample_description = State()
    waiting_for_block_user = State()
    waiting_for_block_reason = State()
    waiting_for_payment_amount = State()
    waiting_for_gift_amount = State()
    waiting_for_take_back_amount = State()
    waiting_for_client_search = State()
    waiting_for_new_client_input = State()
    waiting_for_client_message = State()
    waiting_for_client_add_amount = State()
    waiting_for_client_deduct_amount = State()

class PaymentResubmitStates(StatesGroup):
    waiting_for_receipt = State()
    waiting_for_amount = State()

class ConverterStates(StatesGroup):
    waiting_for_pdf = State()
    waiting_for_payment = State()

class PptxToPdfStates(StatesGroup):
    waiting_for_pptx = State()

class BookTranslateStates(StatesGroup):
    waiting_for_file = State()
    waiting_for_line_range = State()
    waiting_for_target_lang = State()
    waiting_for_payment = State()
    translating = State()
    post_translation = State()
    waiting_for_doc_topic = State()

class TestStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_question_count = State()
    waiting_for_format = State()
    generating = State()

class PremiumPresentationStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_client_name = State()
    waiting_for_level = State()
    waiting_for_slide_count = State()
    generating = State()

