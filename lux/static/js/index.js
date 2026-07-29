let uploadedImageData = null;
let uploadedImageFile = null;
let selectedLook = 'target_image1';
let resultVideoUrl = null;
let videoPollTimer = null;

const LOADER_COUNTDOWN_MS = 2 * 60 * 1000;
const LOADER_RING_RADIUS = 52;
const LOADER_RING_CIRCUMFERENCE = 2 * Math.PI * LOADER_RING_RADIUS;

let loaderAnimationFrame = null;
let loaderPhase = null;

function goToPage(n) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page' + n).classList.add('active');

  if (n === 2) {
    document.getElementById('look1').classList.add('selected');
  }
}

function selectLook(look) {
  selectedLook = look;
  document.querySelectorAll('.look-card').forEach(card => card.classList.remove('selected'));
  document.getElementById('look' + look.replace('target_image', '')).classList.add('selected');
}

function handleUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  uploadedImageFile = file;

  const reader = new FileReader();
  reader.onload = function(e) {
    uploadedImageData = e.target.result;
    const preview = document.getElementById('preview');
    preview.src = uploadedImageData;
    preview.style.display = 'block';
    document.getElementById('uploadIcon').style.display = 'none';
    document.getElementById('uploadText').style.display = 'none';
    document.getElementById('uploadHint').style.display = 'none';
    document.getElementById('uploadZone').style.borderColor = '#c2185b';
    document.getElementById('uploadZone').style.borderStyle = 'solid';
    document.getElementById('btnTransform').classList.add('enabled');
  };
  reader.readAsDataURL(file);
}

function setLoadingText(text) {
  document.getElementById('loadingText').textContent = text;
}

function clearLoaderAnimation() {
  if (loaderAnimationFrame) {
    cancelAnimationFrame(loaderAnimationFrame);
    loaderAnimationFrame = null;
  }
  loaderPhase = null;
}

function resetLoaderRing() {
  const ringWrap = document.getElementById('loadingRingWrap');
  const ringProgress = document.getElementById('loadingRingProgress');
  const timerEl = document.getElementById('loadingTimer');

  ringWrap.classList.remove('indeterminate');
  ringWrap.classList.add('countdown');
  timerEl.style.display = '';
  timerEl.textContent = '2:00';
  ringProgress.style.strokeDasharray = `${LOADER_RING_CIRCUMFERENCE}`;
  ringProgress.style.strokeDashoffset = '0';
}

function switchToIndeterminateLoader(text) {
  if (loaderPhase === 'indeterminate') return;

  loaderPhase = 'indeterminate';
  const ringWrap = document.getElementById('loadingRingWrap');
  ringWrap.classList.remove('countdown');
  ringWrap.classList.add('indeterminate');
  setLoadingText(text || 'Finishing your heroine moment...');
}

function startCountdownLoader(text) {
  clearLoaderAnimation();
  resetLoaderRing();
  if (text) setLoadingText(text);

  loaderPhase = 'countdown';
  const ringProgress = document.getElementById('loadingRingProgress');
  const timerEl = document.getElementById('loadingTimer');
  const startedAt = Date.now();

  function tick() {
    if (loaderPhase !== 'countdown') return;

    const elapsed = Date.now() - startedAt;
    const remaining = Math.max(0, LOADER_COUNTDOWN_MS - elapsed);
    const progress = Math.min(1, elapsed / LOADER_COUNTDOWN_MS);

    ringProgress.style.strokeDashoffset = String(LOADER_RING_CIRCUMFERENCE * progress);

    const totalSeconds = Math.ceil(remaining / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    timerEl.textContent = `${minutes}:${String(seconds).padStart(2, '0')}`;

    if (remaining > 0) {
      loaderAnimationFrame = requestAnimationFrame(tick);
      return;
    }

    switchToIndeterminateLoader('Creating your LUX photo moment...');
  }

  loaderAnimationFrame = requestAnimationFrame(tick);
}

function showLoader(text, options) {
  const opts = options || {};
  document.getElementById('loadingOverlay').classList.add('show');

  if (opts.indeterminate) {
    clearLoaderAnimation();
    resetLoaderRing();
    switchToIndeterminateLoader(text);
    return;
  }

  startCountdownLoader(text);
}

function hideLoader() {
  clearLoaderAnimation();
  resetLoaderRing();
  document.getElementById('loadingOverlay').classList.remove('show');
  setLoadingText('AI Magic in Progress');
}

function resetVideoSection() {
  resultVideoUrl = null;
  if (videoPollTimer) {
    clearTimeout(videoPollTimer);
    videoPollTimer = null;
  }
  document.getElementById('videoFrame').style.display = 'none';
  document.getElementById('btnDownloadVideo').style.display = 'none';
  document.getElementById('videoError').style.display = 'none';
  document.getElementById('videoError').textContent = '';
  document.getElementById('p3ActionBar').style.display = 'none';
  document.getElementById('p3ResultsRow').classList.remove('has-both');
  document.getElementById('page3').classList.remove('has-results');
  const resultVideo = document.getElementById('resultVideo');
  resultVideo.removeAttribute('src');
  resultVideo.load();
}

function showPhotoResult(imageData) {
  const resultImg = document.getElementById('resultImg');
  const photoFrame = document.getElementById('photoFrame');
  resultImg.src = imageData;
  resultImg.style.display = 'block';
  document.getElementById('p3PlaceholderFrame').style.display = 'none';
  photoFrame.style.display = 'block';
  uploadedImageData = imageData;
}

function showResultsComplete(options) {
  const { videoUrl, videoError } = options;

  showPhotoResult(uploadedImageData);

  if (videoUrl) {
    resultVideoUrl = videoUrl;
    document.getElementById('videoFrame').style.display = 'block';
    document.getElementById('btnDownloadVideo').style.display = 'inline-flex';
    document.getElementById('p3ResultsRow').classList.add('has-both');
    document.getElementById('page3').classList.add('has-results');
    const resultVideo = document.getElementById('resultVideo');
    resultVideo.src = videoUrl;
    resultVideo.load();
  }

  if (videoError) {
    const errorEl = document.getElementById('videoError');
    errorEl.textContent = videoError;
    errorEl.style.display = 'block';
    document.getElementById('page3').classList.add('has-results');
  }

  document.getElementById('p3ActionBar').style.display = 'flex';
  hideLoader();
}

function pollVideoStatus(jobId, attempt) {
  const maxAttempts = 60;
  const intervalMs = Math.min(4000 * Math.pow(1.3, attempt), 15000);

  fetch('/api/video-status/' + jobId + '/')
    .then(response => response.json())
    .then(data => {
      if (data.status === 'completed' && data.video_url) {
        showResultsComplete({ videoUrl: data.video_url });
        return;
      }
      if (data.status === 'failed' || data.error) {
        showResultsComplete({
          videoError: 'Video could not be created. Your photo is still ready to download.',
        });
        return;
      }
      if (attempt >= maxAttempts) {
        showResultsComplete({
          videoError: 'Video is taking longer than expected. Your photo is still ready to download.',
        });
        return;
      }
      videoPollTimer = setTimeout(() => pollVideoStatus(jobId, attempt + 1), intervalMs);
    })
    .catch(() => {
      if (attempt >= maxAttempts) {
        showResultsComplete({
          videoError: 'Video status could not be loaded. Your photo is still ready to download.',
        });
        return;
      }
      videoPollTimer = setTimeout(() => pollVideoStatus(jobId, attempt + 1), intervalMs);
    });
}

function startVideoGeneration(jobId) {
  if (loaderPhase !== 'indeterminate') {
    switchToIndeterminateLoader('Creating your LUX video moment...');
  } else {
    setLoadingText('Creating your LUX video moment...');
  }
  pollVideoStatus(jobId, 0);
}

function doTransform() {
  if (!uploadedImageFile) return;

  resetVideoSection();
  showLoader('Creating your LUX photo moment...');

  document.getElementById('sc1').classList.remove('active');
  document.getElementById('sc1').classList.add('done');
  document.getElementById('sl1').classList.add('done');
  document.getElementById('sc2').classList.add('active');

  const formData = new FormData();
  formData.append('image', uploadedImageFile);
  formData.append('target_image', selectedLook);

  fetch('/api/swap-face/', {
    method: 'POST',
    body: formData,
    headers: {
      'X-CSRFToken': getCookie('csrftoken')
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      document.getElementById('sc2').classList.remove('active');
      document.getElementById('sc2').classList.add('done');
      document.getElementById('sl2').classList.add('done');
      document.getElementById('sc3').classList.add('active');

      showPhotoResult(data.result);
      goToPage(3);

      if (data.video_job_id) {
        startVideoGeneration(data.video_job_id);
      } else {
        showResultsComplete({
          videoError: data.video_error || 'Video generation was not started.',
        });
      }
    } else {
      hideLoader();
      alert('Error: ' + (data.error || 'Face swap failed'));

      document.getElementById('sc1').classList.add('active');
      document.getElementById('sc1').classList.remove('done');
      document.getElementById('sl1').classList.remove('done');
      document.getElementById('sc2').classList.remove('active');
    }
  })
  .catch(error => {
    hideLoader();
    alert('Error: ' + error.message);

    document.getElementById('sc1').classList.add('active');
    document.getElementById('sc1').classList.remove('done');
    document.getElementById('sl1').classList.remove('done');
    document.getElementById('sc2').classList.remove('active');
  });
}

function downloadImage() {
  if (!uploadedImageData) return;
  const a = document.createElement('a');
  a.href = uploadedImageData;
  a.download = 'lux-heroine-moment.png';
  a.click();
}

function downloadVideo() {
  if (!resultVideoUrl) return;
  const a = document.createElement('a');
  a.href = resultVideoUrl;
  a.download = 'lux-heroine-moment.mp4';
  a.target = '_blank';
  a.rel = 'noopener';
  a.click();
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
