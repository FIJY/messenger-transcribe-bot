# services/media_handler.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import os
import logging
from typing import Optional, Tuple, Dict, Any
from .audio_processor import AudioProcessor
from .language_detector import LanguageDetector
from .transcription_service import TranscriptionService
from .translation_service import TranslationService
from .native_script_service import NativeScriptService

logger = logging.getLogger(__name__)


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: TranslationService):
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()
        self.transcription_service = transcription_service
        self.translation_service = translation_service
        self.native_script_service = NativeScriptService()  # Добавляем новый сервис

    # Замените ваш метод process_media на этот (строки 21-100):

    def process_media(self, file_path: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Обрабатывает медиа файл (аудио/видео) и возвращает результат

        Args:
            file_path: путь к файлу
            user_preferences: предпочтения пользователя

        Returns:
            dict с результатами обработки
        """
        audio_path = None
        try:
            logger.info(f"Начинаем обработку файла: {file_path}")

            # Получаем предпочтения пользователя
            expected_language = user_preferences.get('language') if user_preferences else None
            target_language = user_preferences.get('target_language', 'en') if user_preferences else 'en'

            # 1. Конвертируем в аудио если нужно
            audio_path = self.audio_processor.process_file(file_path)
            if not audio_path:
                return {
                    'success': False,
                    'error': 'Не удалось обработать медиа файл',
                    'transcription': '',
                    'detected_language': 'unknown',
                    'translation': None
                }

            # 2. Транскрибируем аудио с умным определением языка
            text, detected_language = self.transcription_service.transcribe_with_fallback(
                audio_path,
                expected_language
            )

            if text.startswith("Ошибка"):
                return {
                    'success': False,
                    'error': text,
                    'transcription': '',
                    'detected_language': 'unknown',
                    'translation': None
                }

            # 3. Дополнительный анализ языка
            language_analysis = self.language_detector.analyze_language(text)
            final_language = self._choose_best_language(
                detected_language,
                language_analysis.get('language'),
                expected_language,
                language_analysis.get('confidence', 0)
            )

            # 3.5. 🔧 УЛУЧШЕННОЕ определение кхмерского языка
            final_language = self._improve_khmer_detection(text, final_language)

            # 4. Анализ качества для нативных языков
            quality_analysis = self._analyze_transcription_quality(text, final_language)

            # 5. Создаем результат
            result = {
                'success': True,
                'transcription': text,
                'original_text': text,  # Для совместимости
                'detected_language': final_language,
                'quality_analysis': quality_analysis,
                'language_info': self._get_language_info_safe(final_language)
            }

            # 6. Переводим если запрошено
            if target_language and target_language != final_language:
                translation_result = self.translation_service.translate_text(
                    text, target_language, final_language
                )
                if translation_result.get('success'):
                    result['translation'] = translation_result.get('translated_text')
                    result['translated_text'] = translation_result.get('translated_text')  # Для совместимости
                    result['translation_target'] = target_language

            # 7. Очищаем временные файлы
            self._cleanup_temp_files(file_path, audio_path)

            logger.info(f"Обработка завершена успешно. Язык: {final_language}")
            return result

        except Exception as e:
            logger.error(f"Ошибка при обработке медиа: {e}")
            import traceback
            traceback.print_exc()

            # Очищаем файлы в случае ошибки
            if audio_path:
                self._cleanup_temp_files(file_path, audio_path)

            return {
                'success': False,
                'error': f'Произошла ошибка: {str(e)}',
                'transcription': '',
                'detected_language': 'unknown',
                'translation': None
            }

    def _choose_best_language(self, whisper_lang: str, detector_lang: str, expected_lang: Optional[str],
                              confidence: float) -> str:
        """Выбирает наиболее вероятный язык из разных источников"""

        # Если пользователь явно указал язык и confidence высокий
        if expected_lang and confidence > 0.6:
            if expected_lang == detector_lang:
                return expected_lang

        # Если Whisper и детектор согласны
        if whisper_lang == detector_lang:
            return whisper_lang

        # Если confidence детектора высокий
        if confidence > 0.7:
            return detector_lang

        # Иначе доверяем Whisper
        return whisper_lang

    # Добавьте эти методы в ваш services/media_handler.py после метода _choose_best_language

    def _improve_khmer_detection(self, text: str, detected_language: str) -> str:
        """
        Улучшенное определение кхмерского языка
        """
        if not text:
            return detected_language

        text_lower = text.lower()

        # 1. Проверяем наличие кхмерских Unicode символов
        khmer_chars = sum(1 for char in text if '\u1780' <= char <= '\u17FF')
        total_chars = len([char for char in text if char.isalpha()])

        if total_chars > 0 and khmer_chars / total_chars > 0.1:
            logger.info(f"Detected Khmer by Unicode characters: {khmer_chars}/{total_chars}")
            return 'km'

        # 2. Расширенный список кхмерских слов в латинской транслитерации
        khmer_keywords = [
            # Основные слова
            'bong', 'avan', 'kue', 'vie', 'mien', 'dak', 'chun', 'neng',
            'phnom penh', 'kath', 'chui', 'tae', 'doi', 'knea', 'tam',
            'thap', 'reang', 'sva', 'kam', 'krong', 'tlai', 'vreak',

            # Дополнительные кхмерские слова
            'thangay', 'penjad', 'kamong', 'tarak', 'titang', 'jom',
            'yung', 'knong', 'pya', 'okh', 'kaleng', 'cheung',
            'semeb', 'bannei', 'leak', 'piseh', 'temuy', 'peny', 'thol',
            'rohot', 'tadol', 'pahang', 'ngay', 'kalori', 'kaba', 'teet',
            'sosay', 'masin', 'rodh', 'pran', 'mak', 'jikan', 'phra',
            'trai', 'promoson', 'hoi', 'nesol', 'pophet',
            'thangon', 'ban', 'monitor', 'wilea', 'avey', 'kaha', 'tham',
            'bol', 'ksar', 'tieng', 'maku', 'deng', 'hit',

            # Географические названия
            'cambodia', 'cambodian', 'kampong', 'siem reap', 'battambang',
            'angkor', 'mekong', 'tonle sap', 'phnom', 'penh',

            # Частые фразы в транслитерации
            'chum reap suor', 'arkun', 'som tos', 'ot te', 'mean',
            'min mean', 'chea', 'rous', 'laor', 'ning', 'haiy',

            # Специфические кхмерские звуки в латинице
            'susuday', 'ksabay', 'preab', 'srey', 'pros', 'kmean',
            'preah', 'vihear', 'wat', 'pagoda'
        ]

        # 3. Подсчитываем совпадения кхмерских слов
        khmer_word_count = 0
        found_words = []

        for keyword in khmer_keywords:
            if keyword in text_lower:
                khmer_word_count += 1
                found_words.append(keyword)

        total_words = len(text_lower.split())

        logger.info(f"Khmer keyword analysis:")
        logger.info(f"  Found keywords: {found_words}")
        logger.info(f"  Khmer keywords: {khmer_word_count}/{total_words}")
        logger.info(f"  Original detection: {detected_language}")

        # 4. Если найдено достаточно кхмерских слов, считаем кхмерским
        if total_words > 0:
            khmer_ratio = khmer_word_count / total_words

            # Даже одно кхмерское слово из 3+ может указывать на кхмерский
            if khmer_word_count >= 1 and total_words <= 5:
                logger.info(f"Short text with Khmer keywords detected as Khmer")
                return 'km'

            # Для длинных текстов нужно больше совпадений
            if khmer_ratio > 0.15:  # 15% кхмерских слов
                logger.info(f"High Khmer keyword ratio: {khmer_ratio:.2f} - detected as Khmer")
                return 'km'

        # 5. Проверяем специфические кхмерские паттерны
        khmer_patterns = [
            'susuday mo sa ksabay',  # из вашего примера
            'bong chui',
            'vie mien',
            'kue bong',
            'phnom penh',
            'arkun chea'
        ]

        for pattern in khmer_patterns:
            if pattern in text_lower:
                logger.info(f"Khmer pattern '{pattern}' found - detected as Khmer")
                return 'km'

        # 6. Исключаем тагальский если есть кхмерские признаки
        if detected_language == 'tl' and khmer_word_count > 0:
            logger.info(f"Changing from Tagalog to Khmer due to keywords")
            return 'km'

        return detected_language

    def _analyze_transcription_quality(self, text: str, language: str) -> Dict[str, Any]:
        """Анализирует качество транскрипции для нативных языков"""
        try:
            # Проверяем, является ли язык азиатским/нативным
            native_languages = ['km', 'th', 'zh', 'ja', 'ko', 'vi']

            if language in native_languages:
                # Используем специализированный сервис
                analysis = self.native_script_service.analyze_script_quality(text, language)

                # Добавляем форматированное сообщение
                if 'message' not in analysis:
                    analysis['formatted_message'] = self.native_script_service.format_quality_message(
                        analysis, language
                    )

                return analysis
            else:
                # Базовый анализ для других языков
                return {
                    'quality': 'good',
                    'native_ratio': 1.0,
                    'message': '✅ Транскрипция выполнена успешно',
                    'has_transliteration': False
                }

        except Exception as e:
            logger.error(f"Ошибка при анализе качества: {e}")
            return {
                'quality': 'unknown',
                'native_ratio': 0.0,
                'message': '⚠️ Не удалось проанализировать качество',
                'error': str(e)
            }

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        """Безопасно получает информацию о языке"""
        language_names = {
            'km': {'name': 'Khmer', 'native': 'ខ្មែរ'},
            'en': {'name': 'English', 'native': 'English'},
            'ru': {'name': 'Russian', 'native': 'Русский'},
            'th': {'name': 'Thai', 'native': 'ไทย'},
            'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt'},
            'zh': {'name': 'Chinese', 'native': '中文'},
            'ja': {'name': 'Japanese', 'native': '日本語'},
            'ko': {'name': 'Korean', 'native': '한국어'},
            'ar': {'name': 'Arabic', 'native': 'العربية'},
            'hi': {'name': 'Hindi', 'native': 'हिन्दी'},
            'fr': {'name': 'French', 'native': 'Français'},
            'es': {'name': 'Spanish', 'native': 'Español'},
            'de': {'name': 'German', 'native': 'Deutsch'},
            'it': {'name': 'Italian', 'native': 'Italiano'},
            'pt': {'name': 'Portuguese', 'native': 'Português'},
            'tl': {'name': 'Tagalog', 'native': 'Tagalog'}
        }
        return language_names.get(detected_language, {'name': detected_language.upper(), 'native': ''})

    @staticmethod
    def _cleanup_temp_files(original_path: str, processed_path: Optional[str]):
        """Очищает временные файлы"""
        try:
            # Удаляем обработанный аудио файл если он отличается от оригинала
            if processed_path and processed_path != original_path and os.path.exists(processed_path):
                os.remove(processed_path)
                logger.debug(f"Удален временный файл: {processed_path}")

            # Удаляем оригинальный файл
            if original_path and os.path.exists(original_path):
                os.remove(original_path)
                logger.debug(f"Удален оригинальный файл: {original_path}")

        except Exception as e:
            logger.warning(f"Не удалось очистить временные файлы: {e}")

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        """Проверяет файл на соответствие ограничениям"""
        return self.audio_processor.validate_audio_file(file_path)

    @staticmethod
    def get_supported_formats() -> Dict[str, Any]:
        """Возвращает поддерживаемые форматы файлов"""
        return {
            'audio': ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'],
            'video': ['mp4', 'avi', 'mov', 'mkv', 'webm'],
            'max_duration_free': 300,  # 5 минут для бесплатных пользователей
            'max_duration_premium': 3600,  # 60 минут для премиум
            'max_file_size': 50 * 1024 * 1024  # 50MB
        }