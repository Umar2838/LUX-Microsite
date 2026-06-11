from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.conf import settings
import json
import os
import io
import base64
from PIL import Image
import numpy as np
import insightface
from insightface.app import FaceAnalysis
import logging

logger = logging.getLogger(__name__)

# ---------- Initialize models globally ----------
_models_initialized = False
_face_analyzer = None
_face_swapper = None

def initialize_models():
    global _models_initialized, _face_analyzer, _face_swapper
    
    if _models_initialized:
        return
    
    try:
        logger.info("Initializing insightface models...")
        _face_analyzer = FaceAnalysis(name='buffalo_l')
        _face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
        
        # Load the swapper model
        model_path = os.path.join(settings.BASE_DIR, 'inswapper_128.onnx')
        if os.path.exists(model_path):
            _face_swapper = insightface.model_zoo.get_model(model_path)
        else:
            _face_swapper = insightface.model_zoo.get_model('inswapper_128.onnx', download=True, download_zip=True)
        
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

def index(request):
    return render(request, 'index.html')

@require_http_methods(["POST"])
def swap_face_api(request):
    try:
        # Get uploaded image file
        if 'image' not in request.FILES:
            return JsonResponse({'error': 'No image provided'}, status=400)
        
        user_image_file = request.FILES['image']
        
        # Get target image name from POST data
        target_image_name = request.POST.get('target_image', 'target_image1')
        
        # Validate target image name to prevent path traversal
        valid_targets = ['target_image1', 'target_image2', 'target_image3']
        if target_image_name not in valid_targets:
            target_image_name = 'target_image1'
        
        # Load target image
        target_image_path = os.path.join(settings.BASE_DIR, 'static', 'assets', f'{target_image_name}.png')
        if not os.path.exists(target_image_path):
            return JsonResponse({'error': f'Target image {target_image_name} not found'}, status=500)
        
        # Read and process images
        user_image = Image.open(user_image_file).convert('RGB')
        target_image = Image.open(target_image_path).convert('RGB')
        
        # Convert PIL images to numpy arrays
        user_image_array = np.array(user_image)
        target_image_array = np.array(target_image)
        
        # Initialize models
        face_analyzer, face_swapper = get_models()
        
        # Detect faces
        user_faces = face_analyzer.get(user_image_array)
        target_faces = face_analyzer.get(target_image_array)
        
        if len(user_faces) == 0:
            return JsonResponse({'error': 'No face detected in your image. Please upload a clear front-facing photo.'}, status=400)
        
        if len(target_faces) == 0:
            return JsonResponse({'error': 'No face detected in target image'}, status=500)
        
        # Swap faces
        user_face = user_faces[0]
        target_face = target_faces[0]
        result_array = face_swapper.get(target_image_array, target_face, user_face, paste_back=True)
        
        # Convert result to PIL Image
        result_image = Image.fromarray(np.uint8(result_array)).convert('RGB')
        
        # Convert to base64
        buffered = io.BytesIO()
        result_image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return JsonResponse({'success': True, 'result': f'data:image/png;base64,{img_str}'})
    
    except Exception as e:
        logger.error(f"Error in swap_face_api: {str(e)}")
        return JsonResponse({'error': f'Processing error: {str(e)}'}, status=500)
