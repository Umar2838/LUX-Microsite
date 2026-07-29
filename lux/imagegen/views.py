from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
import os
import io
import uuid
import base64
import shutil
import requests
from urllib.parse import urlparse
from PIL import Image
import numpy as np
import insightface
from insightface.app import FaceAnalysis
import logging

logger = logging.getLogger(__name__)

_models_initialized = False
_face_analyzer = None
_face_swapper = None

VMODEL_CREATE_URL = 'https://api.vmodel.ai/api/tasks/v1/create'
VMODEL_GET_URL = 'https://api.vmodel.ai/api/tasks/v1/get/{task_id}'
_pending_face_images = {}

MEDIA_FACES_DIR = 'faces'
MEDIA_VIDEOS_DIR = 'videos'


def initialize_models():
    global _models_initialized, _face_analyzer, _face_swapper

    if _models_initialized:
        return

    try:
        logger.info("Initializing insightface models...")
        _face_analyzer = FaceAnalysis(name='buffalo_l')
        _face_analyzer.prepare(ctx_id=0, det_size=(640, 640))

        model_path = os.path.join(settings.BASE_DIR, 'inswapper_128.onnx')
        if os.path.exists(model_path):
            _face_swapper = insightface.model_zoo.get_model(model_path)
        else:
            _face_swapper = insightface.model_zoo.get_model(
                'inswapper_128.onnx', download=True, download_zip=True
            )

        _models_initialized = True
        logger.info("Models initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing models: {str(e)}")
        raise


def get_models():
    global _face_analyzer, _face_swapper
    if not _models_initialized:
        initialize_models()
    return _face_analyzer, _face_swapper


def vmodel_headers():
    return {
        'Authorization': f'Bearer {settings.VMODEL_API_TOKEN}',
        'Content-Type': 'application/json',
    }


def get_public_base_url(request):
    return "http://127.0.0.1:8000"



def is_usable_public_base(url):
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if not host or host in {'127.0.0.1', 'localhost', '0.0.0.0', '::1'}:
        return False
    return True


def ensure_media_dirs():
    for subdir in (MEDIA_FACES_DIR, MEDIA_VIDEOS_DIR):
        os.makedirs(os.path.join(settings.MEDIA_ROOT, subdir), exist_ok=True)


def build_media_url(request, relative_path):
    public_base = get_public_base_url(request)
    media_url = settings.MEDIA_URL
    if not media_url.endswith('/'):
        media_url += '/'
    return f'{public_base}{media_url}{relative_path}'


def save_face_image_to_media(user_image):
    ensure_media_dirs()
    filename = f'{uuid.uuid4().hex}.jpg'
    relative_path = f'{MEDIA_FACES_DIR}/{filename}'
    filepath = os.path.join(settings.MEDIA_ROOT, relative_path)
    user_image.save(filepath, format='JPEG', quality=95)
    return relative_path, filename


def cleanup_face_image(filename):
    filepath = os.path.join(settings.MEDIA_ROOT, MEDIA_FACES_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)


def ensure_target_video_in_media():
    ensure_media_dirs()
    video_filename = settings.VMODEL_TARGET_VIDEO
    media_video_path = os.path.join(settings.MEDIA_ROOT, MEDIA_VIDEOS_DIR, video_filename)

    if os.path.exists(media_video_path):
        return video_filename

    static_video_path = os.path.join(
        settings.BASE_DIR, 'static', 'assets', video_filename
    )
    if not os.path.exists(static_video_path):
        raise FileNotFoundError(f'Target video not found: {static_video_path}')

    shutil.copy2(static_video_path, media_video_path)
    logger.info('Copied target video to media: %s', media_video_path)
    return video_filename


def get_public_target_video_url(request):
    if settings.VMODEL_TARGET_VIDEO_URL:
        return settings.VMODEL_TARGET_VIDEO_URL

    video_filename = ensure_target_video_in_media()
    return build_media_url(request, f'{MEDIA_VIDEOS_DIR}/{video_filename}')


def get_public_face_image_url(request, user_image):
    relative_path, filename = save_face_image_to_media(user_image)
    return build_media_url(request, relative_path), filename


def create_vmodel_video_task(target_image_url, source_video_url):
    payload = {
        'version': settings.VMODEL_VERSION,
        'input': {
            'target': target_image_url,
            'source': source_video_url,
        },
    }
    response = requests.post(
        VMODEL_CREATE_URL,
        headers=vmodel_headers(),
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get('code') != 200:
        raise ValueError(data.get('message') or 'VModel task creation failed')

    task_id = (data.get('result') or {}).get('task_id')
    if not task_id:
        raise ValueError('VModel API did not return a task_id')
    return task_id


def fetch_vmodel_task(task_id):
    response = requests.get(
        VMODEL_GET_URL.format(task_id=task_id),
        headers={'Authorization': f'Bearer {settings.VMODEL_API_TOKEN}'},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if data.get('code') != 200:
        raise ValueError(data.get('message') or 'Could not fetch VModel task')
    return data.get('result') or {}


def extract_vmodel_video_url(task_result):
    output = task_result.get('output')
    if isinstance(output, list) and output:
        return output[0]
    if isinstance(output, dict):
        for key in ('video', 'url', 'output', 'result'):
            value = output.get(key)
            if value:
                return value
    if isinstance(output, str) and output.startswith('http'):
        return output
    return None


def start_video_job(request, user_image, response_data):
    if not settings.VMODEL_API_TOKEN:
        response_data['video_status'] = 'not_configured'
        response_data['video_error'] = (
            'Video API token missing. Add VMODEL_API_TOKEN to lux/.env and restart.'
        )
        return

    public_base = get_public_base_url(request)
    if not is_usable_public_base(public_base):
        response_data['video_status'] = 'not_configured'
        response_data['video_error'] = (
            'Set PUBLIC_BASE_URL in lux/.env to your public AWS domain '
            '(e.g. https://your-app.example.com) so VModel can fetch media files.'
        )
        return

    face_filename = None
    try:
        target_image_url, face_filename = get_public_face_image_url(request, user_image)
        source_video_url = get_public_target_video_url(request)
        logger.info(
            'Starting VModel video job: target=%s source=%s',
            target_image_url,
            source_video_url,
        )
        task_id = create_vmodel_video_task(target_image_url, source_video_url)
        if face_filename:
            _pending_face_images[task_id] = face_filename
        response_data['video_job_id'] = task_id
        response_data['video_status'] = 'processing'
    except requests.HTTPError as e:
        if face_filename:
            cleanup_face_image(face_filename)
        detail = e.response.text[:300] if e.response is not None else ''
        logger.error('VModel create task error: %s %s', e, detail)
        response_data['video_status'] = 'failed'
        response_data['video_error'] = 'Could not start video job. Check API token and credits.'
    except Exception as e:
        if face_filename:
            cleanup_face_image(face_filename)
        logger.error('Error starting video job: %s', e)
        response_data['video_status'] = 'failed'
        response_data['video_error'] = f'Could not start video job: {e}'


def index(request):
    return render(request, 'index.html')


DEFAULT_OPENAI_PROMPT = (
    'I want to replace the girl in the 2nd photo with the girl from the 1st photo, '
    'keeping the same face features and body features from photo 1. '
    'Preserve the pose, outfit, lighting, and background from photo 2. '
    'The result should look natural and photorealistic.'
)


def get_target_image_path(target_image_name):
    valid_targets = ['target_image1', 'target_image2', 'target_image3']
    if target_image_name not in valid_targets:
        target_image_name = 'target_image1'

    target_image_path = os.path.join(
        settings.BASE_DIR, 'static', 'assets', f'{target_image_name}.png'
    )
    return target_image_name, target_image_path


def compress_image_for_api(image):
    """Resize and JPEG-compress an image before sending it to the OpenAI API."""
    img = image.convert('RGB')
    max_dimension = settings.OPENAI_IMAGE_MAX_DIMENSION
    max_bytes = settings.OPENAI_IMAGE_MAX_BYTES
    quality = settings.OPENAI_IMAGE_JPEG_QUALITY

    width, height = img.size
    if max(width, height) > max_dimension:
        scale = max_dimension / max(width, height)
        img = img.resize(
            (int(width * scale), int(height * scale)),
            Image.Resampling.LANCZOS,
        )

    while True:
        current_quality = quality
        while current_quality >= 50:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=current_quality, optimize=True)
            data = buffer.getvalue()
            if len(data) <= max_bytes:
                logger.info(
                    'Compressed image for OpenAI: %dx%d, %d KB, quality=%d',
                    img.width,
                    img.height,
                    len(data) // 1024,
                    current_quality,
                )
                return data
            current_quality -= 10

        width, height = img.size
        if max(width, height) <= 512:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=50, optimize=True)
            return buffer.getvalue()

        scale = 0.85
        img = img.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )
        quality = settings.OPENAI_IMAGE_JPEG_QUALITY


def image_to_api_bytes(image):
    return compress_image_for_api(image)


def generate_image_with_openai(user_image, target_image, prompt=None):
    if not settings.OPENAI_API_KEY:
        raise ValueError('OpenAI API key missing. Add OPENAI_API_KEY to lux/.env and restart.')

    edit_prompt = prompt or DEFAULT_OPENAI_PROMPT
    user_bytes = image_to_api_bytes(user_image)
    target_bytes = image_to_api_bytes(target_image)

    files = [
        ('image[]', ('user_photo.jpg', user_bytes, 'image/jpeg')),
        ('image[]', ('target_photo.jpg', target_bytes, 'image/jpeg')),
    ]
    data = {
        'model': settings.OPENAI_IMAGE_MODEL,
        'prompt': edit_prompt,
    }

    response = requests.post(
        'https://api.openai.com/v1/images/edits',
        headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
        files=files,
        data=data,
        timeout=180,
    )

    if not response.ok:
        error_detail = response.text[:500]
        logger.error('OpenAI image edit error: %s', error_detail)
        raise ValueError(f'OpenAI image edit failed: {error_detail}')

    result = response.json()
    image_data = result.get('data', [])
    if not image_data:
        raise ValueError('OpenAI did not return an image.')

    b64_image = image_data[0].get('b64_json')
    if not b64_image:
        raise ValueError('OpenAI response did not include image data.')

    return Image.open(io.BytesIO(base64.b64decode(b64_image))).convert('RGB')


@require_http_methods(["POST"])
def swap_face_api(request):
    try:
        if 'image' not in request.FILES:
            return JsonResponse({'error': 'No image provided'}, status=400)

        if not settings.OPENAI_API_KEY:
            return JsonResponse(
                {'error': 'OpenAI API key missing. Add OPENAI_API_KEY to lux/.env and restart.'},
                status=503,
            )

        user_image_file = request.FILES['image']
        target_image_name = request.POST.get('target_image', 'target_image1')
        custom_prompt = request.POST.get('prompt', '').strip() or None

        target_image_name, target_image_path = get_target_image_path(target_image_name)
        if not os.path.exists(target_image_path):
            return JsonResponse(
                {'error': f'Target image {target_image_name} not found'},
                status=500,
            )

        user_image = Image.open(user_image_file).convert('RGB')
        target_image = Image.open(target_image_path).convert('RGB')

        result_image = generate_image_with_openai(user_image, target_image, custom_prompt)

        buffered = io.BytesIO()
        result_image.save(buffered, format='PNG')
        img_str = base64.b64encode(buffered.getvalue()).decode()

        response_data = {
            'success': True,
            'result': f'data:image/png;base64,{img_str}',
        }
        start_video_job(request, user_image, response_data)

        return JsonResponse(response_data)

    except Exception as e:
        logger.error('Error in swap_face_api: %s', e)
        return JsonResponse({'error': f'Processing error: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def video_status_api(request, job_id):
    if not settings.VMODEL_API_TOKEN:
        return JsonResponse({'error': 'Video API is not configured'}, status=503)

    try:
        task_result = fetch_vmodel_task(job_id)
        status = str(task_result.get('status', '')).lower()

        if status in {'succeeded', 'success', 'completed', 'done'}:
            face_filename = _pending_face_images.pop(job_id, None)
            if face_filename:
                cleanup_face_image(face_filename)
            video_url = extract_vmodel_video_url(task_result)
            if not video_url:
                return JsonResponse({
                    'status': 'failed',
                    'error': 'Video completed but no download URL was returned',
                }, status=500)
            return JsonResponse({'status': 'completed', 'video_url': video_url})

        if status in {'failed', 'error', 'canceled', 'cancelled'}:
            face_filename = _pending_face_images.pop(job_id, None)
            if face_filename:
                cleanup_face_image(face_filename)
            error_message = task_result.get('error') or 'Video generation failed'
            return JsonResponse({'status': 'failed', 'error': error_message})

        return JsonResponse({'status': 'processing'})
    except requests.HTTPError as e:
        logger.error(f'VModel task status error: {e}')
        return JsonResponse({'error': 'Could not check video status'}, status=502)
    except Exception as e:
        logger.error(f'Error in video_status_api: {e}')
        return JsonResponse({'error': 'Could not check video status'}, status=500)
