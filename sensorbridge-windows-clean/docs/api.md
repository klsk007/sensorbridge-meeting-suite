# SensorBridge Camera API

This build exposes only the camera product path.

## Product

- `GET /api/v1/product/status`
- `POST /api/v1/product/start`
- `GET /api/v1/product/contract`

`/api/v1/product/status` returns the camera status fields:

- `activeCameraTransport`
- `receivedFps`
- `decodedFps`
- `virtualCameraFps`
- `latestFrameAgeMs`
- `estimatedLatencyMs`
- `droppedFrames`
- `normalWindowsCameraVisible`

## WebRTC

- `GET /api/v2/webrtc/status`
- `POST /api/v2/webrtc/connect`
- `POST /api/v2/webrtc/receiver/offer`
- `POST /api/v2/webrtc/receiver/answer`
- `POST /api/v2/webrtc/receiver/ice-candidate`
- `GET /api/v2/webrtc/local-ice-candidates`
- `POST /api/v2/webrtc/receiver-stats`

Receiver stats are camera-only and include receive FPS, decode FPS, virtual camera FPS, latency, frame age, and dropped frame evidence.

## Windows Camera

- `GET /api/camera/provider/status`
- `POST /api/camera/provider/register-start`
- `POST /api/camera/provider/start`
- `POST /api/camera/provider/stop`
- `GET /api/camera/directshow/build-status`
- `GET /api/camera/directshow/register-status`
- `GET /api/camera/directshow/open-status`
- `GET /api/camera/directshow/sender-status`
- `POST /api/camera/directshow/sender/build`
- `POST /api/camera/directshow/sender/start`
- `POST /api/camera/directshow/sender/stop`

## Removed Routes

Removed product routes return:

```json
{
  "ok": false,
  "error": {
    "code": "camera_only_feature_removed",
    "message": "..."
  }
}
```
