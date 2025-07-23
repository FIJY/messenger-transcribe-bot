# services/localization_service.py
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LocalizationService:
    def __init__(self, locales_dir: str = "locales", fallback_lang: str = "en"):
        self.locales_dir = locales_dir
        self.fallback_lang = fallback_lang
        self.translations = self._load_translations()

    def _load_translations(self) -> Dict[str, Dict[str, str]]:
        translations = {}
        try:
            for filename in os.listdir(self.locales_dir):
                if filename.endswith(".json"):
                    lang_code = filename.split(".")[0]
                    filepath = os.path.join(self.locales_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        translations[lang_code] = json.load(f)
            logger.info(f"Loaded {len(translations)} languages: {list(translations.keys())}")
        except FileNotFoundError:
            logger.error(f"Locales directory not found at '{self.locales_dir}'")
        except Exception as e:
            logger.error(f"Error loading translation files: {e}", exc_info=True)
        return translations

    def get_string(self, lang_code: str, key: str, **kwargs: Any) -> str:
        """
        Получает переведенную строку по ключу для указанного языка.
        """
        # Используем основной язык или запасной, если основного нет
        lang_dict = self.translations.get(lang_code, self.translations.get(self.fallback_lang, {}))

        # Получаем строку, или ключ, если строка не найдена
        string_template = lang_dict.get(key, key)

        try:
            return string_template.format(**kwargs)
        except (KeyError, TypeError) as e:
            logger.warning(f"Error formatting string for key '{key}' with args {kwargs}: {e}")
            return string_template  # Возвращаем шаблон без форматирования в случае ошибки
