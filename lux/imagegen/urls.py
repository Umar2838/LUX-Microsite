from django.contrib import admin
from django.urls import include, path
from .views import index, swap_face_api, video_status_api

urlpatterns = [
    path('', index, name='index'),
    path('api/swap-face/', swap_face_api, name='swap_face_api'),
    path('api/video-status/<str:job_id>/', video_status_api, name='video_status_api'),
]
