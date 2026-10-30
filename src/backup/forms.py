from django import forms


class RestoreForm(forms.Form):
    backup_name = forms.ChoiceField(
        label="Бэкап",
        choices=(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        from backup.utils import list_backups

        super().__init__(*args, **kwargs)
        backups = list_backups()
        choices = [(b["name"], b["name"]) for b in backups]
        self.fields["backup_name"].choices = choices
        if not choices:
            self.fields["backup_name"].choices = [("", "Нет доступных бэкапов")]


class UploadRestoreForm(forms.Form):
    archive = forms.FileField(
        label="Архив бэкапа (.tar.gz)",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".tar.gz,.tgz"}),
    )


class WipeConfirmForm(forms.Form):
    confirmation = forms.CharField(
        label="Введите 'WIPE_ALL_DATA_CONFIRMED' для подтверждения",
        widget=forms.TextInput(attrs={"class": "form-control", "size": 50}),
    )
