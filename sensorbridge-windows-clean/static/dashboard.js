const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8765" : "";

const connectionStatusEl = document.querySelector("#connectionStatus");
const previewStatusEl = document.querySelector("#previewStatus");
const cameraPreviewEl = document.querySelector("#cameraPreview");
const capturePhotoEl = document.querySelector("#capturePhoto");
const refreshPreviewEl = document.querySelector("#refreshPreview");
const photoSaveStatusEl = document.querySelector("#photoSaveStatus");
const upstreamBaseUrlEl = document.querySelector("#upstreamBaseUrl");
const saveUpstreamEl = document.querySelector("#saveUpstream");
const checkUpstreamEl = document.querySelector("#checkUpstream");
const startProductModeEl = document.querySelector("#startProductMode");
const productOverallStatusEl = document.querySelector("#productOverallStatus");
const activeCameraTransportEl = document.querySelector("#activeCameraTransport");
const productCameraStatusEl = document.querySelector("#productCameraStatus");
const normalWindowsCameraVisibleEl = document.querySelector("#normalWindowsCameraVisible");
const productBlockersStatusEl = document.querySelector("#productBlockersStatus");
const webrtcCompleteStatusEl = document.querySelector("#webrtcCompleteStatus");
const webrtcRuntimeStatusEl = document.querySelector("#webrtcRuntimeStatus");
const webrtcSignalingStatusEl = document.querySelector("#webrtcSignalingStatus");
const webrtcIceStatusEl = document.querySelector("#webrtcIceStatus");
const receivedFpsEl = document.querySelector("#receivedFps");
const decodedFpsEl = document.querySelector("#decodedFps");
const virtualCameraFpsEl = document.querySelector("#virtualCameraFps");
const latestFrameAgeMsEl = document.querySelector("#latestFrameAgeMs");
const estimatedLatencyMsEl = document.querySelector("#estimatedLatencyMs");
const droppedFramesEl = document.querySelector("#droppedFrames");
const webrtcFallbackStatusEl = document.querySelector("#webrtcFallbackStatus");
const virtualCameraStatusEl = document.querySelector("#virtualCameraStatus");
const registerCameraProviderEl = document.querySelector("#registerCameraProvider");
const startCameraProviderEl = document.querySelector("#startCameraProvider");
const stopCameraProviderEl = document.querySelector("#stopCameraProvider");
const cameraProviderStatusEl = document.querySelector("#cameraProviderStatus");
const windowsAppCameraStatusEl = document.querySelector("#windowsAppCameraStatus");
const cameraSinkStatusEl = document.querySelector("#cameraSinkStatus");
const systemDeviceNoteEl = document.querySelector("#systemDeviceNote");

function setText(element, value) {
  if (element) {
    element.textContent = value === undefined || value === null || value === "" ? "-" : String(value);
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error?.message || `Request failed: ${response.status}`);
  }
  return payload;
}

function boolText(value) {
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  return "-";
}

function renderProductStatus(payload) {
  if (!payload) {
    setText(productOverallStatusEl, "offline");
    return;
  }
  const blockers = Array.isArray(payload.blockers) ? payload.blockers : [];
  setText(productOverallStatusEl, payload.readyForMeeting ? "ready" : blockers.length ? "blocked" : "checking");
  setText(activeCameraTransportEl, payload.activeCameraTransport);
  setText(productCameraStatusEl, payload.virtualCameraReady ? "ready" : payload.cameraProviderReady ? "provider ready" : "checking");
  setText(normalWindowsCameraVisibleEl, boolText(payload.normalWindowsCameraVisible));
  setText(productBlockersStatusEl, blockers.length ? blockers.join(" | ") : "no blockers");
}

function renderWebRTCStatus(payload) {
  if (!payload) {
    setText(webrtcCompleteStatusEl, "offline");
    return;
  }
  setText(webrtcCompleteStatusEl, payload.mediaConnected ? "connected" : payload.transportMode || "checking");
  setText(webrtcRuntimeStatusEl, payload.runtime || payload.receiverState);
  setText(webrtcSignalingStatusEl, payload.signalingState);
  setText(webrtcIceStatusEl, payload.iceConnectionState || payload.iceGatheringState);
  setText(receivedFpsEl, payload.receivedFps);
  setText(decodedFpsEl, payload.decodedFps);
  setText(virtualCameraFpsEl, payload.virtualCameraFps);
  setText(latestFrameAgeMsEl, payload.latestFrameAgeMs);
  setText(estimatedLatencyMsEl, payload.estimatedLatencyMs);
  setText(droppedFramesEl, payload.droppedFrames);
  setText(webrtcFallbackStatusEl, payload.nextAction || payload.receiverState);
}

function renderProviderStatus(payload) {
  if (!payload) {
    setText(virtualCameraStatusEl, "offline");
    return;
  }
  setText(virtualCameraStatusEl, payload.virtualCameraVisible ? "visible" : payload.registered ? "registered" : "not visible");
  setText(cameraProviderStatusEl, payload.providerRunning ? "running" : payload.providerRegistered ? "registered" : "stopped");
  setText(windowsAppCameraStatusEl, boolText(payload.normalWindowsCameraVisible));
  setText(cameraSinkStatusEl, payload.frameSinkReady ? "ready" : payload.latestFrameAgeMs);
  setText(systemDeviceNoteEl, payload.note || payload.nextAction);
}

async function refreshPreview() {
  if (!cameraPreviewEl) {
    return;
  }
  const stamp = Date.now();
  cameraPreviewEl.src = `${API_BASE}/api/camera/preview.jpg?t=${stamp}`;
  setText(previewStatusEl, "refreshing");
}

async function refreshStatus() {
  try {
    const [product, rtc, provider] = await Promise.all([
      fetchJson("/api/v1/product/status"),
      fetchJson("/api/v2/webrtc/status"),
      fetchJson("/api/camera/provider/status"),
    ]);
    setText(connectionStatusEl, "Live");
    renderProductStatus(product);
    renderWebRTCStatus(rtc);
    renderProviderStatus(provider);
  } catch (error) {
    setText(connectionStatusEl, "Offline");
    setText(productBlockersStatusEl, error.message);
  }
}

saveUpstreamEl?.addEventListener("click", async () => {
  try {
    await fetchJson("/api/upstream/config", {
      method: "POST",
      body: JSON.stringify({ base_url: upstreamBaseUrlEl?.value || "" }),
    });
    await refreshStatus();
  } catch (error) {
    setText(productBlockersStatusEl, error.message);
  }
});

checkUpstreamEl?.addEventListener("click", async () => {
  try {
    const payload = await fetchJson("/api/upstream/check", { method: "POST", body: "{}" });
    setText(productBlockersStatusEl, payload?.upstream?.connected ? "connected" : payload?.upstream?.last_error?.message);
  } catch (error) {
    setText(productBlockersStatusEl, error.message);
  }
});

startProductModeEl?.addEventListener("click", async () => {
  startProductModeEl.disabled = true;
  try {
    const payload = await fetchJson("/api/v1/product/start", { method: "POST", body: "{}" });
    renderProductStatus(payload.product_status || payload);
    await refreshStatus();
  } catch (error) {
    setText(productBlockersStatusEl, error.message);
  } finally {
    startProductModeEl.disabled = false;
  }
});

registerCameraProviderEl?.addEventListener("click", async () => {
  renderProviderStatus(await fetchJson("/api/camera/provider/register-start", { method: "POST", body: "{}" }));
});

startCameraProviderEl?.addEventListener("click", async () => {
  renderProviderStatus(await fetchJson("/api/camera/provider/start", { method: "POST", body: "{}" }));
});

stopCameraProviderEl?.addEventListener("click", async () => {
  renderProviderStatus(await fetchJson("/api/camera/provider/stop", { method: "POST", body: "{}" }));
});

refreshPreviewEl?.addEventListener("click", refreshPreview);

capturePhotoEl?.addEventListener("click", async () => {
  try {
    const payload = await fetchJson("/api/camera/capture-photo", { method: "POST", body: "{}" });
    setText(photoSaveStatusEl, payload.path || "saved");
  } catch (error) {
    setText(photoSaveStatusEl, error.message);
  }
});

cameraPreviewEl?.addEventListener("load", () => setText(previewStatusEl, "live"));
cameraPreviewEl?.addEventListener("error", () => setText(previewStatusEl, "waiting"));

refreshPreview();
refreshStatus();
setInterval(refreshStatus, 2000);
