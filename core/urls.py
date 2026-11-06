from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', RedirectView.as_view(pattern_name='account_login', query_string=True), name='login'),
]
