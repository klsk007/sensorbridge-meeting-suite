# WebRTC Windows Receiver

The Windows receiver uses optional `aiortc` support when available. It creates a receive-only video offer, prefers H.264, applies the iPad answer and ICE candidates, and writes decoded video frames to the virtual camera sink.

The receiver reports:

- `activeCameraTransport`
- `receivedFps`
- `decodedFps`
- `virtualCameraFps`
- `latestFrameAgeMs`
- `estimatedLatencyMs`
- `droppedFrames`
- `normalWindowsCameraVisible`

If `aiortc` is missing or signaling fails, the camera is unavailable. The product path does not switch to HTTP frame polling.
