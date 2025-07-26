# services/telegram_ui.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any, Tuple
from bson import ObjectId

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

        header = f"✅ *Выберите форматы обработки*\n\n"
        header += f"Тариф: *{limit['name']}*\n"
        header += f"Выбрано: *{selected_count} из {limit['checkboxes']}*\n"
        if limit_reached:
            header += "Лимит достигнут. Чтобы выбрать больше, повысьте тариф.\n"

        keyboard = []

        pack_row = []
        for code, pack in QUICK_PACKS.items():
            pack_row.append(InlineKeyboardButton(pack['label'], callback_data=f"PACK_{code}_{note_id}"))
        keyboard.append(pack_row)

        for category, options in CHECKBOX_CONFIG.items():
            keyboard.append([InlineKeyboardButton(f"--- {category} ---", callback_data=f"IGNORE_{note_id}")])
            row = []
            for option in options:
                is_selected = option['code'] in selected_options
                is_locked = limit_reached and not is_selected
                button_text = f"✅ {option['label']}" if is_selected else f"🔒 {option['label']}" if is_locked else f"☐ {option['label']}"
                callback_data = f"CHECKBOX_{option['code']}_{note_id}"
                row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

        keyboard.append([InlineKeyboardButton("🔄 Сбросить выбор", callback_data=f"RESET_{note_id}")])
        if selected_count > 0:
            keyboard.append([InlineKeyboardButton(f"🚀 Начать обработку ({selected_count} опций)",
                                                  callback_data=f"PROCESS_{note_id}")])

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
