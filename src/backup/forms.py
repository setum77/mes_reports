from django import forms


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