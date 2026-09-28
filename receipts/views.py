from django.http import HttpResponse


def home(request):
    return HttpResponse("Чек на удачу — сервис запущен.")
