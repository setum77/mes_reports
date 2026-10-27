"""
Основные запросы для отчетов.
Все функции возвращают списки словарей, готовые для шаблонов.
"""
from collections import Counter
from datetime import date, timedelta
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
        defect_display = row["defect_sns"] if defect_count < 10 else "SN не прошедших сборку более 10 штук"

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
            "defect_sns": row["defect_sns"].split(", ") if row["defect_sns"] and defect_count < 10 else [],
            "start": row["start_dt"],
            "finish": row["finish_dt"],
            "comment": lot_info.comment if lot_info else "",
        })

    return results


def report2_line_productivity(start_date, end_date, lot_number=None):
    """
    Отчет 2: Производительность линии по дням.
    FOL: время [первый 010 → последний 050] на дату, уникальные PCSNo на выходе 050 со статусом OK (последний раз)
    BOL: время [первый 060 → последний 130] на дату, уникальные PCSNo на выходе 130 со статусом OK (последний раз)

    lot_number: если задан, ограничивает данные по лоту (для фильтра «По лоту»).
    При фильтре по лоту без диапазона дат диапазон вычисляется из записей лота.
    """
    # При фильтре «По лоту» без диапазона дат вычисляем диапазон из записей лота
    # (нужен для generate_series).
    if lot_number and (not start_date or not end_date):
        range_sql = """
            SELECT MIN(DATE(created_date)), MAX(DATE(created_date))
            FROM production_productionrecord
            WHERE lot_number = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(range_sql, [lot_number])
            row = cursor.fetchone()
        if row and row[0] and row[1]:
            start_date, end_date = row[0], row[1]
        else:
            return []

    # Без диапазона дат и лота нечего отображать.
    if not start_date or not end_date:
        return []

    lot_clause = "AND lot_number = %s" if lot_number else ""
    lot_param = [lot_number] if lot_number else []

    sql = f"""
        WITH date_series AS (
            SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date as dt
        ),
        -- Last OK exit at station 50 per PCSNo
        fol_last_ok AS (
            SELECT pcs_no, MAX(created_date) as dt
            FROM production_productionrecord
            WHERE subop_no = {STATION_FOL_END} AND result = 'OK'
            {lot_clause}
            GROUP BY pcs_no
        ),
        -- Last OK exit at station 130 per PCSNo
        bol_last_ok AS (
            SELECT pcs_no, MAX(created_date) as dt
            FROM production_productionrecord
            WHERE subop_no = {STATION_BOL_END} AND result = 'OK'
            {lot_clause}
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
            {lot_clause}
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
            {lot_clause}
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

    params = [start_date, end_date]
    params += lot_param            # fol_last_ok
    params += lot_param            # bol_last_ok
    params += lot_param + [start_date, end_date]  # fol_bounds: lot, start, end
    params += lot_param + [start_date, end_date]  # bol_bounds: lot, start, end

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

        r["has_data"] = (r["fol_hours"] > 0) or (r["bol_hours"] > 0)

    return rows


def _aggregate_monthly(daily_rows, year):
    """
    Агрегирует дневные строки отчёта №2 в 12 месячных строк.

    Для каждого месяца суммируется fol_hours, fol_production, bol_hours,
    bol_production. Месячная скорость — среднее дневных скоростей только по
    активным дням соответствующей линии (как в _report2_summary).
    Пустые месяцы остаются с нулевыми значениями, сохраняется хронология.
    """
    months = []
    for month in range(1, 13):
        month_rows = [
            row for row in daily_rows
            if row.get("report_date") and row["report_date"].year == year
            and row["report_date"].month == month
        ]

        fol_hours = round(sum((row.get("fol_hours") or 0) for row in month_rows), 2)
        fol_production = sum((row.get("fol_production") or 0) for row in month_rows)
        bol_hours = round(sum((row.get("bol_hours") or 0) for row in month_rows), 2)
        bol_production = sum((row.get("bol_production") or 0) for row in month_rows)

        fol_speeds = [
            row.get("fol_speed", 0)
            for row in month_rows
            if (row.get("fol_hours") or 0) > 0
        ]
        bol_speeds = [
            row.get("bol_speed", 0)
            for row in month_rows
            if (row.get("bol_hours") or 0) > 0
        ]
        fol_speed = round(sum(fol_speeds) / len(fol_speeds), 2) if fol_speeds else 0
        bol_speed = round(sum(bol_speeds) / len(bol_speeds), 2) if bol_speeds else 0

        months.append({
            "report_month": date(year, month, 1),
            "fol_hours": fol_hours,
            "fol_production": fol_production,
            "fol_speed": fol_speed,
            "bol_hours": bol_hours,
            "bol_production": bol_production,
            "bol_speed": bol_speed,
        })
    return months


def report3_monthly_productivity(start_date, end_date):
    """
    Отчет 3: Сводный по месяцам.

    Строится на том же дневном наборе, что и отчёт №2
    (report2_line_productivity), с последующей агрегацией по месяцам.
    """
    daily_rows = report2_line_productivity(start_date, end_date)
    return _aggregate_monthly(daily_rows, start_date.year)


REPORT4_STATION_NAMES = {
    20: "FCT1",
    30: "Pasma Cleaning",
    50: "Assembly",
    60: "Standing",
    70: "High-Temperature Aging",
    80: "FCT2",
    90: "Firmware Flashing (Programming)",
    100: "Firmware Verification",
    110: "Seal Test",
    120: "PIN Test",
    130: "Labeling",
}


def _report4_last_ok_rows(pcs_numbers):
    unique_pcs_numbers = list(dict.fromkeys(pcs_numbers))
    if not unique_pcs_numbers:
        return {}

    sql = """
        WITH station_order(station_no, station_rank) AS (
            VALUES
                (20, 1),
                (30, 2),
                (50, 3),
                (60, 4),
                (70, 5),
                (80, 6),
                (90, 7),
                (100, 8),
                (110, 9),
                (120, 10),
                (130, 11)
        ),
        last_ok_per_station AS (
            SELECT
                r.pcs_no,
                r.subop_no,
                MAX(r.created_date) AS last_ok_at
            FROM production_productionrecord AS r
            JOIN station_order AS so
              ON so.station_no = r.subop_no
            WHERE UPPER(TRIM(COALESCE(r.result, ''))) = 'OK'
            GROUP BY r.pcs_no, r.subop_no
        ),
        ranked_last_ok AS (
            SELECT
                los.pcs_no,
                los.subop_no AS last_ok_station,
                los.last_ok_at,
                ROW_NUMBER() OVER (
                    PARTITION BY los.pcs_no
                    ORDER BY so.station_rank DESC, los.last_ok_at DESC
                ) AS rn
            FROM last_ok_per_station AS los
            JOIN station_order AS so
              ON so.station_no = los.subop_no
            WHERE los.pcs_no = ANY(%s)
        )
        SELECT
            pcs_no,
            last_ok_station,
            last_ok_at
        FROM ranked_last_ok
        WHERE rn = 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [unique_pcs_numbers])
        return {
            row["pcs_no"]: row
            for row in dictfetchall(cursor)
        }


def report4_defects(start_date=None, end_date=None, limit=None):
    """
    Отчет 4: Брак.
    BU прошедшие 010 с OK, но не прошедшие 130 с OK + ручные браки.
    limit: если задан, ограничивает количество записей (для "последних N").
    """
    from production.models import ManualDefect, SNComment

    params = []
    date_clause = ""
    if start_date and end_date:
        date_clause = "AND r.created_date::date >= %s AND r.created_date::date <= %s"
        params.extend([start_date, end_date])

    limit_clause = "LIMIT %s" if limit else ""
    if limit:
        params.append(limit)

    sql = f"""
        SELECT
            p.pcs_no,
            p.production_spec,
            p.lot_number,
            p.entry_date
        FROM (
            SELECT
                r.pcs_no,
                r.production_spec,
                r.lot_number,
                MIN(r.created_date) AS entry_date
            FROM production_productionrecord AS r
            WHERE r.subop_no = {STATION_FOL_START}
              AND UPPER(TRIM(COALESCE(r.result, ''))) = 'OK'
              {date_clause}
              AND NOT EXISTS (
                  SELECT 1
                  FROM production_productionrecord AS completed
                  WHERE completed.pcs_no = r.pcs_no
                    AND completed.subop_no = {STATION_BOL_END}
                    AND UPPER(TRIM(COALESCE(completed.result, ''))) = 'OK'
              )
            GROUP BY r.pcs_no, r.production_spec, r.lot_number
        ) AS p
        ORDER BY p.entry_date DESC
        {limit_clause}
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = dictfetchall(cursor)

    manual_defects = ManualDefect.objects.all().order_by("-created_at")[:50]
    manual_data = []
    manual_comments = {}
    for md in manual_defects:
        manual_comments[md.pcs_no] = md.comment
        manual_data.append({
            "pcs_no": md.pcs_no,
            "production_spec": md.production_spec or "",
            "lot_number": md.lot_number or "",
            "entry_date": md.entry_date,
            "last_ok_station": None,
            "last_ok_at": None,
            "is_manual": True,
            "comment": md.comment,
        })

    pcs_numbers = [row["pcs_no"] for row in rows] + [
        row["pcs_no"] for row in manual_data
    ]
    comments = {}
    if pcs_numbers:
        comments = {
            item["pcs_no"]: item["comment"]
            for item in SNComment.objects.filter(pcs_no__in=pcs_numbers).values(
                "pcs_no", "comment"
            )
        }
    last_ok_by_pcs = _report4_last_ok_rows(pcs_numbers)

    for row in rows:
        last_ok = last_ok_by_pcs.get(row["pcs_no"], {})
        row["last_ok_station"] = last_ok.get("last_ok_station")
        row["last_ok_at"] = last_ok.get("last_ok_at")
        row["last_station"] = REPORT4_STATION_NAMES.get(
            row["last_ok_station"], ""
        )
        row["last_station_date"] = row["last_ok_at"]
        row["is_manual"] = False
        row["comment"] = comments.get(row["pcs_no"], "")

    for row in manual_data:
        last_ok = last_ok_by_pcs.get(row["pcs_no"], {})
        row["last_ok_station"] = last_ok.get("last_ok_station")
        row["last_ok_at"] = last_ok.get("last_ok_at")
        row["last_station"] = REPORT4_STATION_NAMES.get(
            row["last_ok_station"], ""
        )
        row["last_station_date"] = row["last_ok_at"]
        row["comment"] = comments.get(row["pcs_no"], row.get("comment", ""))

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

    from production.models import ProductionRecord, SNComment

    records = list(
        ProductionRecord.objects.filter(pcs_no=pcs_no).order_by("created_date", "id")
    )
    comments = {}
    if records:
        comments = {
            item["pcs_no"]: item["comment"]
            for item in SNComment.objects.filter(
                pcs_no__in=[record.pcs_no for record in records]
            ).values("pcs_no", "comment")
        }
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
            "comment": comments.get(record.pcs_no, ""),
        }
         for record in records
     ]


def report6_summary(pcs_no):
    """
    Сводка по серийному номеру для отчёта 6.

    Возвращает словарь с:
      pcs_no, lot_number, production_spec, assembly_start,
      assembly_end, completed, last_station, last_station_date,
      last_station_status, comment, double_passes.

    double_passes — станции, пройденные более 2 раз (формат: "20 - 3, 70 - 2").

    completed = True, если SN прошёл станцию 130 (STATION_BOL_END) с OK.
    completed = False — сборка не завершена: в last_station / last_station_date
    возвращается последняя пройденная станция и её дата/время,
    last_station_status — статус этой станции (OK или NG).
    """
    if not pcs_no:
        return None

    from production.models import ProductionRecord, SNComment

    records = list(
        ProductionRecord.objects.filter(pcs_no=pcs_no).order_by("created_date", "id")
    )
    if not records:
        return None

    first = records[0]

    start_record = next(
        (r for r in records if r.subop_no == STATION_FOL_START),
        None,
    )
    assembly_start = start_record.created_date if start_record else first.created_date

    end_record = None
    for r in reversed(records):
        if r.subop_no == STATION_BOL_END and (r.result or "").upper() == "OK":
            end_record = r
            break

    comment = ""
    sn_comment = SNComment.objects.filter(pcs_no=pcs_no).first()
    if sn_comment:
        comment = sn_comment.comment

    subop_counts = Counter(r.subop_no for r in records)
    double_passes = ", ".join(
        f"{sn} - {count}" for sn, count in sorted(subop_counts.items()) if count > 2
    )

    if end_record:
        return {
            "pcs_no": pcs_no,
            "lot_number": end_record.lot_number,
            "production_spec": end_record.production_spec or "",
            "assembly_start": assembly_start,
            "assembly_end": end_record.created_date,
            "completed": True,
            "last_station": "",
            "last_station_date": None,
            "comment": comment,
            "double_passes": double_passes,
        }

    last_record = records[-1]

    station_name = REPORT4_STATION_NAMES.get(last_record.subop_no)
    if not station_name:
        station_name = translate_workstation_name(last_record.position_no, last_record.workstation_name)

    return {
        "pcs_no": pcs_no,
        "lot_number": first.lot_number,
        "production_spec": first.production_spec or "",
        "assembly_start": assembly_start,
        "assembly_end": None,
        "completed": False,
        "last_station": station_name or "",
        "last_station_date": last_record.created_date,
        "last_station_status": (last_record.result or "").upper(),
        "comment": comment,
        "double_passes": double_passes,
    }


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


# ========================
# Отчет 8: По станциям
# ========================

# Станции с колонками Ok (уникальные SN) — промежуточные станции FOL/BOL.
REPORT8_UNIQUE_STATIONS = {10, 30, 50, 60, 70}

# Станции-тестеры с колонками Ok/NG/%/NG SN.
REPORT8_TEST_STATIONS = {20, 80, 90, 100, 110, 120, 130}

# Читаемые подписи станций для графика и сводки (только станции с %).
REPORT8_CHART_STATIONS = [
    (20, "FCT1"),
    (80, "FCT2"),
    (90, "Прошивка"),
    (100, "Проверка прошивки"),
    (110, "Герметичность"),
    (120, "PIN"),
    (130, "Этикетка"),
]

# Цвета линий диаграммы «Средний % NG по дням» — по порядку станций REPORT8_CHART_STATIONS.
# Каждый NG-тип своего цвета (HEX) — используется в Chart.js и в Excel-экспорте.
REPORT8_CHART_COLORS = [
    "#4361EE",  # FCT1 — синий
    "#F77F00",  # FCT2 — оранжевый
    "#06A786",  # Прошивка — бирюзовый
    "#8F3FFC",  # Проверка прошивки — фиолетовый
    "#DC3545",  # Герметичность — красный
    "#17A2B8",  # PIN — циан
    "#D63384",  # Этикетка — розовый
]

# Подписи столбцов для таблицы отчёта 8.
# (key, station_no, kind, row1_title, row2_title, css_group)
# kind: date | unique_ok | all_ok | all_ng | pct | ng_sns | diff_fol | diff_bol
REPORT8_COLUMNS = [
    ("report_date", None, "date", "Дата", "", "date"),
    ("station_010_ok", 10, "unique_ok", "010 Подача PCB-плат", "Ok", "process"),
    ("station_020_ok", 20, "all_ok", "020 FCT1", "Ok", "test"),
    ("station_020_ng", 20, "all_ng", "020 FCT1", "NG", "test"),
    ("station_020_pct", 20, "pct", "020 FCT1", "%", "test"),
    ("station_020_ng_sns", 20, "ng_sns", "020 FCT1", "NG SN", "test"),
    ("station_030_ok", 30, "unique_ok", "030 Плазма", "Ok", "process"),
    ("station_050_ok", 50, "unique_ok", "050 Сборка корпуса", "Ok", "process"),
    ("fol_diff", None, "diff_fol", "Разница FOL", "Разница", "diff"),
    ("station_060_ok", 60, "unique_ok", "060 Стабилизация", "Ok", "process"),
    ("station_070_ok", 70, "unique_ok", "070 Burn-in", "Ok", "process"),
    ("station_080_ok", 80, "all_ok", "080 FCT2", "Ok", "test"),
    ("station_080_ng", 80, "all_ng", "080 FCT2", "NG", "test"),
    ("station_080_pct", 80, "pct", "080 FCT2", "%", "test"),
    ("station_080_ng_sns", 80, "ng_sns", "080 FCT2", "NG SN", "test"),
    ("station_090_ok", 90, "all_ok", "090 Прошивка", "Ok", "test"),
    ("station_090_ng", 90, "all_ng", "090 Прошивка", "NG", "test"),
    ("station_090_pct", 90, "pct", "090 Прошивка", "%", "test"),
    ("station_090_ng_sns", 90, "ng_sns", "090 Прошивка", "NG SN", "test"),
    ("station_100_ok", 100, "all_ok", "100 Проверка прошивки", "Ok", "test"),
    ("station_100_ng", 100, "all_ng", "100 Проверка прошивки", "NG", "test"),
    ("station_100_pct", 100, "pct", "100 Проверка прошивки", "%", "test"),
    ("station_100_ng_sns", 100, "ng_sns", "100 Проверка прошивки", "NG SN", "test"),
    ("station_110_ok", 110, "all_ok", "110 Проверка герметичности", "Ok", "test"),
    ("station_110_ng", 110, "all_ng", "110 Проверка герметичности", "NG", "test"),
    ("station_110_pct", 110, "pct", "110 Проверка герметичности", "%", "test"),
    ("station_110_ng_sns", 110, "ng_sns", "110 Проверка герметичности", "NG SN", "test"),
    ("station_120_ok", 120, "all_ok", "120 PIN-тест", "Ok", "test"),
    ("station_120_ng", 120, "all_ng", "120 PIN-тест", "NG", "test"),
    ("station_120_pct", 120, "pct", "120 PIN-тест", "%", "test"),
    ("station_120_ng_sns", 120, "ng_sns", "120 PIN-тест", "NG SN", "test"),
    ("station_130_ok", 130, "all_ok", "130 Наклейка этикетки", "Ok", "test"),
    ("station_130_ng", 130, "all_ng", "130 Наклейка этикетки", "NG", "test"),
    ("station_130_pct", 130, "pct", "130 Наклейка этикетки", "%", "test"),
    ("station_130_ng_sns", 130, "ng_sns", "130 Наклейка этикетки", "NG SN", "test"),
    ("bol_diff", None, "diff_bol", "Разница BOL", "Разница", "diff"),
]

# Заголовки для строки 1 таблицы (с colspan для сгруппированных станций).
REPORT8_HEADER_GROUPS = [
    {"title": "Дата", "span": 1},
    {"title": "010 Подача PCB-плат", "span": 1},
     {"title": "020 FCT1", "span": 4},
    {"title": "030 Плазма", "span": 1},
    {"title": "050 Сборка корпуса", "span": 1},
    {"title": "Разница FOL", "span": 1},
    {"title": "060 Стабилизация", "span": 1},
    {"title": "070 Burn-in", "span": 1},
     {"title": "080 FCT2", "span": 4},
     {"title": "090 Прошивка", "span": 4},
     {"title": "100 Проверка прошивки", "span": 4},
     {"title": "110 Проверка герметичности", "span": 4},
     {"title": "120 PIN-тест", "span": 4},
     {"title": "130 Наклейка этикетки", "span": 4},
    {"title": "Разница BOL", "span": 1},
]

# Ключи станций, используемых в сводке и графике (только станции с %).
REPORT8_CHART_KEYS = [
    "station_020_pct", "station_080_pct", "station_090_pct",
    "station_100_pct", "station_110_pct", "station_120_pct", "station_130_pct",
]


def report8_table_columns():
    """REPORT8_COLUMNS с вычисленным флагом group_start (индекс 6).

    group_start = True для первой колонки каждого станционного блока (т.е. когда
    station_no меняется по сравнению с предыдущей колонкой). Используется шаблоном
    отчёта 8 для вертикальных разделителей между блоками станций.
    """
    cols = []
    prev_station = object()
    for key, station_no, kind, r1, r2, css in REPORT8_COLUMNS:
        cols.append([key, station_no, kind, r1, r2, css, station_no != prev_station])
        prev_station = station_no
    return cols



def report8_stations(start_date, end_date, lot_number=None):
    """
    Отчет 8: По станциям (качество прохождения станций по дням).

    Для каждой даты возвращает одну строку со столбцами по каждой станции:
    уникальное количество OK, все OK, все NG, % NG от OK и список SN с NG.
    Включаются только даты, где есть хотя бы одна запись.
    """
    stations = [10, 20, 30, 50, 60, 70, 80, 90, 100, 110, 120, 130]
    stations_in = ", ".join(str(s) for s in stations)

    sql = f"""
        SELECT
            DATE(created_date) AS report_date,
            subop_no AS station_no,
            COUNT(DISTINCT pcs_no) FILTER (WHERE result = 'OK') AS unique_ok,
            COUNT(*) FILTER (WHERE result = 'OK') AS ok_count,
            COUNT(*) FILTER (WHERE result = 'NG') AS ng_count,
            STRING_AGG(DISTINCT pcs_no, ', ' ORDER BY pcs_no) FILTER (WHERE result = 'NG') AS ng_sns
        FROM production_productionrecord
        WHERE 1=1
          {("AND created_date::date >= %s AND created_date::date <= %s" if start_date and end_date else "")}
          {("AND lot_number = %s" if lot_number else "")}
          AND subop_no IN ({stations_in})
        GROUP BY DATE(created_date), subop_no
        ORDER BY report_date, subop_no
    """
    if start_date and end_date:
        params = [start_date, end_date]
    else:
        params = []
    if lot_number:
        params = params + [lot_number]

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        raw = dictfetchall(cursor)

    # Pivot rows into one dict per date.
    by_date = {}
    for r in raw:
        d = r["report_date"]
        if d not in by_date:
            by_date[d] = {"report_date": d}
        station = r["station_no"]
        by_date[d][f"station_{station}_unique_ok"] = r["unique_ok"] or 0
        by_date[d][f"station_{station}_ok_count"] = r["ok_count"] or 0
        by_date[d][f"station_{station}_ng_count"] = r["ng_count"] or 0
        by_date[d][f"station_{station}_ng_sns"] = (
            [s for s in (r["ng_sns"] or "").split(",")] if r["ng_sns"] else []
        )

    results = []
    for d in sorted(by_date):
        row = by_date[d]
        for key, station_no, kind, _r1, _r2, _css in REPORT8_COLUMNS:
            if kind == "date":
                continue
            if kind == "unique_ok":
                row[key] = row.get(f"station_{station_no}_unique_ok", 0)
            elif kind == "all_ok":
                row[key] = row.get(f"station_{station_no}_ok_count", 0)
            elif kind == "all_ng":
                row[key] = row.get(f"station_{station_no}_ng_count", 0)
            elif kind == "pct":
                ok = row.get(f"station_{station_no}_ok_count", 0)
                ng = row.get(f"station_{station_no}_ng_count", 0)
                row[key] = round(ng / ok * 100, 2) if ok else 0.0 if ng == 0 else 100.0
            elif kind == "ng_sns":
                row[key] = row.get(f"station_{station_no}_ng_sns", [])
            elif kind == "diff_fol":
                row[key] = row.get("station_50_unique_ok", 0) - row.get("station_10_unique_ok", 0)
            elif kind == "diff_bol":
                row[key] = row.get("station_130_unique_ok", 0) - row.get("station_60_unique_ok", 0)
        results.append(row)

    return results
