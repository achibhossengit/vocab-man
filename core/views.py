from django.shortcuts import render


def home(request):
    return render(request, 'core/home.html', {
        'nav': 'home',
        'query': request.GET.get('q', ''),
    })


def login_page(request):
    return render(request, 'core/login.html', {'nav': 'login'})
