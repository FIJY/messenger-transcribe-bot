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
        return self.localizer.get_string(lang_code, 'welcome_message')

    def get_checkbox_selection_menu(self, lang_code: str, note_id: ObjectId, user_plan: str,
                                    selected_options: List[str]) -> Tuple[str, InlineKeyboardMarkup]:
        """
        Generates the main checkbox selection interface based on the user's plan and current selections.
        """
        limit = TARIFF_LIMITS.get(user_plan, TARIFF_LIMITS['free'])
        selected_count = len(selected_options)
        limit_reached = selected_count >= limit['checkboxes']

        # --- Build Header Text ---
        header = f"✅ *Выберите форматы обработки*\n\n"
        header += f"Тариф: *{limit['name']}*\n"
        header += f"Выбрано: *{selected_count} из {limit['checkboxes']}*\n"
        if limit_reached:
            header += "Лимит достигнут. Чтобы выбрать больше, повысьте тариф.\n"

        keyboard = []

        # --- Quick Packs Buttons ---
        pack_row = []
        for code, pack in QUICK_PACKS.items():
            pack_row.append(InlineKeyboardButton(pack['label'], callback_data=f"PACK_{code}_{note_id}"))
        keyboard.append(pack_row)

        # --- Checkbox Option Buttons ---
        for category, options in CHECKBOX_CONFIG.items():
            keyboard.append([InlineKeyboardButton(f"--- {category} ---", callback_data="IGNORE")])
            row = []
            for option in options:
                is_selected = option['code'] in selected_options
                is_locked = limit_reached and not is_selected

                if is_selected:
                    button_text = f"✅ {option['label']}"
                elif is_locked:
                    button_text = f"🔒 {option['label']}"
                else:
                    button_text = f"☐ {option['label']}"

                callback_data = f"CHECKBOX_{option['code']}_{note_id}"
                row.append(InlineKeyboardButton(button_text, callback_data=callback_data))

                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

        # --- Action Buttons ---
        keyboard.append([InlineKeyboardButton("🔄 Сбросить выбор", callback_data=f"RESET_ALL_{note_id}")])
        if selected_count > 0:
            keyboard.append([InlineKeyboardButton(f"🚀 Начать обработку ({selected_count} опций)",
                                                  callback_data=f"PROCESS_{note_id}")])

        return header, InlineKeyboardMarkup(keyboard)

    # --- Other UI methods remain for other parts of the bot ---
    def get_main_actions_menu(self, lang_code: str, note_id: ObjectId) -> Tuple[str, InlineKeyboardMarkup]:
        # This menu is now for post-processing actions.
        text = "✅ Обработка завершена! Что еще сделать с результатами?"
        keyboard = [
            [
                InlineKeyboardButton("🌐 Перевести", callback_data=f"SHOW_LANG_MENU_TRANSLATE_1_{note_id}"),
                InlineKeyboardButton("📄 Экспорт в файл", callback_data=f"ACTION_EXPORT_{note_id}")
            ],
            [
                InlineKeyboardButton("🗑️ Удалить", callback_data=f"ACTION_DELETE_{note_id}")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)
