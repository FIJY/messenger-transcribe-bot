# services/export_service.py
import os
import logging
from docx import Document
from fpdf import FPDF

logger = logging.getLogger(__name__)


class ExportService:
    """
    Сервис для генерации файлов (Markdown, DOCX, PDF) из текста транскрипции и отчетов.
    """

    def __init__(self, transcription_text: str, report_text: str = None, title: str = "Exported Document"):
        """
        Инициализирует сервис с текстами.

        :param transcription_text: Полный текст транскрипции.
        :param report_text: Текст сгенерированного отчета (например, summary).
        :param title: Заголовок документа.
        """
        self.transcription_text = transcription_text
        self.report_text = report_text
        self.title = title

    def to_markdown(self) -> str:
        """Генерирует содержимое файла в формате Markdown."""
        content = f"# {self.title}\n\n## Транскрипция\n\n{self.transcription_text}"
        if self.report_text:
            content += f"\n\n## Отчет\n\n{self.report_text}"

        filepath = "export.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def to_docx(self) -> str:
        """Генерирует документ в формате DOCX."""
        document = Document()
        document.add_heading(self.title, level=1)
        document.add_heading('Транскрипция', level=2)
        document.add_paragraph(self.transcription_text)

        if self.report_text:
            document.add_heading('Отчет', level=2)
            document.add_paragraph(self.report_text)

        filepath = "export.docx"
        document.save(filepath)
        return filepath

    def to_pdf(self) -> str:
        """
        Генерирует документ в формате PDF с поддержкой кириллицы.
        ВАЖНО: Для корректной работы требуется шрифт DejaVuSans.ttf в корне проекта.
        """
        pdf = FPDF()
        pdf.add_page()

        try:
            # Попытка добавить шрифт для поддержки UTF-8 (кириллицы)
            pdf.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
            font_family = 'DejaVu'
        except RuntimeError:
            logger.warning("Шрифт DejaVuSans.ttf не найден. Кириллица в PDF может отображаться некорректно.")
            font_family = 'Arial'  # Резервный шрифт

        # Заголовок
        pdf.set_font(font_family, 'B', 16)
        # Костыль для поддержки UTF-8 в заголовках в некоторых версиях FPDF
        pdf.cell(0, 10, self.title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
        pdf.ln(10)

        # Транскрипция
        pdf.set_font(font_family, 'B', 14)
        pdf.cell(0, 10, 'Транскрипция'.encode('latin-1', 'replace').decode('latin-1'), ln=True)
        pdf.set_font(font_family, '', 12)
        pdf.multi_cell(0, 10, self.transcription_text)

        # Отчет (если есть)
        if self.report_text:
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 14)
            pdf.cell(0, 10, 'Отчет'.encode('latin-1', 'replace').decode('latin-1'), ln=True)
            pdf.set_font(font_family, '', 12)
            pdf.multi_cell(0, 10, self.report_text)

        filepath = "export.pdf"
        pdf.output(filepath)
        return filepath
