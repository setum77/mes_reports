from django import forms


class UploadFileForm(forms.Form):
    file = forms.FileField(
        label="Excel файл (.xls, .xlsx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xls,.xlsx", "class": "file-input"}),
    )

    def clean_file(self):
        f = self.files.get("file")
        if not f:
            raise forms.ValidationError("Файл не выбран")
        if not f.name.lower().endswith((".xls", ".xlsx")):
            raise forms.ValidationError("Поддерживаются только файлы .xls и .xlsx")
        return f
