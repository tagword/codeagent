/* Real-time camera: getUserMedia preview, single capture + interval frames + MediaRecorder video */

(function initCameraUi() {
  const cameraBtn = document.getElementById('cameraBtn');
  const nativeInput = document.getElementById('nativeCameraInput');
  const modal = document.getElementById('cameraModal');
  const closeBtn = document.getElementById('cameraModalClose');
  const doneBtn = document.getElementById('cameraModalDone');
  const doneBtnVideo = document.getElementById('cameraModalDoneVideo');
  const captureBtn = document.getElementById('cameraCaptureBtn');
  const intervalBtn = document.getElementById('cameraToggleInterval');
  const recordBtn = document.getElementById('cameraRecordBtn');
  const video = document.getElementById('cameraPreview');
  const canvas = document.getElementById('cameraCanvas');
  const statusEl = document.getElementById('cameraStatus');
  const modeBar = document.getElementById('cameraModeBar');
  const footerPhoto = document.getElementById('cameraFooterPhoto');
  const footerVideo = document.getElementById('cameraFooterVideo');
  const modalTitle = document.getElementById('cameraModalTitle');
  const recIndicator = document.getElementById('cameraRecIndicator');
  const recTimer = document.getElementById('cameraRecTimer');

  if (!modal) return;

  // --- State ---
  let stream = null;
  let intervalId = null;
  let captureCount = 0;
  const MAX_INTERVAL_CAPTURES = 8;
  const INTERVAL_MS = 3000;

  // Recording state
  let mediaRecorder = null;
  let recordedBlobs = [];
  let recordStartTs = 0;
  let recordTimerId = null;
  let isRecording = false;
  let currentMode = 'photo'; // 'photo' | 'video'
  // 'user' = front, 'environment' = back
  let currentFacing = 'environment';

  // --- Helpers ---
  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || '';
  }

  function visionReady() {
    return typeof attachmentImageReady === 'function' && attachmentImageReady();
  }

  function videoModelReady() {
    return typeof attachmentVideoReady === 'function' && attachmentVideoReady();
  }

  function stopInterval() {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
    if (intervalBtn) {
      intervalBtn.classList.remove('is-active');
      intervalBtn.textContent = '定时截帧';
    }
  }

  function stopStream() {
    stopInterval();
    stopRecording(false);
    if (stream) {
      stream.getTracks().forEach(function(t) { t.stop(); });
      stream = null;
    }
    if (video) video.srcObject = null;
  }

  function closeModal() {
    stopStream();
    captureCount = 0;
    if (recIndicator) recIndicator.hidden = true;
    if (recordBtn) {
      recordBtn.textContent = '开始录制';
      recordBtn.classList.remove('is-recording');
    }
    modal.style.display = 'none';
    setStatus('');
  }

  // --- Photo capture ---
  async function captureFrame() {
    if (!video || !canvas || !video.videoWidth) {
      systemMsg('err', '摄像头未就绪');
      return false;
    }
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
      stopInterval();
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
        stopInterval();
        if (typeof systemMsg === 'function') systemMsg('info', '已达截帧上限 ' + MAX_INTERVAL_CAPTURES);
        return;
      }
      captureFrame();
    }, INTERVAL_MS);
  }

  // --- Video recording ---
  function pickRecorderMime() {
    const candidates = [
      'video/webm;codecs=vp9',
      'video/webm;codecs=vp8',
      'video/webm',
      'video/mp4',
    ];
    for (let i = 0; i < candidates.length; i++) {
      if (typeof MediaRecorder !== 'undefined' &&
          MediaRecorder.isTypeSupported &&
          MediaRecorder.isTypeSupported(candidates[i])) {
        return candidates[i];
      }
    }
    return '';
  }

  function formatRecordTime(ms) {
    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function startRecording() {
    if (!stream) {
      systemMsg('err', '摄像头未就绪，无法录制');
      return;
    }
    const mime = pickRecorderMime();
    try {
      mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime })
                           : new MediaRecorder(stream);
    } catch (e) {
      systemMsg('err', '当前浏览器不支持视频录制: ' + (e.message || e));
      return;
    }
    recordedBlobs = [];
    mediaRecorder.ondataavailable = function(ev) {
      if (ev.data && ev.data.size > 0) recordedBlobs.push(ev.data);
    };
    mediaRecorder.onstop = function() {
      finalizeRecording();
    };
    mediaRecorder.onerror = function(ev) {
      systemMsg('err', '录制出错: ' + (ev.error && ev.error.name ? ev.error.name : 'unknown'));
    };
    mediaRecorder.start(250); // collect a chunk every 250ms
    isRecording = true;
    recordStartTs = Date.now();
    if (recIndicator) recIndicator.hidden = false;
    if (recTimer) recTimer.textContent = '00:00';
    if (recordBtn) {
      recordBtn.textContent = '停止录制';
      recordBtn.classList.add('is-recording');
    }
    setStatus('正在录制…点击「停止录制」结束');
    recordTimerId = setInterval(function() {
      if (recTimer) recTimer.textContent = formatRecordTime(Date.now() - recordStartTs);
    }, 250);
  }

  function stopRecording(finish) {
    if (recordTimerId) {
      clearInterval(recordTimerId);
      recordTimerId = null;
    }
    if (!isRecording) return;
    isRecording = false;
    if (recIndicator) recIndicator.hidden = true;
    if (recordBtn) {
      recordBtn.textContent = '开始录制';
      recordBtn.classList.remove('is-recording');
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try {
        mediaRecorder.stop();
      } catch (_) {}
    }
    if (!finish) {
      // forced stop without saving (e.g. stream was torn down)
      recordedBlobs = [];
    }
  }

  function finalizeRecording() {
    if (!recordedBlobs.length) {
      setStatus('录制已停止（无数据）');
      return;
    }
    const mime = (mediaRecorder && mediaRecorder.mimeType) || 'video/webm';
    const ext = mime.indexOf('mp4') >= 0 ? 'mp4' : 'webm';
    const blob = new Blob(recordedBlobs, { type: mime });
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const file = new File([blob], 'camera-' + ts + '.' + ext, { type: mime });
    const dur = formatRecordTime(Date.now() - recordStartTs);
    if (typeof stageFiles === 'function') {
      stageFiles([file]).then(function() {
        setStatus('已录制 ' + dur + ' · 已加入附件');
        if (typeof systemMsg === 'function') systemMsg('info', '已附加录像 ' + dur);
      }).catch(function() {
        setStatus('录像已停止，但加入附件失败');
      });
    } else {
      setStatus('录像已停止（无 stageFiles）');
    }
    recordedBlobs = [];
  }

  // --- Stream acquisition ---
  async function tryGetStream(facing) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('浏览器不支持 getUserMedia');
    }
    // 1st try: requested facing
    try {
      return await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: currentMode === 'video',
      });
    } catch (e1) {
      // 2nd try: any camera (desktop usually has front only)
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: currentMode === 'video',
        });
      } catch (e2) {
        // 3rd try: no constraints at all
        try {
          return await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: currentMode === 'video',
          });
        } catch (e3) {
          throw e1; // surface the original error
        }
      }
    }
  }

  async function openStream() {
    if (stream) return stream;
    setStatus('正在打开摄像头…');
    stream = await tryGetStream(currentFacing);
    if (video) {
      video.srcObject = stream;
      video.muted = true;
      try { await video.play(); } catch (_) {}
    }
    return stream;
  }

  // --- Modal open ---
  async function openCameraModal(mode) {
    currentMode = (mode === 'video') ? 'video' : 'photo';
    setModeUi(currentMode);

    if (currentMode === 'photo' && !visionReady()) {
      systemMsg('err', '请先配置识图（多模态 LLM 或 MiniMax MCP）');
      // Fall through anyway — let user test the camera; the staged file would just be ignored by /api/chat
    }
    if (currentMode === 'video' && !videoModelReady()) {
      systemMsg('err', '请先配置视频识图模型');
    }

    captureCount = 0;
    modal.style.display = 'flex';
    setStatus('正在打开摄像头…');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus('当前浏览器不支持实时摄像头，已为你打开系统相机/文件选择器');
      if (nativeInput) nativeInput.click();
      // give the native picker a moment, then close the modal
      setTimeout(function() { try { closeModal(); } catch (_) {} }, 600);
      return;
    }

    try {
      await openStream();
      setStatus(currentMode === 'video'
        ? '点击「开始录制」开始录像'
        : '对准目标后点击「拍照」，或开启定时截帧');
    } catch (e) {
      const msg = (e && (e.name || e.message)) ? (e.name + ': ' + (e.message || '')) : String(e);
      setStatus('无法访问摄像头：' + msg + ' — 回退到系统相机/文件选择器');
      if (typeof systemMsg === 'function') {
        systemMsg('err', '无法访问摄像头，已回退到系统相机/文件选择器');
      }
      if (nativeInput) {
        try { nativeInput.click(); } catch (_) {}
      }
      setTimeout(function() { try { closeModal(); } catch (_) {} }, 600);
    }
  }

  function setModeUi(mode) {
    currentMode = mode;
    if (modeBar) {
      Array.from(modeBar.querySelectorAll('.camera-modal__mode-btn')).forEach(function(btn) {
        const isActive = btn.getAttribute('data-mode') === mode;
        btn.classList.toggle('is-active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
    }
    if (footerPhoto) footerPhoto.hidden = (mode !== 'photo');
    if (footerVideo) footerVideo.hidden = (mode !== 'video');
    if (modalTitle) modalTitle.textContent = (mode === 'video') ? '录像' : '拍照';
  }

  // --- Expose to popup ---
  window.openCameraModal = openCameraModal;

  // --- Bindings ---
  captureBtn && captureBtn.addEventListener('click', function() { captureFrame(); });
  intervalBtn && intervalBtn.addEventListener('click', function() { toggleIntervalCapture(); });

  recordBtn && recordBtn.addEventListener('click', function() {
    if (isRecording) stopRecording(true);
    else startRecording();
  });

  // Mode switch
  if (modeBar) {
    modeBar.addEventListener('click', function(e) {
      const btn = e.target.closest('.camera-modal__mode-btn');
      if (!btn) return;
      const m = btn.getAttribute('data-mode');
      if (!m || m === currentMode) return;
      // Stop any in-flight recording before switching
      if (isRecording) stopRecording(true);
      setModeUi(m);
      setStatus(m === 'video' ? '点击「开始录制」开始录像' : '对准目标后点击「拍照」');
    });
  }

  closeBtn && closeBtn.addEventListener('click', closeModal);
  doneBtn && doneBtn.addEventListener('click', closeModal);
  doneBtnVideo && doneBtnVideo.addEventListener('click', closeModal);

  modal.addEventListener('click', function(e) {
    if (e.target === modal) closeModal();
  });

  document.addEventListener('keydown', function(e) {
    if (modal.style.display === 'none' || modal.style.display === '') return;
    if (e.key === 'Escape') closeModal();
  });
})();
