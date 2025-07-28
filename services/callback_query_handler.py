# services/callback_query_handler.py
import logging
import random
from typing import TYPE_CHECKING
from telegram import Update
import asyncio
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
        elif action_type == "RESET":
            await self._handle_reset(query, note_id, user_plan, user_lang)
        elif action_type == "PACK":
            pack_code = parts[1]
            await self._handle_quick_pack(query, note_id, user_plan, pack_code, user_lang)
        elif action_type == "IGNORE":
            pass

    async def _update_menu(self, query: Update.callback_query, note_id: ObjectId, user_plan: str,
                           selected_options: list, lang_code: str):
        """
        Радикально обновляет меню с принудительным изменением контента.
        """
        import time

        text, markup = self.ui.get_checkbox_selection_menu(lang_code, note_id, user_plan, selected_options)

        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            try:
                # Попытка обновления
                await query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                logger.info(f"Меню успешно обновлено для заметки {note_id} (попытка {attempt + 1})")
                return

            except Exception as e:
                if "Message is not modified" in str(e):
                    attempt += 1
                    logger.warning(f"Сообщение не изменилось, попытка {attempt}/{max_attempts}")

                    if attempt < max_attempts:
                        # Добавляем случайные символы и пробуем снова
                        import random
                        random_suffix = ''.join([
                                                    '\u200B',  # Zero Width Space
                                                    '\u200C',  # Zero Width Non-Joiner
                                                    '\u200D',  # Zero Width Joiner
                                                ][random.randint(0, 2)] for _ in range(random.randint(1, 4)))

                        text = text + random_suffix
                        # Небольшая задержка перед повторной попыткой
                        await asyncio.sleep(0.1)
                    else:
                        # Последняя попытка - полная замена сообщения
                        try:
                            await query.delete_message()
                            await asyncio.sleep(0.2)

                            # Отправляем новое сообщение
                            new_message = await query.message.reply_text(
                                text=text,
                                reply_markup=markup,
                                parse_mode='Markdown'
                            )
                            logger.info(f"Меню пересоздано для заметки {note_id}")
                            return

                        except Exception as delete_error:
                            logger.error(f"Не удалось пересоздать сообщение: {delete_error}")

                else:
                    logger.error(f"Ошибка при обновлении меню для заметки {note_id}: {e}", exc_info=True)
                    return

    async def _handle_checkbox_toggle(self, query, note_id, user_plan, selected, option_code, lang_code):
        limit = TARIFF_LIMITS.get(user_plan, TARIFF_LIMITS['free'])['checkboxes']

        if option_code in selected:
            selected.remove(option_code)
        else:
            if len(selected) < limit:
                selected.append(option_code)
            else:
                await query.answer("Достигнут лимит по вашему тарифу!", show_alert=True)
                return

        self.db.update_note(note_id, {"$set": {"selection_state": {"selected": selected}}})
        await self._update_menu(query, note_id, user_plan, selected, lang_code)

    async def _handle_quick_pack(self, query, note_id, user_plan, pack_code, lang_code):
        limit = TARIFF_LIMITS.get(user_plan, TARIFF_LIMITS['free'])['checkboxes']
        pack_options = QUICK_PACKS.get(pack_code, {}).get('options', [])

        if len(pack_options) > limit:
            await query.answer(f"Этот пакет требует {len(pack_options)} опции. Ваш лимит: {limit}.", show_alert=True)
            return

        self.db.update_note(note_id, {"$set": {"selection_state": {"selected": pack_options}}})
        await self._update_menu(query, note_id, user_plan, pack_options, lang_code)

    async def _handle_reset(self, query, note_id, user_plan, lang_code):
        self.db.update_note(note_id, {"$set": {"selection_state": {"selected": []}}})
        await self._update_menu(query, note_id, user_plan, [], lang_code)

    async def _handle_process_start(self, query, note, selected_options, lang_code):
        if not selected_options:
            await query.answer("Пожалуйста, выберите хотя бы одну опцию.", show_alert=True)
            return

        await query.edit_message_text(f"🚀 Задание принято! Начинаем обработку...")

        platform_payload = {
            'platform': 'telegram',
            'chat_id': query.message.chat_id,
            'lang_code': lang_code,
            'note_id': str(note['_id'])
        }
        task_kwargs = {'selected_options': selected_options}

        s3_key = note.get('s3_object_key') or note.get('s3_key')
        if not s3_key:
            await query.edit_message_text("Ошибка: не удалось найти ключ файла S3.")
            return

        self.celery_app_client.send_task(
            'tasks.process_media_v2',
            args=[note['user_id'], s3_key, {}, platform_payload],
            kwargs=task_kwargs
        )
