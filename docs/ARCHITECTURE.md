# Architecture

SensorBridge Meeting Suite is a Windows virtual-device bridge for meeting software. The mobile device contributes media; Windows exposes the meeting-facing devices.

## Device Roles

| Meeting role | Windows-facing device | Source or sink | Current component |
| --- | --- | --- | --- |
| Camera | `SensorBridge Camera` | iPhone/iPad camera over WebRTC/H.264 | `sensorbridge-windows-clean` |
| Microphone | `Cable Microphone` (usually shown as `CABLE Output`) | iPhone/iPad microphone over WebRTC/Opus, written to the selected playback endpoint, usually `CABLE Input` | `sensorbridge-microphone-windows` |
| Speaker | `Cable Speaker` (usually shown as `CABLE Input`) | Captured from the selected recording endpoint, usually `CABLE Output`, and sent to iPhone/iPad speaker over WebRTC/Opus | `sensorbridge-speaker-windows` |

## Why Windows Owns the Virtual Devices

Meeting apps enumerate local operating-system capture and render endpoints. On Windows, camera exposure can be implemented through Media Foundation virtual camera APIs or DirectShow-style virtual camera paths, and audio routing can be provided by virtual audio endpoints such as VB-CABLE or a custom driver.

iOS/iPadOS apps can capture camera and microphone media inside their own sandbox, but they do not become arbitrary system-wide Windows devices. The bridge therefore has two halves:

- Mobile app: capture, encode, send, receive, play.
- Windows app: receive, decode, route into meeting-selectable devices.

## One-Cable Versus Two-Cable Audio

The safe development route uses VB-CABLE because it gives ordinary Windows apps a selectable input/output pair.

For full-duplex meeting use, two independent virtual cables are preferable:

- Cable A: iPhone/iPad microphone -> meeting microphone.
- Cable B: meeting speaker output -> iPhone/iPad speaker.

Using one cable for both directions is useful for development and can work with
the WebRTC microphone plus WebRTC speaker route. For the cleanest full-duplex
meeting setup, two independent virtual cables are still preferable: one route
for microphone injection and another route for speaker return.

## Echo Boundary

Windows routing does not by itself solve acoustic echo. Echo control belongs near the physical capture/playback path. The iPhone/iPad side should use a voice-processing audio session when the same mobile device plays meeting audio and captures microphone audio.
