"""Справочник станций производства и значения по умолчанию.

Китайские названия соответствуют реальным значениям `subop name` в выгрузках MES.
Английские и русские названия используются в отчётах и могут редактироваться
администратором через админку.
"""

DEFAULT_STATIONS = [
    {
        "number": 10,
        "position_no": "10",
        "name_zh": "PCB板投料",
        "name_en": "PCB Loading",
        "name_ru": "Подача PCB-плат",
        "sort_order": 10,
    },
    {
        "number": 20,
        "position_no": "20",
        "name_zh": "FCT1",
        "name_en": "FCT1",
        "name_ru": "FCT1",
        "sort_order": 20,
    },
    {
        "number": 30,
        "position_no": "30",
        "name_zh": "等离子清洁",
        "name_en": "Plasma Cleaning",
        "name_ru": "Плазменная очистка",
        "sort_order": 30,
    },
    {
        "number": 50,
        "position_no": "50",
        "name_zh": "壳体组装",
        "name_en": "Assembly",
        "name_ru": "Сборка корпуса",
        "sort_order": 50,
    },
    {
        "number": 60,
        "position_no": "60",
        "name_zh": "静置",
        "name_en": "Standing",
        "name_ru": "Стабилизация",
        "sort_order": 60,
    },
    {
        "number": 70,
        "position_no": "70",
        "name_zh": "高温老化",
        "name_en": "High-Temperature Aging (Burn-in)",
        "name_ru": "Термостарение (Burn-in)",
        "sort_order": 70,
    },
    {
        "number": 80,
        "position_no": "80",
        "name_zh": "FCT2",
        "name_en": "FCT2",
        "name_ru": "FCT2",
        "sort_order": 80,
    },
    {
        "number": 90,
        "position_no": "90",
        "name_zh": "标定刷写",
        "name_en": "Firmware Flashing (Programming)",
        "name_ru": "Прошивка",
        "sort_order": 90,
    },
    {
        "number": 100,
        "position_no": "A100",
        "name_zh": "标定检测",
        "name_en": "Firmware Verification",
        "name_ru": "Проверка прошивки",
        "sort_order": 100,
    },
    {
        "number": 110,
        "position_no": "A110",
        "name_zh": "气密检测",
        "name_en": "Seal Test",
        "name_ru": "Проверка герметичности",
        "sort_order": 110,
    },
    {
        "number": 120,
        "position_no": "A120",
        "name_zh": "PIN检测",
        "name_en": "PIN Test",
        "name_ru": "PIN-тест",
        "sort_order": 120,
    },
    {
        "number": 130,
        "position_no": "A130",
        "name_zh": "贴标",
        "name_en": "Labeling",
        "name_ru": "Наклейка этикетки",
        "sort_order": 130,
    },
]

DEFAULT_STATIONS_BY_NUMBER = {item["number"]: item for item in DEFAULT_STATIONS}
STATION_NUMBERS = tuple(item["number"] for item in DEFAULT_STATIONS)
STATION_NUMBERS_IN_REPORT8 = (10, 20, 30, 50, 60, 70, 80, 90, 100, 110, 120, 130)