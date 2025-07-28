# services/callback_query_handler.py
import logging
from typing import TYPE_CHECKING
from telegram import Update
from bson import ObjectId, errors as bson_errors

from .processing_config import TARIFF_LIMITS, QUICK_PACKS

if TYPE_CHECKING:
    from .telegram_handler import TelegramHandler

logger = logging.getLogger(__name__)


class CallbackQueryHandler:
    def __init__(self, main_handler: 'TelegramHandler'):
        self.main_handler = main_handler
        self.bot = main_handler.bot
        self.db = main_handler.database
        self.ui = main_handler.ui
        self.celery_app_client = main_handler.celery_app_client

    async def handle(self, query: Update.callback_query, user_lang: str):
        await query.answer()
        payload = query.data
        parts = payload.split('_')
        action_type = parts[0]

        try:
            note_id_str = parts[-1]
            note_id = ObjectId(note_id_str)
            note = self.db.get_note_by_id(note_id)
            if not note:
                await query.edit_message_text("Задача обработки устарела или была удалена.", reply_markup=None)
                return
        except (IndexError, bson_errors.InvalidId):
            logger.warning(f"Could not parse note_id from callback: {payload}")
            return

        user_id = str(query.from_user.id)
        user = self.db.get_user(user_id)
        user_plan = user.get('plan', 'free')

        ADMIN_ID = "588450053"
        if user_id == ADMIN_ID:
            user_plan = 'pro'

        selection_state = note.get('selection_state', {'selected': []})
        selected_options = selection_state.get('selected', [])

        if action_type == "CHECKBOX":
            option_code = parts[1]
            await self._handle_checkbox_toggle(query, note_id, user_plan, selected_options, option_code, user_lang)
        elif action_type == "PROCESS":
            await self._handle_process_start(query, note, selected_options, user_lang)
        # Добавьте здесь обработку других action_type (PACK, RESET...)

    async def _update_menu(self, query: Update.callback_query, note_id: ObjectId, user_plan: str,
                           selected_options: list, lang_code: str):
        """
        Надежно обновляет меню, всегда отправляя и текст, и клавиатуру.
        """
        text, markup = self.ui.get_checkbox_selection_menu(lang_code, note_id, user_plan, selected_options)
        try:
            await query.edit_message_text(text=text, reply_markup=markup)
        except Exception as e:
            # Игнорируем ошибку "Message is not modified", так как это нормальное поведение
            if "Message is not modified" not in str(e):
                logger.error(f"Не удалось обновить меню выбора: {e}", exc_info=True)

    async def _handle_checkbox_toggle(self, query, note_id, user_plan, selected, option_code, lang_code):
        limit = TARIFF_LIMITS.get(user_plan, TARIFF_LIMITS['free'])['checkboxes']

        if option_code in selected:
            selected.remove(option_code)
        else:
            if len(selected) < limit:
                selected.append(option_code)
            else:
                await query.answer("Достигнут лимит по вашему тарифу! Повысьте тариф, чтобы выбрать больше.",
                                   show_alert=True)
                return

        self.db.update_note(note_id, {"$set": {"selection_state": {"selected": selected}}})
        await self._update_menu(query, note_id, user_plan, selected, lang_code)

    async def _handle_process_start(self, query, note, selected_options, lang_code):
        if not selected_options:
            await query.answer("Пожалуйста, выберите хотя бы одну опцию для обработки.", show_alert=True)
            return

        await query.edit_message_text(
            f"🚀 Задание принято! Начинаем обработку {len(selected_options)} опций...")

        platform_payload = {
            'platform': 'telegram',
            'chat_id': query.message.chat_id,
            'lang_code': lang_code,
            'note_id': str(note['_id'])  # Передаем note_id в payload
        }
        task_kwargs = {'selected_options': selected_options}

        s3_key = note.get('s3_object_key') or note.get('s3_key')
        if not s3_key:
            await query.edit_message_text("Ошибка: не удалось найти ключ файла в S3.")
            return

        self.celery_app_client.send_task(
            'tasks.process_media_v2',
            args=[note['user_id'], s3_key, {}, platform_payload],
            kwargs=task_kwargs
        )
