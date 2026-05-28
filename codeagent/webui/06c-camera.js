/* Real-time camera: getUserMedia preview, single capture + interval frames → attachments */

(function initCameraUi() {
  const cameraBtn = document.getElementById('cameraBtn');
  const nativeInput = document.getElementById('nativeCameraInput');
  const modal = document.getElementById('cameraModal');
  const closeBtn = document.getElementById('cameraModalClose');
  const doneBtn = document.getElementById('cameraModalDone');
  const captureBtn = document.getElementById('cameraCaptureBtn');
  const intervalBtn = document.getElementById('cameraToggleInterval');
  const video = document.getElementById('cameraPreview');
  const canvas = document.getElementById('cameraCanvas');
  const statusEl = document.getElementById('cameraStatus');

  if (!cameraBtn || !modal) return;

  let stream = null;
  let intervalId = null;
  let captureCount = 0;
  const MAX_INTERVAL_CAPTURES = 8;
  const INTERVAL_MS = 3000;

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || '';
  }

  function visionReady() {
    return typeof visionModelReadyForAttachments === 'function' && visionModelReadyForAttachments();
  }

  function stopStream() {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
    if (intervalBtn) {
      intervalBtn.classList.remove('is-active');
      intervalBtn.textContent = '定时截帧';
    }
    if (stream) {
      stream.getTracks().forEach(function(t) { t.stop(); });
      stream = null;
    }
    if (video) video.srcObject = null;
  }

  function closeModal() {
    stopStream();
    captureCount = 0;
    modal.style.display = 'none';
    setStatus('');
  }

  async function captureFrame() {
    if (!video || !canvas || !video.videoWidth) return false;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return false;
    ctx.drawImage(video, 0, 0);
    return new Promise(function(resolve) {
      canvas.toBlob(function(blob) {
        if (!blob) {
          resolve(false);
          return;
        }
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        const file = new File([blob], 'camera-' + ts + '.jpg', { type: 'image/jpeg' });
        if (typeof stageFiles === 'function') {
          stageFiles([file]).then(function() {
            captureCount += 1;
            setStatus('已捕获 ' + captureCount + ' 张');
            resolve(true);
          }).catch(function() { resolve(false); });
        } else {
          resolve(false);
        }
      }, 'image/jpeg', 0.92);
    });
  }

  function toggleIntervalCapture() {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
      if (intervalBtn) {
        intervalBtn.classList.remove('is-active');
        intervalBtn.textContent = '定时截帧';
      }
      setStatus('定时截帧已停止 · 共 ' + captureCount + ' 张');
      return;
    }
    if (intervalBtn) {
      intervalBtn.classList.add('is-active');
      intervalBtn.textContent = '停止截帧';
    }
    setStatus('每 ' + (INTERVAL_MS / 1000) + ' 秒截帧（最多 ' + MAX_INTERVAL_CAPTURES + ' 张）');
    intervalId = setInterval(function() {
      if (captureCount >= MAX_INTERVAL_CAPTURES) {
        toggleIntervalCapture();
        systemMsg('info', '已达截帧上限 ' + MAX_INTERVAL_CAPTURES);
        return;
      }
      captureFrame();
    }, INTERVAL_MS);
  }

  async function openCameraModal() {
    if (!visionReady()) {
      systemMsg('err', '请先选择多模态模型');
      return;
    }
    captureCount = 0;
    modal.style.display = 'flex';
    setStatus('正在打开摄像头…');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus('浏览器不支持摄像头，尝试系统相机…');
      if (nativeInput) nativeInput.click();
      closeModal();
      return;
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      if (video) {
        video.srcObject = stream;
        await video.play().catch(function() {});
      }
      setStatus('对准目标后点击「拍照」，或开启定时截帧');
    } catch (e) {
      setStatus('');
      systemMsg('err', '无法访问摄像头: ' + String(e.message || e));
      if (nativeInput) {
        systemMsg('info', '尝试使用系统相机');
        nativeInput.click();
      }
      closeModal();
    }
  }

  cameraBtn.addEventListener('click', function() {
    openCameraModal();
  });

  captureBtn && captureBtn.addEventListener('click', function() {
    captureFrame();
  });

  intervalBtn && intervalBtn.addEventListener('click', function() {
    toggleIntervalCapture();
  });

  closeBtn && closeBtn.addEventListener('click', closeModal);
  doneBtn && doneBtn.addEventListener('click', closeModal);

  modal.addEventListener('click', function(e) {
    if (e.target === modal) closeModal();
  });

  nativeInput && nativeInput.addEventListener('change', function() {
    if (nativeInput.files && nativeInput.files.length && typeof stageFiles === 'function') {
      stageFiles(Array.from(nativeInput.files));
    }
    nativeInput.value = '';
  });

  document.addEventListener('keydown', function(e) {
    if (modal.style.display === 'none' || modal.style.display === '') return;
    if (e.key === 'Escape') closeModal();
  });

  window.updateCameraButtonGate = function() {
    if (!cameraBtn) return;
    const ready = visionReady();
    cameraBtn.disabled = !ready;
    cameraBtn.title = ready ? '摄像头拍照 / 定时截帧' : '请先选择多模态模型';
  };

  const _origGate = typeof updateAttachmentUiGate === 'function' ? updateAttachmentUiGate : null;
  if (_origGate) {
    updateAttachmentUiGate = function() {
      _origGate();
      window.updateCameraButtonGate();
    };
  }
  window.updateCameraButtonGate();
})();
