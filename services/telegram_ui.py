# services/telegram_ui.py - Вариант с простыми кнопками
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any, Tuple
from bson import ObjectId
import time
import hashlib

from .localization_service import LocalizationService
from .processing_config import CHECKBOX_CONFIG, QUICK_PACKS, TARIFF_LIMITS


class TelegramUI:
    def __init__(self, localizer: LocalizationService):
        self.localizer = localizer

    def get_welcome_message(self, lang_code: str) -> str:
        return self.localizer.get_string(lang_code, 'welcome_message',
                                         default="Добро пожаловать! Отправьте мне аудио, видео или ссылку для начала работы.")

    def get_checkbox_selection_menu(self, lang_code: str, note_id: ObjectId, user_plan: str,
                                    selected_options: List[str]) -> Tuple[str, InlineKeyboardMarkup]:
        limit = TARIFF_LIMITS.get(user_plan, TARIFF_LIMITS['free'])
        selected_count = len(selected_options)
        limit_reached = selected_count >= limit['checkboxes']

        # Создаем уникальный хэш для каждого состояния
        state_string = f"{note_id}_{user_plan}_{sorted(selected_options)}_{int(time.time())}"
        state_hash = hashlib.md5(state_string.encode()).hexdigest()[:8]

        header = f"🎛 **ВЫБЕРИТЕ ОБРАБОТКУ**\n"
        header += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        header += f"📋 План: **{limit['name']}** | Лимит: **{limit['checkboxes']}**\n"
        header += f"📊 Выбрано: **{selected_count} из {limit['checkboxes']}**\n"

        if selected_count > 0:
            selected_names = []
            all_options_map = {item['code']: item['label'] for category in CHECKBOX_CONFIG.values() for item in
                               category}
            for code in selected_options:
                selected_names.append(all_options_map.get(code, code))
            header += f"✅ Активные: {', '.join(selected_names[:3])}"
            if len(selected_names) > 3:
                header += f" и еще {len(selected_names) - 3}"
            header += f"\n"

        if limit_reached:
            header += f"⚠️ **ЛИМИТ ДОСТИГНУТ** - для большего выбора повысьте план\n"

        header += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        header += f"`ID: {state_hash}`\n"

        keyboard = []

        # Быстрые пакеты
        if QUICK_PACKS:
            keyboard.append([InlineKeyboardButton("⚡ БЫСТРЫЙ ВЫБОР", callback_data=f"IGNORE_{note_id}")])
            for code, pack in QUICK_PACKS.items():
                can_use = len(pack.get('options', [])) <= limit['checkboxes']
                btn_text = f"{'📦' if can_use else '🔒'} {pack['label']}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"PACK_{code}_{note_id}")])

            keyboard.append([InlineKeyboardButton("─" * 25, callback_data=f"IGNORE_{note_id}")])

        # Опции по категориям - БЕЗ checkbox стиля
        for category_idx, (category, options) in enumerate(CHECKBOX_CONFIG.items()):
            # Заголовок категории
            keyboard.append([InlineKeyboardButton(
                f"🔹 {category.upper()}",
                callback_data=f"IGNORE_{note_id}"
            )])

            for option in options:
                is_selected = option['code'] in selected_options
                is_locked = limit_reached and not is_selected

                # Простые кнопки без checkbox-символов
                if is_selected:
                    # Активная опция - яркий эмодзи
                    button_text = f"🟢 {option['label']}"
                elif is_locked:
                    # Заблокированная опция
                    button_text = f"🔒 {option['label']}"
                else:
                    # Неактивная опция - нейтральный эмодзи
                    button_text = f"⚪ {option['label']}"

                callback_data = f"TOGGLE_{option['code']}_{note_id}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        # Управляющие кнопки
        keyboard.append([InlineKeyboardButton("═" * 20, callback_data=f"IGNORE_{note_id}")])

        control_row = []
        control_row.append(InlineKeyboardButton("🗑 ОЧИСТИТЬ", callback_data=f"RESET_{note_id}"))

        if selected_count > 0:
            control_row.append(InlineKeyboardButton(
                f"🚀 ЗАПУСК ({selected_count})",
                callback_data=f"PROCESS_{note_id}"
            ))

        keyboard.append(control_row)

        return header, InlineKeyboardMarkup(keyboard)

    def get_status_message(self, user: Dict[str, Any]) -> str:
        lang_code = user.get('language_code', 'en')
        plan_key = user.get('plan', 'free')
        plan_info = TARIFF_LIMITS.get(plan_key, TARIFF_LIMITS['free'])
        plan_name = plan_info['name']
        limit = plan_info['checkboxes']

        header = self.localizer.get_string(lang_code, 'status_header', default="📊 Ваш статус")
        plan_str = self.localizer.get_string(lang_code, 'status_plan', default=f"Тарифный план: *{plan_name}*")
        limit_str = self.localizer.get_string(lang_code, 'status_limit', default=f"Лимит опций обработки: *{limit}*")

        return f"{header}\n\n{plan_str}\n{limit_str}"

    def get_help_message(self, lang_code: str, add_to_group_url: str) -> str:
        return self.localizer.get_string(lang_code, 'help_body',
                                         default="Отправьте аудио/видео файл или ссылку, чтобы начать. После этого вы сможете выбрать нужные форматы обработки.")