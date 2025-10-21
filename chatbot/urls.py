from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/help/', views.chat_help, name='chat_help'),
]


