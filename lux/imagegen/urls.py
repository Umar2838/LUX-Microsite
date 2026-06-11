from django.contrib import admin
from django.urls import include, path
from .views import index, swap_face_api

urlpatterns = [
    path('', index, name='index'),
    path('api/swap-face/', swap_face_api, name='swap_face_api'),
]
