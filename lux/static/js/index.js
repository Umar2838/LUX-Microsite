let uploadedImageData = null;
let uploadedImageFile = null;
let selectedLook = 'target_image1'; // Default look

function goToPage(n) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page' + n).classList.add('active');
  
  // Initialize look selection when going to page 2
  if (n === 2) {
    document.getElementById('look1').classList.add('selected');
  }
}

function selectLook(look) {
  selectedLook = look;
  // Update UI to show selection
  document.querySelectorAll('.look-card').forEach(card => card.classList.remove('selected'));
  document.getElementById('look' + look.replace('target_image', '')).classList.add('selected');
}

function handleUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  // Store the file for API upload
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

function doTransform() {
  if (!uploadedImageFile) return;

  // Show loading overlay
  document.getElementById('loadingOverlay').classList.add('show');

  // Update step indicators
  document.getElementById('sc1').classList.remove('active');
  document.getElementById('sc1').classList.add('done');
  document.getElementById('sl1').classList.add('done');
  document.getElementById('sc2').classList.add('active');

  // Create FormData for file upload
  const formData = new FormData();
  formData.append('image', uploadedImageFile);
  formData.append('target_image', selectedLook);

  // Call the face swap API
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
      // Update step 2 complete
      document.getElementById('sc2').classList.remove('active');
      document.getElementById('sc2').classList.add('done');
      document.getElementById('sl2').classList.add('done');
      document.getElementById('sc3').classList.add('active');

      // Wait a moment then show result
      setTimeout(() => {
        document.getElementById('loadingOverlay').classList.remove('show');

        const resultImg = document.getElementById('resultImg');
        resultImg.src = data.result;
        resultImg.style.display = 'block';
        document.getElementById('p3PlaceholderFrame').style.display = 'none';

        // Store the result for download
        uploadedImageData = data.result;

        goToPage(3);
      }, 500);
    } else {
      // Show error
      document.getElementById('loadingOverlay').classList.remove('show');
      alert('Error: ' + (data.error || 'Face swap failed'));
      
      // Reset step indicators
      document.getElementById('sc1').classList.add('active');
      document.getElementById('sc1').classList.remove('done');
      document.getElementById('sl1').classList.remove('done');
      document.getElementById('sc2').classList.remove('active');
    }
  })
  .catch(error => {
    document.getElementById('loadingOverlay').classList.remove('show');
    alert('Error: ' + error.message);
    
    // Reset step indicators
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

// Helper function to get CSRF token from cookie
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