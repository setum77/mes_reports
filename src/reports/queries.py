"""
Основные запросы для отчетов.
Все функции возвращают списки словарей, готовые для шаблонов.
"""
from datetime import timedelta
from django.db import connection

STATION_FOL_START = 10
STATION_FOL_END = 50
STATION_BOL_START = 60
STATION_BOL_END = 130

STATION_NAME_TRANSLATIONS = {
    "PCB投料": "PCB Loading",
    "等离子清洁": "Plasma Cleaning",
    "壳体组装": "Assembly",
    "静置": "Standing",
    "高温老化": "Oven (High-Temperature Aging / Furnace)",
    "标定刷写": "Firmware Flashing (Programming)",
    "标定检测": "Firmware Verification",
    "气密测试": "Seal Test",
    "PIN测试": "PIN Test",
    "贴标": "Labeling",
}

STATION_POSITION_TRANSLATIONS = {
    "10": "PCB Loading",
    "20": "FCT1",
    "30": "Plasma Cleaning",
    "50": "Assembly",
    "60": "Standing",
    "70": "Oven (High-Temperature Aging / Furnace)",
    "80": "FCT2",
    "90": "Firmware Flashing (Programming)",
    "A100": "Firmware Verification",
    "A110": "Seal Test",
    "A120": "PIN Test",
    "A130": "Labeling",
}


def translate_workstation_name(position_no, workstation_name):
    name = (workstation_name or "").strip()
    if name in STATION_NAME_TRANSLATIONS:
        return STATION_NAME_TRANSLATIONS[name]
    return STATION_POSITION_TRANSLATIONS.get(str(position_no or "").strip(), name)


def dictfetchall(cursor):
    """Возвращает строки курсора как список dict."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_date_range(filter_type, start_date=None, end_date=None):
    """
    Возвращает (start, end) — диапазон дат для фильтрации.
    filter_type: '30d', 'month', '90d', '180d', 'year', 'period'
    """
    from django.utils import timezone
    today = timezone.now().date()

    if filter_type == "30d":
        return today - timedelta(days=29), today
    elif filter_type == "month":
        start = today.replace(day=1)
        return start, today
    elif filter_type == "90d":
        return today - timedelta(days=89), today
    elif filter_type == "180d":
        return today - timedelta(days=179), today
    elif filter_type == "year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    elif filter_type == "period" and start_date and end_date:
        return start_date, end_date
    return today - timedelta(days=29), today


def report1_orders(start_date=None, end_date=None):
    """
    Отчет 1: Сводный отчет по лотам.
    Production = уникальные PCSNo прошедшие станцию 010 с OK
    Ok = уникальные PCSNo прошедшие станцию 130 с OK
    Defect = SN из Diff (если <=10 иначе сообщение)
    """
    if start_date and end_date:
        df_clause = "WHERE DATE(created_date) >= %s AND DATE(created_date) <= %s"
        dp = [start_date, end_date]
    else:
        df_clause = "WHERE TRUE"
        dp = []

    sql = f"""
        WITH lots AS (
            SELECT DISTINCT lot_number FROM production_productionrecord
            {df_clause}
        ),
        production_cte AS (
            SELECT lot_number, COUNT(DISTINCT pcs_no) as cnt
            FROM production_productionrecord
            {df_clause}
            AND subop_no = %s AND result = 'OK'
            GROUP BY lot_number
        ),
        ok_cte AS (
            SELECT lot_number, COUNT(DISTINCT pcs_no) as cnt
            FROM production_productionrecord
            {df_clause}
            AND subop_no = %s AND result = 'OK'
            GROUP BY lot_number
        ),
        start_cte AS (
            SELECT lot_number, MIN(created_date) as dt
            FROM production_productionrecord
            {df_clause}
            AND subop_no = %s
            GROUP BY lot_number
        ),
        finish_cte AS (
            SELECT lot_number, MAX(created_date) as dt
            FROM production_productionrecord
            {df_clause}
            AND subop_no = %s AND result = 'OK'
            GROUP BY lot_number
        ),
        defect_cte AS (
            SELECT DISTINCT d.lot_number, d.pcs_no
            FROM production_productionrecord d
            {df_clause}
            AND d.subop_no = %s AND d.result = 'OK'
            AND d.pcs_no NOT IN (
                SELECT DISTINCT pcs_no FROM production_productionrecord
                WHERE subop_no = %s AND result = 'OK'
            )
        ),
        defect_sns AS (
            SELECT lot_number, STRING_AGG(pcs_no, ', ' ORDER BY pcs_no) as sns, COUNT(*) as cnt
            FROM defect_cte
            GROUP BY lot_number
        )
        SELECT
            l.lot_number,
            COALESCE(p.cnt, 0) as production,
            COALESCE(o.cnt, 0) as ok_count,
            s.dt as start_dt,
            f.dt as finish_dt,
            COALESCE(ds.cnt, 0) as defect_count,
            ds.sns as defect_sns
        FROM lots l
        LEFT JOIN production_cte p ON p.lot_number = l.lot_number
        LEFT JOIN ok_cte o ON o.lot_number = l.lot_number
        LEFT JOIN start_cte s ON s.lot_number = l.lot_number
        LEFT JOIN finish_cte f ON f.lot_number = l.lot_number
        LEFT JOIN defect_sns ds ON ds.lot_number = l.lot_number
        ORDER BY l.lot_number DESC
    """
    # Build params in SQL order of %s placeholders:
    # lots: dp → production: dp + FOL_START → ok: dp + BOL_END → start: dp + FOL_START
    # → finish: dp + BOL_END → defect: dp + FOL_START + BOL_END
    stations = [
        STATION_FOL_START, STATION_BOL_END,
        STATION_FOL_START, STATION_BOL_END,
        STATION_FOL_START, STATION_BOL_END,
    ]
    if dp:
        final_params = (
            dp +
            dp + [stations[0]] +
            dp + [stations[1]] +
            dp + [stations[2]] +
            dp + [stations[3]] +
            dp + [stations[4], stations[5]]
        )
    else:
        final_params = stations

    with connection.cursor() as cursor:
        cursor.execute(sql, final_params)
        rows = dictfetchall(cursor)

    results = []
    for i, row in enumerate(rows, 1):
        production = row["production"]
        ok = row["ok_count"]
        diff = production - ok
        defect_count = row["defect_count"]
        defect_display = row["defect_sns"] if defect_count <= 10 else "SN не прошедших сборку более 10 штук"

        from production.models import LotInfo
        lot_info = LotInfo.objects.filter(lot_number=row["lot_number"]).first()

        results.append({
            "N": i,
            "LOT": row["lot_number"],
            "production_spec": lot_info.production_spec if lot_info else "",
            "Total": lot_info.plan_total if lot_info else None,
            "Production": production,
            "Ok": ok,
            "Diff": diff,
            "Defect": defect_display,
            "defect_sns": row["defect_sns"].split(", ") if row["defect_sns"] and defect_count <= 10 else [],
            "start": row["start_dt"],
            "finish": row["finish_dt"],
            "comment": lot_info.comment if lot_info else "",
        })

    return results


def report2_line_productivity(start_date, end_date):
    """
    Отчет 2: Производительность линии по дням.
    FOL: время [первый 010 → последний 050] на дату, уникальные PCSNo на выходе 050 со статусом OK (последний раз)
    BOL: время [первый 060 → последний 130] на дату, уникальные PCSNo на выходе 130 со статусом OK (последний раз)
    """
    sql = f"""
        WITH date_series AS (
            SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date as dt
        ),
        -- Last OK exit at station 50 per PCSNo
        fol_last_ok AS (
            SELECT pcs_no, MAX(created_date) as dt
            FROM production_productionrecord
            WHERE subop_no = {STATION_FOL_END} AND result = 'OK'
            GROUP BY pcs_no
        ),
        -- Last OK exit at station 130 per PCSNo
        bol_last_ok AS (
            SELECT pcs_no, MAX(created_date) as dt
            FROM production_productionrecord
            WHERE subop_no = {STATION_BOL_END} AND result = 'OK'
            GROUP BY pcs_no
        ),
        -- FOL hourly bounds per date
        fol_bounds AS (
            SELECT
                DATE(created_date) as dt,
                MIN(created_date) as first_ts,
                MAX(created_date) as last_ts
            FROM production_productionrecord
            WHERE subop_no IN ({STATION_FOL_START}, {STATION_FOL_END})
            AND created_date::date >= %s AND created_date::date <= %s
            GROUP BY DATE(created_date)
        ),
        -- BOL hourly bounds per date
        bol_bounds AS (
            SELECT
                DATE(created_date) as dt,
                MIN(created_date) as first_ts,
                MAX(created_date) as last_ts
            FROM production_productionrecord
            WHERE subop_no IN ({STATION_BOL_START}, {STATION_BOL_END})
            AND created_date::date >= %s AND created_date::date <= %s
            GROUP BY DATE(created_date)
        )
        SELECT
            d.dt as report_date,
            fb.first_ts as fol_start,
            fb.last_ts as fol_end,
            (EXTRACT(EPOCH FROM (fb.last_ts - fb.first_ts)) / 3600.0) as fol_hours,
            (
                SELECT COUNT(DISTINCT fk.pcs_no)
                FROM fol_last_ok fk
                WHERE DATE(fk.dt) = d.dt
            ) as fol_production,
            bb.first_ts as bol_start,
            bb.last_ts as bol_end,
            (EXTRACT(EPOCH FROM (bb.last_ts - bb.first_ts)) / 3600.0) as bol_hours,
            (
                SELECT COUNT(DISTINCT bk.pcs_no)
                FROM bol_last_ok bk
                WHERE DATE(bk.dt) = d.dt
            ) as bol_production
        FROM date_series d
        LEFT JOIN fol_bounds fb ON fb.dt = d.dt
        LEFT JOIN bol_bounds bb ON bb.dt = d.dt
        ORDER BY d.dt
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [start_date, end_date, start_date, end_date, start_date, end_date])
        rows = dictfetchall(cursor)

    for r in rows:
        fol_hours = r["fol_hours"] or 0
        r["fol_hours"] = round(fol_hours, 2)
        r["fol_production"] = r["fol_production"] or 0
        r["fol_speed"] = round(r["fol_production"] / fol_hours, 2) if fol_hours > 0 else 0

        bol_hours = r["bol_hours"] or 0
        r["bol_hours"] = round(bol_hours, 2)
        r["bol_production"] = r["bol_production"] or 0
        r["bol_speed"] = round(r["bol_production"] / bol_hours, 2) if bol_hours > 0 else 0

    return rows


def report3_monthly_productivity(start_date, end_date):
    """
    Отчет 3: Сводный по месяцам.
    Та же логика что и Report 2, но группировка по месяцам.
    """
    sql = f"""
        WITH month_series AS (
            SELECT generate_series(
                DATE(DATE_TRUNC('month', %s::date)),
                DATE_TRUNC('month', %s::date)::date,
                '1 month'::interval
            )::date as dt
        ),
        fol_last_ok AS (
            SELECT pcs_no, MAX(created_date) as dt
            FROM production_productionrecord
            WHERE subop_no = {STATION_FOL_END} AND result = 'OK'
            AND created_date::date >= %s AND created_date::date <= %s
            GROUP BY pcs_no
        ),
        bol_last_ok AS (
            SELECT pcs_no, MAX(created_date) as dt
            FROM production_productionrecord
            WHERE subop_no = {STATION_BOL_END} AND result = 'OK'
            AND created_date::date >= %s AND created_date::date <= %s
            GROUP BY pcs_no
        ),
        fol_bounds AS (
            SELECT
                DATE_TRUNC('month', created_date)::date as dt,
                MIN(created_date) as first_ts,
                MAX(created_date) as last_ts
            FROM production_productionrecord
            WHERE subop_no IN ({STATION_FOL_START}, {STATION_FOL_END})
            AND created_date::date >= %s AND created_date::date <= %s
            GROUP BY DATE_TRUNC('month', created_date)
        ),
        bol_bounds AS (
            SELECT
                DATE_TRUNC('month', created_date)::date as dt,
                MIN(created_date) as first_ts,
                MAX(created_date) as last_ts
            FROM production_productionrecord
            WHERE subop_no IN ({STATION_BOL_START}, {STATION_BOL_END})
            AND created_date::date >= %s AND created_date::date <= %s
            GROUP BY DATE_TRUNC('month', created_date)
        )
        SELECT
            m.dt as report_month,
            fb.first_ts as fol_start,
            fb.last_ts as fol_end,
            (EXTRACT(EPOCH FROM (fb.last_ts - fb.first_ts)) / 3600.0) as fol_hours,
            (
                SELECT COUNT(DISTINCT fk.pcs_no)
                FROM fol_last_ok fk
                WHERE DATE_TRUNC('month', fk.dt)::date = m.dt
            ) as fol_production,
            bb.first_ts as bol_start,
            bb.last_ts as bol_end,
            (EXTRACT(EPOCH FROM (bb.last_ts - bb.first_ts)) / 3600.0) as bol_hours,
            (
                SELECT COUNT(DISTINCT bk.pcs_no)
                FROM bol_last_ok bk
                WHERE DATE_TRUNC('month', bk.dt)::date = m.dt
            ) as bol_production
        FROM month_series m
        LEFT JOIN fol_bounds fb ON fb.dt = m.dt
        LEFT JOIN bol_bounds bb ON bb.dt = m.dt
        ORDER BY m.dt
    """

    params = [start_date, end_date] * 5
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = dictfetchall(cursor)

    for r in rows:
        fol_hours = r["fol_hours"] or 0
        r["fol_hours"] = round(fol_hours, 2)
        r["fol_production"] = r["fol_production"] or 0
        r["fol_speed"] = round(r["fol_production"] / fol_hours, 2) if fol_hours > 0 else 0

        bol_hours = r["bol_hours"] or 0
        r["bol_hours"] = round(bol_hours, 2)
        r["bol_production"] = r["bol_production"] or 0
        r["bol_speed"] = round(r["bol_production"] / bol_hours, 2) if bol_hours > 0 else 0

    return rows


def report4_defects(start_date=None, end_date=None, limit=None):
    """
    Отчет 4: Брак.
    BU прошедшие 010 с OK, но не прошедшие 130 с OK + ручные браки.
    limit: если задан, ограничивает количество записей (для "последних N").
    """
    from production.models import ManualDefect

    params = []
    date_clause = ""
    if start_date and end_date:
        date_clause = "AND r.created_date::date >= %s AND r.created_date::date <= %s"
        params.extend([start_date, end_date])

    limit_clause = f"LIMIT {limit}" if limit else ""

    sql = f"""
        SELECT
            p.pcs_no,
            p.production_spec,
            p.lot_number,
            p.entry_date
        FROM (
            SELECT DISTINCT
                r.pcs_no,
                r.production_spec,
                r.lot_number,
                MIN(r.created_date) as entry_date
            FROM production_productionrecord r
            WHERE r.subop_no = {STATION_FOL_START} AND r.result = 'OK'
            {date_clause}
            AND r.pcs_no NOT IN (
                SELECT DISTINCT pcs_no
                FROM production_productionrecord
                WHERE subop_no = {STATION_BOL_END} AND result = 'OK'
            )
            GROUP BY r.pcs_no, r.production_spec, r.lot_number
        ) p
        ORDER BY p.entry_date DESC
        {limit_clause}
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = dictfetchall(cursor)

    manual_defects = ManualDefect.objects.all().order_by("-created_at")[:50]
    manual_data = []
    for md in manual_defects:
        manual_data.append({
            "pcs_no": md.pcs_no,
            "production_spec": md.production_spec or "",
            "lot_number": md.lot_number or "",
            "entry_date": md.entry_date,
            "is_manual": True,
            "comment": md.comment,
        })

    for row in rows:
        row["is_manual"] = False
        row["comment"] = ""

    return rows + manual_data


def report5_repeated_passes(start_date=None, end_date=None, limit=50):
    """
    Отчет 5: Повторные проходы станций.
    BU прошедшие какую-либо станцию более одного раза.
    """
    from production.models import Report5Comment

    params = []
    date_clause = ""
    if start_date and end_date:
        date_clause = "created_date::date >= %s AND created_date::date <= %s"
        date_params = [start_date, end_date]
    else:
        date_params = []

    limit_clause = f"LIMIT {limit}" if limit else ""
    where_clause = f"WHERE {date_clause}" if date_clause else ""

    sql = f"""
        WITH repeated AS (
            SELECT pcs_no, lot_number, production_spec, subop_no
            FROM production_productionrecord r
            {where_clause}
            GROUP BY pcs_no, lot_number, production_spec, subop_no
            HAVING COUNT(*) > 1
        )
        SELECT
            r.pcs_no,
            r.lot_number,
            r.production_spec,
            r.subop_no as station,
            STRING_AGG(
                TO_CHAR(rr.created_date, 'YYYY-MM-DD HH24:MI:SS'),
                ', ' ORDER BY rr.created_date
            ) as dates
        FROM repeated r
        JOIN production_productionrecord rr ON rr.pcs_no = r.pcs_no AND rr.subop_no = r.subop_no
        {where_clause}
        GROUP BY r.pcs_no, r.lot_number, r.production_spec, r.subop_no
        ORDER BY r.pcs_no, r.subop_no
        {limit_clause}
    """
    params = date_params + date_params
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = dictfetchall(cursor)

    comments_map = {}
    if rows:
        existing = Report5Comment.objects.filter(
            pcs_no__in=[r["pcs_no"] for r in rows],
            station_no__in=[r["station"] for r in rows],
        )
        for ec in existing:
            comments_map[(ec.pcs_no, ec.station_no)] = ec.comment

    for row in rows:
        row["comment"] = comments_map.get((row["pcs_no"], row["station"]), "")

    return rows


def report6_serial_number(pcs_no):
    if not pcs_no:
        return []

    from production.models import ProductionRecord

    records = ProductionRecord.objects.filter(pcs_no=pcs_no).order_by("created_date", "id")
    return [
        {
            "pcs_no": record.pcs_no,
            "lot_number": record.lot_number,
            "production_spec": record.production_spec or "",
            "subop_no": record.subop_no,
            "workstation_name": translate_workstation_name(
                record.position_no, record.workstation_name
            ),
            "created_date": record.created_date,
            "result": record.result or "",
            "test_data": record.test_data or "",
        }
        for record in records
    ]


def report7_station130_output(start_date, end_date):
    if not start_date or not end_date:
        return []

    sql = """
        WITH ranked AS (
            SELECT
                pcs_no,
                lot_number,
                production_spec,
                created_date,
                ROW_NUMBER() OVER (
                    PARTITION BY pcs_no
                    ORDER BY created_date DESC, id DESC
                ) AS rn
            FROM production_productionrecord
            WHERE subop_no = %s
              AND result = 'OK'
              AND created_date::date >= %s
              AND created_date::date <= %s
        )
        SELECT
            pcs_no,
            lot_number,
            production_spec,
            created_date
        FROM ranked
        WHERE rn = 1
        ORDER BY created_date DESC, pcs_no
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [STATION_BOL_END, start_date, end_date])
        return dictfetchall(cursor)
