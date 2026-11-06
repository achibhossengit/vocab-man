from django.shortcuts import render


def home(request):
    return render(request, 'core/home.html', {
        'nav': 'home',
        'query': request.GET.get('q', ''),
        'recent': [],
        'wordpacks': [],
    })
