import os
import logging
from typing import Optional, Tuple, Dict, Any
from .audio_processor import AudioProcessor
from .language_detector import LanguageDetector
from .transcription_service import TranscriptionService
from .translation_service import TranslationService

logger = logging.getLogger(__name__)


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: TranslationService):
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()
        self.transcription_service = transcription_service
        self.translation_service = translation_service

    def process_media(self, file_path: str, target_language: Optional[str] = None) -> Dict[str, Any]:
        """
        Обрабатывает медиа файл (аудио/видео) и возвращает результат

        Args:
            file_path: путь к файлу
            target_language: целевой язык для перевода (опционально)

        Returns:
            dict с результатами обработки
        """
        audio_path = None
        try:
            logger.info(f"Начинаем обработку файла: {file_path}")

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

            # 2. Попытка определить язык из имени файла (если метод существует)
            filename_language = None
            try:
                if hasattr(self.language_detector, 'detect_language_from_filename'):
                    filename_language = self.language_detector.detect_language_from_filename(file_path)
                    logger.info(f"Язык из имени файла: {filename_language}")
                else:
                    logger.info("Метод detect_language_from_filename не найден, пропускаем")
            except Exception as e:
                logger.warning(f"Ошибка определения языка по имени файла: {e}")

            # 3. Транскрибируем аудио
            transcription = None
            detected_language = 'unknown'

            if filename_language in ['khmer', 'km']:
                # Для кхмерского используем специальную стратегию
                logger.info("Используем кхмерскую транскрипцию")
                result = self.transcription_service.transcribe_audio(audio_path, 'km')
            else:
                # Обычная транскрипция с автоопределением языка
                logger.info("Используем обычную транскрипцию с автоопределением")
                result = self.transcription_service.transcribe_with_language_detection(audio_path)

            if result['success']:
                transcription = result['text']
                detected_language = result.get('detected_language', 'unknown')
                logger.info(f"Транскрипция успешна: {len(transcription)} символов, язык: {detected_language}")
            else:
                logger.error(f"Ошибка транскрипции: {result.get('error')}")
                return {
                    'success': False,
                    'error': result.get('error', 'Ошибка транскрипции'),
                    'transcription': '',
                    'detected_language': 'unknown',
                    'translation': None
                }

            # 4. Улучшенное определение кхмерского языка
            detected_language = self._detect_khmer_language(transcription, detected_language)

            # 5. Дополнительное определение языка по тексту (если нужно)
            if detected_language == 'unknown' and transcription:
                try:
                    if hasattr(self.language_detector, 'analyze_language'):
                        text_language, confidence = self.language_detector.analyze_language(transcription)
                        if confidence > 0.3:
                            detected_language = text_language
                            logger.info(
                                f"Язык определен по тексту: {detected_language} (уверенность: {confidence:.2f})")
                    else:
                        logger.info("Метод analyze_language не найден, пропускаем анализ")
                except Exception as e:
                    logger.warning(f"Ошибка анализа языка по тексту: {e}")

            # 6. Проверяем качество транскрипции для кхмерского
            if detected_language in ['km', 'khmer']:
                transcription = self._improve_khmer_transcription(transcription)

            result = {
                'success': True,
                'transcription': transcription,
                'detected_language': detected_language,
                'translation': None,
                'language_info': self._get_language_info_safe(detected_language)
            }

            # 7. Переводим если запрошено
            if target_language and target_language != detected_language:
                try:
                    translation_result = self.translation_service.translate_text(
                        transcription, detected_language, target_language
                    )
                    if translation_result.get('success'):
                        result['translation'] = translation_result.get('translated_text')
                        logger.info(f"Выполнен перевод на {target_language}")
                    else:
                        logger.warning(f"Не удалось выполнить перевод: {translation_result.get('error')}")
                except Exception as e:
                    logger.error(f"Ошибка при переводе: {e}")

            # 8. Очищаем временные файлы
            self._cleanup_temp_files(file_path, audio_path)

            logger.info(f"Обработка завершена успешно. Язык: {detected_language}")
            return result

        except Exception as e:
            logger.error(f"Ошибка при обработке медиа: {e}")
            import traceback
            traceback.print_exc()

            # Очищаем файлы в случае ошибки
            try:
                if audio_path:
                    self._cleanup_temp_files(file_path, audio_path)
            except Exception as cleanup_error:
                logger.warning(f"Ошибка при очистке файлов: {cleanup_error}")

            return {
                'success': False,
                'error': f'Произошла ошибка: {str(e)}',
                'transcription': '',
                'detected_language': 'unknown',
                'translation': None
            }

    def _detect_khmer_language(self, transcription: str, detected_language: str) -> str:
        """
        Улучшенное определение кхмерского языка по содержанию
        """
        if not transcription:
            return detected_language

        text_lower = transcription.lower()

        # Кхмерские слова в латинской транслитерации
        khmer_keywords = [
            'bong', 'avan', 'kue', 'vie', 'mien', 'dak', 'chun', 'neng',
            'phnom penh', 'kath', 'chui', 'tae', 'doi', 'knea', 'tam',
            'thap', 'reang', 'sva', 'kam', 'krong', 'tlai', 'vreak',
            'thangay', 'penjad', 'kamong', 'tarak', 'titang', 'jom',
            'yung', 'knong', 'free', 'pya', 'okh', 'kaleng', 'cheung',
            'semeb', 'bannei', 'leak', 'piseh', 'temuy', 'peny', 'thol',
            'rohot', 'tadol', 'pahang', 'ngay', 'kalori', 'kaba', 'teet',
            'sosay', 'masin', 'rodh', 'pran', 'mak', 'jikan', 'phra',
            'trai', 'promoson', 'hoi', 'nesol', 'pophet', 'full option',
            'thangon', 'ban', 'monitor', 'wilea', 'avey', 'like share',
            'kaha', 'tham', 'bol', 'reang mui', 'ksar', 'tieng', 'maku',
            'chum mui', 'deng', 'hit', 'cambodia', 'cambodian'
        ]

        # Подсчитываем кхмерские слова
        khmer_word_count = sum(1 for keyword in khmer_keywords if keyword in text_lower)
        total_words = len(text_lower.split())

        if total_words > 0:
            khmer_ratio = khmer_word_count / total_words
            logger.info(f"Khmer keywords found: {khmer_word_count}/{total_words} = {khmer_ratio:.2f}")

            # Если более 10% слов кхмерские, считаем это кхмерским языком
            if khmer_ratio > 0.10:
                logger.info(f"Detected as Khmer based on keyword analysis (ratio: {khmer_ratio:.2f})")
                return 'km'

            # Проверяем на упоминание Пномпеня и других географических названий
            cambodian_places = ['phnom penh', 'cambodia', 'kampong', 'siem reap', 'battambang', 'angkor']
            if any(place in text_lower for place in cambodian_places):
                logger.info("Detected as Khmer based on Cambodian place names")
                return 'km'

            # Проверяем специфические кхмерские фразы
            khmer_phrases = ['sosay bong', 'bong chui', 'vie mien', 'kue bong', 'no phnom penh']
            if any(phrase in text_lower for phrase in khmer_phrases):
                logger.info("Detected as Khmer based on specific phrases")
                return 'km'

        return detected_language

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        """
        Безопасно получает информацию о языке
        """
        try:
            if hasattr(self.language_detector, 'get_language_info'):
                return self.language_detector.get_language_info(detected_language)
            else:
                # Простая заглушка
                language_names = {
                    'km': {'name': 'Khmer', 'native': 'ខ្មែរ'},
                    'en': {'name': 'English', 'native': 'English'},
                    'ru': {'name': 'Russian', 'native': 'Русский'},
                    'th': {'name': 'Thai', 'native': 'ไทย'},
                    'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt'},
                    'zh': {'name': 'Chinese', 'native': '中文'},
                    'ja': {'name': 'Japanese', 'native': '日本語'},
                    'ko': {'name': 'Korean', 'native': '한국어'},
                    'tl': {'name': 'Tagalog', 'native': 'Tagalog'}
                }
                return language_names.get(detected_language, {'name': detected_language.upper(), 'native': ''})
        except Exception as e:
            logger.warning(f"Ошибка получения информации о языке: {e}")
            return {'name': detected_language.upper(), 'native': ''}

    @staticmethod
    def _improve_khmer_transcription(transcription: str) -> str:
        """
        Улучшает транскрипцию кхмерского языка
        """
        if not transcription:
            return transcription

        # Проверяем соотношение кхмерских символов
        khmer_chars = sum(1 for char in transcription if '\u1780' <= char <= '\u17FF')
        total_chars = len([char for char in transcription if char.isalpha()])

        if total_chars > 0:
            khmer_ratio = khmer_chars / total_chars

            if khmer_ratio < 0.1:  # Очень мало кхмерских символов
                # Добавляем предупреждение для транслитерированного текста
                warning = "ℹ️ Кхмерская речь распознана в латинской транслитерации.\n"
                warning += "📝 Для лучшего качества попробуйте:\n"
                warning += "• Говорить четче и медленнее\n"
                warning += "• Записывать в тихом месте\n"
                warning += "• Использовать качественный микрофон\n\n"
                transcription = warning + transcription
            elif khmer_ratio < 0.3:  # Мало кхмерских символов
                transcription = "⚠️ Частичное распознавание кхмерского языка:\n\n" + transcription

        return transcription

    @staticmethod
    def _cleanup_temp_files(original_path: str, processed_path: Optional[str]):
        """
        Очищает временные файлы
        """
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

    @staticmethod
    def get_supported_formats() -> Dict[str, Any]:
        """
        Возвращает поддерживаемые форматы файлов
        """
        return {
            'audio': ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'],
            'video': ['mp4', 'avi', 'mov', 'mkv', 'webm'],
            'max_duration_free': 300,  # 5 минут для бесплатных пользователей
            'max_duration_premium': 3600,  # 60 минут для премиум
            'max_file_size': 50 * 1024 * 1024  # 50MB
        }

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        """
        Проверяет файл на соответствие ограничениям

        Args:
            file_path: путь к файлу
            is_premium: является ли пользователь премиум

        Returns:
            Tuple[is_valid, error_message]
        """
        try:
            if not os.path.exists(file_path):
                return False, "Файл не найден"

            # Проверяем размер файла
            file_size = os.path.getsize(file_path)
            max_size = self.get_supported_formats()['max_file_size']

            if file_size > max_size:
                return False, f"Файл слишком большой. Максимальный размер: {max_size // (1024 * 1024)}MB"

            # ВАЖНО: Для временных файлов Facebook всегда возвращаем True
            if '/tmp/' in file_path and file_path.endswith('.tmp'):
                logger.info(f"Обнаружен временный Facebook файл: {file_path}, размер: {file_size} байт")
                return True, ""

            # Обычная проверка расширения для локальных файлов
            file_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
            supported = self.get_supported_formats()
            all_formats = supported['audio'] + supported['video']

            if file_ext not in all_formats:
                return False, f"Неподдерживаемый формат файла. Поддерживаются: {', '.join(all_formats)}"

            # Проверяем длительность (если метод существует)
            if hasattr(self.audio_processor, 'get_media_duration'):
                duration = self.audio_processor.get_media_duration(file_path)
                if duration:
                    max_duration = supported['max_duration_premium'] if is_premium else supported['max_duration_free']
                    if duration > max_duration:
                        max_minutes = max_duration // 60
                        return False, f"Файл слишком длинный. Максимальная длительность: {max_minutes} минут"

            return True, ""

        except Exception as e:
            logger.error(f"Ошибка при проверке файла: {e}")
            return False, f"Ошибка при проверке файла: {str(e)}"

    def create_smart_response(self, result: Dict[str, Any], user_language: str = 'en') -> str:
        """
        Создает умный ответ пользователю с учетом результатов обработки

        Args:
            result: результат обработки медиа
            user_language: предпочитаемый язык пользователя

        Returns:
            Отформатированный ответ
        """
        if not result['success']:
            return f"❌ {result['error']}"

        detected_lang = result['detected_language']
        transcription = result['transcription']
        translation = result.get('translation')
        language_info = result.get('language_info', {})

        # Определяем иконку для языка
        language_icons = {
            'km': '🇰🇭',  # Камбоджа
            'th': '🇹🇭',  # Таиланд
            'vi': '🇻🇳',  # Вьетнам
            'zh': '🇨🇳',  # Китай
            'ja': '🇯🇵',  # Япония
            'ko': '🇰🇷',  # Корея
            'en': '🇺🇸',  # США
            'ru': '🇷🇺',  # Россия
            'fr': '🇫🇷',  # Франция
            'es': '🇪🇸',  # Испания
            'de': '🇩🇪',  # Германия
            'ar': '🇸🇦',  # Саудовская Аравия
            'tl': '🇵🇭',  # Филиппины
        }

        icon = language_icons.get(detected_lang, '🌐')
        lang_name = language_info.get('name', detected_lang.upper())
        native_name = language_info.get('native', '')

        # Формируем ответ
        response = f"🎯 **Распознанный язык:** {icon} {lang_name}"
        if native_name and native_name != lang_name:
            response += f" ({native_name})"
        response += "\n\n"

        # Добавляем транскрипцию
        response += f"📝 **Транскрипция:**\n{transcription}"

        # Добавляем перевод если есть
        if translation:
            response += f"\n\n🔄 **Перевод:**\n{translation}"

        # Добавляем предложение перевода для определенных случаев
        if not translation and self._should_offer_translation(detected_lang, user_language):
            response += self._get_translation_offer(detected_lang, user_language)

        return response

    @staticmethod
    def _should_offer_translation(detected_lang: str, user_lang: str) -> bool:
        """
        Определяет, стоит ли предложить перевод
        """
        if detected_lang == user_lang:
            return False

        # Предлагаем перевод для азиатских языков на английский/русский
        asian_languages = ['km', 'th', 'vi', 'zh', 'ja', 'ko', 'tl']
        western_languages = ['en', 'ru', 'fr', 'es', 'de']

        return (detected_lang in asian_languages and user_lang in western_languages) or \
            (detected_lang in western_languages and user_lang in asian_languages)

    @staticmethod
    def _get_translation_offer(detected_lang: str, user_lang: str) -> str:
        """
        Возвращает предложение перевода
        """
        suggestions = {
            'en': "\n\n💡 Want a translation? Reply with 'translate to [language]'",
            'ru': "\n\n💡 Нужен перевод? Ответьте 'перевести на [язык]'",
            'km': "\n\n💡 ត្រូវការការបកប្រែទេ? ឆ្លើយតប 'បកប្រែទៅ [ភាសា]'",
            'th': "\n\n💡 ต้องการแปลไหม? ตอบกলับด้วย 'แปลเป็น [ภาษา]'",
            'vi': "\n\n💡 Cần dịch không? Trả lời 'dịch sang [ngôn ngữ]'",
            'tl': "\n\n💡 Gusto mo bang isalin? Sumagot ng 'translate to [language]'"
        }

        return suggestions.get(user_lang, suggestions['en'])