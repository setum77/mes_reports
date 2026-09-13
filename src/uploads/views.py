from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from accounts.views import admin_required
from uploads.forms import UploadFileForm
from uploads.excel_parser import parse_excel_file, import_to_database, ExcelParseError


@method_decorator(admin_required, name="dispatch")
class UploadHomeView(TemplateView):
    template_name = "uploads/upload_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = UploadFileForm()
        return context


@method_decorator(admin_required, name="dispatch")
class UploadFileView(View):
    template_name = "uploads/upload_home.html"

    def get(self, request):
        return redirect("uploads:upload_home")

    def post(self, request):
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["file"]
            try:
                records = parse_excel_file(f)
            except ExcelParseError as e:
                messages.error(request, str(e))
                return render(request, self.template_name, {"form": form})
            except Exception as e:
                messages.error(request, f"Ошибка обработки файла: {e}")
                return render(request, self.template_name, {"form": form})

            if not records:
                messages.warning(request, "Файл не содержит данных для загрузки.")
                return render(request, self.template_name, {"form": form})

            result = import_to_database(records, created_by=getattr(request.user, "username", "system"))
            return redirect("uploads:upload_success",
                            inserted=result["inserted"],
                            duplicates=result["duplicates"],
                            total=result["total"])
        return render(request, self.template_name, {"form": form})


class UploadSuccessView(TemplateView):
    template_name = "uploads/upload_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["inserted"] = kwargs.get("inserted", 0)
        context["duplicates"] = kwargs.get("duplicates", 0)
        context["total"] = kwargs.get("total", 0)
        return context
