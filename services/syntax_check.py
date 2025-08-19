# syntax_check.py - Проверка синтаксиса

import ast
import sys


def check_syntax(filename):
    """Проверяет синтаксис Python файла"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            source = f.read()

        # Парсим AST
        ast.parse(source, filename)
        print(f"✅ {filename} - синтаксис корректен")
        return True

    except SyntaxError as e:
        print(f"❌ {filename} - синтаксическая ошибка:")
        print(f"   Строка {e.lineno}: {e.text}")
        print(f"   {' ' * (e.offset - 1)}^")
        print(f"   {e.msg}")
        return False

    except Exception as e:
        print(f"❌ {filename} - ошибка чтения: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = "smart_video_service.py"

    check_syntax(filename)