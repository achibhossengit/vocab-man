from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def home(request):
    return render(request, 'core/home.html', {
        'nav': 'home',
        'query': request.GET.get('q', ''),
    })


@login_required
def profile(request):
    user = request.user
    name = ' '.join(part for part in (user.first_name, user.last_name) if part)
    return render(request, 'core/profile.html', {'name': name})
