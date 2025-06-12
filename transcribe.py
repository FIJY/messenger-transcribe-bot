import os
import tempfile
import logging
import whisper
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import io

class TranscribeService:
    def __init__(self):
        # Загружаем модель Whisper
        # Для продакшена рекомендую 'small' или 'medium' для баланса скорости и качества
        model_size = os.getenv('WHISPER_MODEL', 'base')
        logging.info(f"Loading Whisper model: {model_size}")
        self.model = whisper.load_model(model_size)
        
        # Поддерживаемые языки (можно расширить)
        self.supported_languages = {
            'km': 'ខ្មែរ (Khmer)',
            'en': 'English',
            'ru': 'Русский',
            'zh': '中文',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
            'fr': 'Français',
            'es': 'Español',
            'ja': '日本語',
            'ko': '한국어'
        }
        
    def transcribe(self, audio_data):
        """Транскрибировать аудио данные"""
        try:
            # Сохраняем аудио во временный файл
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_file_path = tmp_file.name
            
            # Конвертируем в формат, который понимает Whisper
            audio_path = self._convert_audio(tmp_file_path)
            
            # Проверяем длительность
            duration = self._get_audio_duration(audio_path)
            if duration > 300:  # 5 минут
                os.unlink(tmp_file_path)
                os.unlink(audio_path)
                return {
                    'success': False,
                    'error': 'Audio too long. Maximum 5 minutes allowed.'
                }
            
            # Транскрибируем с автоопределением языка
            logging.info(f"Transcribing audio, duration: {duration}s")
            result = self.model.transcribe(
                audio_path,
                task='transcribe',  # 'transcribe' или 'translate' (в английский)
                verbose=False
            )
            
            # Удаляем временные файлы
            os.unlink(tmp_file_path)
            if audio_path != tmp_file_path:
                os.unlink(audio_path)
            
            # Определяем язык
            detected_language = result['language']
            language_name = self.supported_languages.get(
                detected_language, 
                f"Language: {detected_language}"
            )
            
            return {
                'success': True,
                'text': result['text'].strip(),
                'language': language_name,
                'language_code': detected_language,
                'duration': duration
            }
            
        except CouldntDecodeError:
            logging.error("Could not decode audio file")
            return {
                'success': False,
                'error': 'Invalid audio format. Please send a valid audio message.'
            }
        except Exception as e:
            logging.error(f"Transcription error: {str(e)}")
            return {
                'success': False,
                'error': 'Transcription failed. Please try again.'
            }
    
    def _convert_audio(self, input_path):
        """Конвертировать аудио в WAV формат для Whisper"""
        try:
            # Пробуем загрузить как есть
            audio = AudioSegment.from_file(input_path)
            
            # Конвертируем в WAV
            output_path = input_path.replace('.mp3', '.wav')
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(output_path, format='wav')
            
            return output_path
        except Exception as e:
            logging.error(f"Audio conversion error: {e}")
            # Возвращаем оригинальный путь и надеемся что Whisper справится
            return input_path
    
    def _get_audio_duration(self, audio_path):
        """Получить длительность аудио в секундах"""
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0  # Конвертируем миллисекунды в секунды
        except:
            # Если не можем определить, возвращаем 0 (без ограничений)
            return 0
    
    def translate_to_english(self, audio_data):
        """Транскрибировать и перевести в английский"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_file_path = tmp_file.name
            
            audio_path = self._convert_audio(tmp_file_path)
            
            # Используем task='translate' для перевода в английский
            result = self.model.transcribe(
                audio_path,
                task='translate',
                verbose=False
            )
            
            os.unlink(tmp_file_path)
            if audio_path != tmp_file_path:
                os.unlink(audio_path)
            
            return {
                'success': True,
                'text': result['text'].strip(),
                'original_language': result['language']
            }
            
        except Exception as e:
            logging.error(f"Translation error: {str(e)}")
            return {
                'success': False,
                'error': 'Translation failed'
            }
    
    def get_supported_languages(self):
        """Получить список поддерживаемых языков"""
        return self.supported_languages
    
    def is_language_supported(self, language_code):
        """Проверить поддерживается ли язык"""
        return language_code in self.supported_languages