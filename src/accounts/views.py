from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.views import View

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login


def is_admin(user):
    return user.is_authenticated and user.is_staff


admin_required = user_passes_test(is_admin, login_url="accounts:login")


class LoginView(View):
    template_name = "accounts/login.html"

    def get(self, request):
        form = AuthenticationForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("home")
        return render(request, self.template_name, {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect("home")
