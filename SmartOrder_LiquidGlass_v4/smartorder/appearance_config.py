"""Validated, portable presentation preferences; no UI or database imports."""
from copy import deepcopy

FONT_ROLES = {
    "window_title": ("Заголовок окна", 14, 600),
    "caption": ("Подписи верхней панели", 12, 400),
    "heading": ("Заголовки разделов", 22, 700),
    "body": ("Текст и подписи", 12, 400),
    "buttons": ("Кнопки", 13, 600),
    "inputs": ("Поля ввода и списки", 13, 400),
    "table": ("Строки таблиц", 12, 400),
    "table_header": ("Заголовки таблиц", 12, 500),
    "tabs": ("Вкладки", 13, 600),
}


def normalize_appearance(value=None):
    value = value if isinstance(value, dict) else {}
    fonts = value.get("fonts", {})
    fonts = fonts if isinstance(fonts, dict) else {}
    result = {"fonts": {}, "background_mode": value.get("background_mode", "builtin"),
              "background_file": str(value.get("background_file", ""))[:4096]}
    if result["background_mode"] not in {"builtin", "none", "custom"}:
        result["background_mode"] = "builtin"
    for key, (_, size, weight) in FONT_ROLES.items():
        spec = fonts.get(key, {})
        spec = spec if isinstance(spec, dict) else {}
        try:
            chosen_size = max(6.0, min(64.0, float(spec.get("size", size))))
            if chosen_size != chosen_size: chosen_size = size
        except (ValueError, TypeError, OverflowError):
            chosen_size = size
        try: chosen_weight = max(100, min(900, round(int(spec.get("weight", weight)) / 100) * 100))
        except (ValueError, TypeError, OverflowError): chosen_weight = weight
        family = str(spec.get("family", "Segoe UI"))[:128].replace("\n", " ").replace("\r", " ")
        result["fonts"][key] = {"family": family or "Segoe UI", "size": chosen_size,
                               "weight": chosen_weight, "italic": bool(spec.get("italic", False))}
    return deepcopy(result)
