# Architecture

SensorBridge Windows is camera-only.

```text
iPad Camera
  -> WebRTC/H.264 low-latency transport
  -> Windows receiver/decoder
  -> newest-frame-wins decoded frame queue
  -> Windows virtual camera provider/sender
  -> Windows Camera or meeting software
```

The decoded frame queue is bounded to one frame. If the virtual camera sink is slower than the decoder, the old queued frame is dropped and the newest frame wins.

Product Mode starts the WebRTC receiver and Windows virtual camera sender. It does not start HTTP frame polling.
