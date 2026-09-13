from django import template
from django.utils.html import format_html
from builtins import sum as _sum


register = template.Library()


@register.filter
def sum(data, field):
    """Суммирует значения поля в списке словарей."""
    total = 0
    for item in data:
        val = item.get(field, 0)
        if val is not None:
            try:
                total += float(val)
            except (TypeError, ValueError):
                pass
    return round(total, 2)


@register.filter
def avg(data, field):
    """Вычисляет среднее значение поля."""
    values = []
    for item in data:
        val = item.get(field)
        if val is not None:
            try:
                values.append(float(val))
            except (TypeError, ValueError):
                pass
    return round(_sum(values) / len(values), 2) if values else 0


@register.filter
def unique_pcs(data):
    """Подсчитывает уникальные pcs_no в списке."""
    seen = set()
    for item in data:
        if item.get("pcs_no"):
            seen.add(item["pcs_no"])
    return len(seen)


@register.simple_tag(takes_context=True)
def sort_link(context, field, label, extra_class=""):
    """
    Генерирует ссылку-заголовок колонки для сортировки.
    Сохраняет остальные GET-параметры, переключает направление сортировки.
    """
    request = context["request"]
    params = request.GET.copy()
    current_sort = params.get("sort", "")
    current_dir = params.get("dir", "asc")

    if current_sort == field:
        new_dir = "desc" if current_dir == "asc" else "asc"
    else:
        new_dir = "asc"

    params["sort"] = field
    params["dir"] = new_dir
    url = f"{request.path}?{params.urlencode()}"

    arrow = ""
    link_class = "sort-link text-decoration-none text-dark"
    if extra_class:
        link_class += f" {extra_class}"
    if current_sort == field:
        arrow = " ▲" if current_dir == "asc" else " ▼"
        link_class += " sorted"

    return format_html('<a href="{}" class="{}">{}{}</a>', url, link_class, label, arrow)


@register.filter
def sort_table(data, sort_spec):
    """
    Сортирует список словарей по полю.
    sort_spec — "field_name:asc|desc".
    None всегда сортируются в конец.
    """
    if not sort_spec or not isinstance(data, list):
        return data

    parts = sort_spec.split(":", 1)
    if len(parts) != 2:
        return data

    field, direction = parts
    reverse = direction == "desc"

    def get_key(item):
        val = item.get(field) if isinstance(item, dict) else None
        if val is None:
            return (0,) if reverse else (1,)
        return (0, val)

    return sorted(data, key=get_key, reverse=reverse)
