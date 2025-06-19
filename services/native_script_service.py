# services/native_script_service.py
import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class NativeScriptService:
    """
    Сервис для обработки и улучшения текста на нативных письменностях
    Поддерживает азиатские языки: кхмерский, тайский, китайский, японский, корейский, вьетнамский
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Определение Unicode диапазонов для разных письменностей
        self.script_ranges = {
            'khmer': (0x1780, 0x17FF),  # Кхмерский
            'thai': (0x0E00, 0x0E7F),  # Тайский
            'chinese': (0x4E00, 0x9FFF),  # CJK Unified Ideographs
            'hiragana': (0x3040, 0x309F),  # Японская хирагана
            'katakana': (0x30A0, 0x30FF),  # Японская катакана
            'hangul': (0xAC00, 0xD7AF),  # Корейский хангыль
            'hangul_jamo': (0x1100, 0x11FF),  # Корейские jamo
            'vietnamese': (0x1EA0, 0x1EF9),  # Вьетнамские диакритики
        }

        # Ключевые слова для определения языков в латинице
        self.transliteration_keywords = {
            'km': [
                'bong', 'avan', 'kue', 'vie', 'mien', 'dak', 'chun', 'neng',
                'phnom penh', 'kath', 'chui', 'tae', 'doi', 'knea', 'tam',
                'thap', 'reang', 'sva', 'kam', 'krong', 'tlai', 'vreak',
                'sosay', 'masin', 'rodh', 'pran', 'mak', 'nesol', 'cambodia'
            ],
            'th': [
                'thai', 'thailand', 'bangkok', 'krung', 'thep', 'mai', 'chai',
                'sabai', 'aroi', 'khrap', 'kha', 'sanuk', 'nam', 'khao'
            ],
            'vi': [
                'vietnam', 'viet', 'saigon', 'hanoi', 'pho', 'banh', 'com',
                'nuoc', 'chao', 'xin', 'cam', 'gia', 'nha', 'toi'
            ],
            'zh': [
                'china', 'chinese', 'beijing', 'shanghai', 'ni hao', 'xie xie',
                'zai jian', 'wo shi', 'zhong guo', 'hen hao'
            ],
            'ja': [
                'japan', 'japanese', 'tokyo', 'osaka', 'arigatou', 'konnichiwa',
                'sayonara', 'watashi', 'anata', 'desu', 'masu'
            ],
            'ko': [
                'korea', 'korean', 'seoul', 'annyeong', 'saranghae', 'gamsahamnida',
                'yeoboseyo', 'naneun', 'dangsin', 'hankook'
            ]
        }

    def analyze_script_quality(self, text: str, expected_language: str) -> Dict[str, any]:
        """
        Анализирует качество нативной письменности в тексте

        Args:
            text: Анализируемый текст
            expected_language: Ожидаемый язык (km, th, zh, ja, ko, vi)

        Returns:
            dict с результатами анализа
        """
        if not text:
            return {'native_ratio': 0, 'quality': 'empty', 'has_transliteration': False}

        analysis = {
            'native_ratio': 0,
            'quality': 'poor',
            'has_transliteration': False,
            'script_counts': {},
            'total_chars': 0,
            'recommendations': []
        }

        # Подсчитываем символы разных письменностей
        analysis['script_counts'] = self._count_script_characters(text)
        analysis['total_chars'] = sum(analysis['script_counts'].values())

        # Определяем качество для конкретного языка
        if expected_language == 'km':
            analysis.update(self._analyze_khmer_quality(text, analysis['script_counts']))
        elif expected_language == 'th':
            analysis.update(self._analyze_thai_quality(text, analysis['script_counts']))
        elif expected_language == 'zh':
            analysis.update(self._analyze_chinese_quality(text, analysis['script_counts']))
        elif expected_language == 'ja':
            analysis.update(self._analyze_japanese_quality(text, analysis['script_counts']))
        elif expected_language == 'ko':
            analysis.update(self._analyze_korean_quality(text, analysis['script_counts']))
        elif expected_language == 'vi':
            analysis.update(self._analyze_vietnamese_quality(text, analysis['script_counts']))

        # Проверяем наличие транслитерации
        analysis['has_transliteration'] = self._has_transliteration(text, expected_language)

        return analysis

    def _count_script_characters(self, text: str) -> Dict[str, int]:
        """Подсчитывает символы разных письменностей"""
        counts = {script: 0 for script in self.script_ranges.keys()}
        counts['latin'] = 0
        counts['other'] = 0

        for char in text:
            if char.isalpha():
                categorized = False
                for script, (start, end) in self.script_ranges.items():
                    if start <= ord(char) <= end:
                        counts[script] += 1
                        categorized = True
                        break

                if not categorized:
                    if 'a' <= char.lower() <= 'z':
                        counts['latin'] += 1
                    else:
                        counts['other'] += 1

        return counts

    def _analyze_khmer_quality(self, text: str, script_counts: Dict) -> Dict:
        """Анализ качества кхмерского текста"""
        total_alpha = sum(script_counts.values())
        khmer_count = script_counts.get('khmer', 0)

        if total_alpha == 0:
            return {'native_ratio': 0, 'quality': 'empty'}

        khmer_ratio = khmer_count / total_alpha

        quality_info = {
            'native_ratio': khmer_ratio,
            'khmer_chars': khmer_count,
            'latin_chars': script_counts.get('latin', 0),
        }

        if khmer_ratio >= 0.8:
            quality_info.update({
                'quality': 'excellent',
                'message': "✅ កម្មវិធីបានដកស្រង់អក្សរខ្មែរដោយជោគជ័យ"
            })
        elif khmer_ratio >= 0.5:
            quality_info.update({
                'quality': 'good',
                'message': "✓ ការដកស្រង់អក្សរខ្មែរល្អ"
            })
        elif khmer_ratio >= 0.2:
            quality_info.update({
                'quality': 'mixed',
                'message': "⚠️ ការដកស្រង់ចម្រុះ (មានអក្សរខ្មែរខ្លះ)",
                'recommendations': [
                    "និយាយយឺតៗ និងច្បាស់",
                    "កុំលាយភាសាអង់គ្លេស",
                    "ថតក្នុងកន្លែងស្ងាត់"
                ]
            })
        else:
            quality_info.update({
                'quality': 'poor',
                'message': "❌ ការដកស្រង់មិនបានគុណភាពល្អ",
                'recommendations': [
                    "និយាយខ្មែរសុទ្ធ",
                    "និយាយយឺតៗ និងច្បាស់",
                    "ថតក្នុងកន្លែងស្ងាត់",
                    "ប្រើម៉ាយក្រូហ្វូនល្អ"
                ]
            })

        return quality_info

    def _analyze_thai_quality(self, text: str, script_counts: Dict) -> Dict:
        """Анализ качества тайского текста"""
        total_alpha = sum(script_counts.values())
        thai_count = script_counts.get('thai', 0)

        if total_alpha == 0:
            return {'native_ratio': 0, 'quality': 'empty'}

        thai_ratio = thai_count / total_alpha

        quality_info = {'native_ratio': thai_ratio}

        if thai_ratio >= 0.8:
            quality_info.update({
                'quality': 'excellent',
                'message': "✅ การแปลงเสียงเป็นข้อความภาษาไทยสำเร็จ"
            })
        elif thai_ratio >= 0.5:
            quality_info.update({
                'quality': 'good',
                'message': "✓ การแปลงภาษาไทยได้ดี"
            })
        elif thai_ratio >= 0.2:
            quality_info.update({
                'quality': 'mixed',
                'message': "⚠️ การแปลงแบบผสม (มีอักษรไทยบางส่วน)",
                'recommendations': [
                    "พูดช้าและชัดเจน",
                    "อย่าผสมภาษาอังกฤษ",
                    "บันทึกในที่เงียบ"
                ]
            })
        else:
            quality_info.update({
                'quality': 'poor',
                'message': "❌ คุณภาพการแปลงไม่ดี",
                'recommendations': [
                    "พูดภาษาไทยล้วนๆ",
                    "พูดช้าและชัดเจน",
                    "บันทึกในที่เงียบ",
                    "ใช้ไมค์คุณภาพดี"
                ]
            })

        return quality_info

    def _analyze_chinese_quality(self, text: str, script_counts: Dict) -> Dict:
        """Анализ качества китайского текста"""
        total_alpha = sum(script_counts.values())
        chinese_count = script_counts.get('chinese', 0)

        if total_alpha == 0:
            return {'native_ratio': 0, 'quality': 'empty'}

        chinese_ratio = chinese_count / total_alpha

        quality_info = {'native_ratio': chinese_ratio}

        if chinese_ratio >= 0.8:
            quality_info.update({
                'quality': 'excellent',
                'message': "✅ 中文语音转文字成功"
            })
        elif chinese_ratio >= 0.5:
            quality_info.update({
                'quality': 'good',
                'message': "✓ 中文转换效果良好"
            })
        elif chinese_ratio >= 0.2:
            quality_info.update({
                'quality': 'mixed',
                'message': "⚠️ 混合语言转录 (部分中文)",
                'recommendations': [
                    "说话慢一些，清楚一些",
                    "不要混合英语",
                    "在安静的地方录音"
                ]
            })
        else:
            quality_info.update({
                'quality': 'poor',
                'message': "❌ 转录质量不佳",
                'recommendations': [
                    "说纯中文",
                    "说话慢一些，清楚一些",
                    "在安静的地方录音",
                    "使用好的麦克风"
                ]
            })

        return quality_info

    def _analyze_japanese_quality(self, text: str, script_counts: Dict) -> Dict:
        """Анализ качества японского текста"""
        total_alpha = sum(script_counts.values())
        hiragana = script_counts.get('hiragana', 0)
        katakana = script_counts.get('katakana', 0)
        kanji = script_counts.get('chinese', 0)  # Kanji использует китайские символы
        japanese_total = hiragana + katakana + kanji

        if total_alpha == 0:
            return {'native_ratio': 0, 'quality': 'empty'}

        japanese_ratio = japanese_total / total_alpha

        quality_info = {
            'native_ratio': japanese_ratio,
            'hiragana_count': hiragana,
            'katakana_count': katakana,
            'kanji_count': kanji
        }

        if japanese_ratio >= 0.8:
            quality_info.update({
                'quality': 'excellent',
                'message': "✅ 日本語音声認識が成功しました"
            })
        elif japanese_ratio >= 0.5:
            quality_info.update({
                'quality': 'good',
                'message': "✓ 日本語の認識が良好です"
            })
        elif japanese_ratio >= 0.2:
            quality_info.update({
                'quality': 'mixed',
                'message': "⚠️ 混合言語の認識 (一部日本語)",
                'recommendations': [
                    "ゆっくりはっきりと話す",
                    "英語を混ぜない",
                    "静かな場所で録音する"
                ]
            })
        else:
            quality_info.update({
                'quality': 'poor',
                'message': "❌ 認識品質が良くありません",
                'recommendations': [
                    "純粋な日本語を話す",
                    "ゆっくりはっきりと話す",
                    "静かな場所で録音する",
                    "良いマイクを使用する"
                ]
            })

        return quality_info

    def _analyze_korean_quality(self, text: str, script_counts: Dict) -> Dict:
        """Анализ качества корейского текста"""
        total_alpha = sum(script_counts.values())
        hangul = script_counts.get('hangul', 0) + script_counts.get('hangul_jamo', 0)

        if total_alpha == 0:
            return {'native_ratio': 0, 'quality': 'empty'}

        korean_ratio = hangul / total_alpha

        quality_info = {'native_ratio': korean_ratio}

        if korean_ratio >= 0.8:
            quality_info.update({
                'quality': 'excellent',
                'message': "✅ 한국어 음성 인식이 성공했습니다"
            })
        elif korean_ratio >= 0.5:
            quality_info.update({
                'quality': 'good',
                'message': "✓ 한국어 인식이 양호합니다"
            })
        elif korean_ratio >= 0.2:
            quality_info.update({
                'quality': 'mixed',
                'message': "⚠️ 혼합 언어 인식 (일부 한국어)",
                'recommendations': [
                    "천천히 명확하게 말하기",
                    "영어를 섞지 않기",
                    "조용한 곳에서 녹음하기"
                ]
            })
        else:
            quality_info.update({
                'quality': 'poor',
                'message': "❌ 인식 품질이 좋지 않습니다",
                'recommendations': [
                    "순수한 한국어로 말하기",
                    "천천히 명확하게 말하기",
                    "조용한 곳에서 녹음하기",
                    "좋은 마이크 사용하기"
                ]
            })

        return quality_info

    def _analyze_vietnamese_quality(self, text: str, script_counts: Dict) -> Dict:
        """Анализ качества вьетнамского текста"""
        # Вьетнамский использует латиницу с диакритиками
        total_alpha = sum(script_counts.values())
        vietnamese_markers = script_counts.get('vietnamese', 0)
        latin_count = script_counts.get('latin', 0)

        # Проверяем наличие вьетнамских диакритических знаков
        vietnamese_diacritics = sum(1 for char in text if '\u1EA0' <= char <= '\u1EF9')
        vietnamese_ratio = vietnamese_diacritics / len(text) if text else 0

        quality_info = {'native_ratio': vietnamese_ratio}

        if vietnamese_ratio >= 0.1:  # Для вьетнамского достаточно 10% диакритиков
            quality_info.update({
                'quality': 'excellent',
                'message': "✅ Nhận dạng tiếng Việt thành công"
            })
        elif latin_count > 0 and self._has_vietnamese_words(text):
            quality_info.update({
                'quality': 'good',
                'message': "✓ Nhận dạng tiếng Việt tốt"
            })
        else:
            quality_info.update({
                'quality': 'poor',
                'message': "❌ Chất lượng nhận dạng không tốt",
                'recommendations': [
                    "Nói tiếng Việt thuần túy",
                    "Nói chậm và rõ ràng",
                    "Ghi âm ở nơi yên tĩnh"
                ]
            })

        return quality_info

    def _has_transliteration(self, text: str, language: str) -> bool:
        """Проверяет наличие транслитерации для указанного языка"""
        if language not in self.transliteration_keywords:
            return False

        text_lower = text.lower()
        keywords = self.transliteration_keywords[language]

        found_keywords = sum(1 for keyword in keywords if keyword in text_lower)
        return found_keywords >= 2  # Минимум 2 ключевых слова для подтверждения

    def _has_vietnamese_words(self, text: str) -> bool:
        """Проверяет наличие вьетнамских слов"""
        vietnamese_words = ['vietnam', 'viet', 'pho', 'banh', 'xin', 'chao', 'cam on']
        text_lower = text.lower()
        return any(word in text_lower for word in vietnamese_words)

    def format_quality_message(self, analysis: Dict, language: str) -> str:
        """
        Форматирует сообщение о качестве транскрипции

        Args:
            analysis: Результат анализа от analyze_script_quality
            language: Код языка

        Returns:
            Отформатированное сообщение
        """
        message = analysis.get('message', '')

        if analysis.get('recommendations'):
            message += "\n\n💡 Рекомендации:\n"
            for rec in analysis['recommendations']:
                message += f"• {rec}\n"

        # Добавляем статистику если качество не отличное
        if analysis.get('quality') != 'excellent' and analysis.get('native_ratio', 0) > 0:
            message += f"\n📊 Нативных символов: {analysis['native_ratio']:.1%}"

        return message.strip()

    def should_retry_transcription(self, analysis: Dict) -> bool:
        """
        Определяет, стоит ли повторить транскрипцию с принудительным языком

        Args:
            analysis: Результат анализа

        Returns:
            True если стоит повторить транскрипцию
        """
        return (analysis.get('has_transliteration', False) and
                analysis.get('native_ratio', 0) < 0.3)