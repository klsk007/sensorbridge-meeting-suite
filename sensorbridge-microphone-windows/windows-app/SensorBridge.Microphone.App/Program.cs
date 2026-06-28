using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Management;
using System.Media;
using System.Net;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using System.Web.Script.Serialization;

namespace SensorBridge.Microphone.App
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            bool createdNew;
            using (Mutex mutex = new Mutex(true, "SensorBridge.Microphone.App.SingleInstance", out createdNew))
            {
                if (!createdNew)
                {
                    MessageBox.Show("SensorBridge Microphone is already running.", "SensorBridge Microphone", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new MainForm(AppOptions.Parse(args)));
            }
        }
    }

    internal sealed class AppOptions
    {
        public string ProjectRoot = ResolveDefaultProjectRoot();
        public string BaseUrl = "http://192.168.0.24:27180";
        public string RelayUrl = "http://192.168.0.23:27181";
        public string OutputDevice = "CABLE Input";
        public string Language = ResolveDefaultLanguage();
        public string MicGain = "1.0";
        public string MonitorGain = "4.0";
        public string NoiseGate = "0.0";
        public string PlaybackPrebufferMs = "1500";
        public int Frames = 5;

        public static AppOptions Parse(string[] args)
        {
            AppOptions options = new AppOptions();
            for (int i = 0; i < args.Length; i++)
            {
                string value = i + 1 < args.Length ? args[i + 1] : "";
                if (args[i] == "--project-root" && value.Length > 0)
                {
                    options.ProjectRoot = Path.GetFullPath(value);
                    i++;
                }
                else if (args[i] == "--base-url" && value.Length > 0)
                {
                    options.BaseUrl = value;
                    i++;
                }
                else if (args[i] == "--relay-url" && value.Length > 0)
                {
                    options.RelayUrl = value;
                    i++;
                }
                else if (args[i] == "--frames" && value.Length > 0)
                {
                    int parsed;
                    if (Int32.TryParse(value, out parsed))
                    {
                        options.Frames = Math.Max(1, parsed);
                    }
                    i++;
                }
                else if (args[i] == "--output-device" && value.Length > 0)
                {
                    options.OutputDevice = value;
                    i++;
                }
                else if (args[i] == "--language" && value.Length > 0)
                {
                    options.Language = value.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh-CN" : "en-US";
                    i++;
                }
                else if (args[i] == "--mic-gain" && value.Length > 0)
                {
                    options.MicGain = value;
                    i++;
                }
                else if (args[i] == "--monitor-gain" && value.Length > 0)
                {
                    options.MonitorGain = value;
                    i++;
                }
                else if (args[i] == "--noise-gate" && value.Length > 0)
                {
                    options.NoiseGate = value;
                    i++;
                }
                else if (args[i] == "--playback-prebuffer-ms" && value.Length > 0)
                {
                    options.PlaybackPrebufferMs = value;
                    i++;
                }
            }
            return options;
        }

        private static string ResolveDefaultLanguage()
        {
            string name = CultureInfo.CurrentUICulture.Name;
            return name.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh-CN" : "en-US";
        }

        private static string ResolveDefaultProjectRoot()
        {
            string current = AppDomain.CurrentDomain.BaseDirectory;
            for (int depth = 0; depth < 8 && !String.IsNullOrEmpty(current); depth++)
            {
                if (File.Exists(Path.Combine(current, "bridge.py")) &&
                    Directory.Exists(Path.Combine(current, "bridgeclient")))
                {
                    return Path.GetFullPath(current);
                }
                DirectoryInfo parent = Directory.GetParent(current);
                if (parent == null)
                {
                    break;
                }
                current = parent.FullName;
            }
            return Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", ".."));
        }
    }

    internal static class LocalizedText
    {
        private static readonly Dictionary<string, string> En = new Dictionary<string, string>
        {
            {"appTitle", "SensorBridge Microphone"},
            {"subtitle", "WebRTC/Opus iPad microphone to VB-CABLE, with honest status"},
            {"baseUrl", "Base URL"},
            {"output", "Output"},
            {"message", "Message"},
            {"language", "Language"},
            {"start", "Start"},
            {"stop", "Stop"},
            {"refresh", "Refresh"},
            {"testCable", "Test Cable"},
            {"qualityCheck", "Quality check"},
            {"tuneGain", "Tune"},
            {"micGain", "Mic gain"},
            {"listenGain", "Listen gain"},
            {"noiseGate", "Gate"},
            {"prebuffer", "Prebuffer"},
            {"useRecommended", "Use"},
            {"seconds", "sec"},
            {"record", "Record"},
            {"stopRecording", "Stop recording"},
            {"play", "Play"},
            {"recordHint", "Listen gain only affects playback WAV, not Tencent Meeting."},
            {"backend", "Backend"},
            {"ipadUpstream", "iPad upstream"},
            {"windowsReceiver", "Windows receiver"},
            {"inputLevel", "input"},
            {"outputLevel", "output"},
            {"buffer", "Buffer"},
            {"vbcable", "VB-CABLE"},
            {"tencentMeeting", "Tencent Meeting"},
            {"trayOpen", "Open"},
            {"trayRecord", "Record sample"},
            {"trayPlay", "Play sample"},
            {"trayTune", "Tune gain"},
            {"trayOpenCaptures", "Open diagnostics folder"},
            {"trayBundleDiagnostics", "Bundle diagnostics"},
            {"trayExit", "Exit"},
            {"statusNotStarted", "not started"},
            {"statusStarting", "starting WebRTC..."},
            {"statusRefreshing", "refreshing..."},
            {"statusFailed", "failed"},
            {"statusTestingCable", "testing cable..."},
            {"statusTestFailed", "test failed"},
            {"statusStreaming", "webrtc streaming"},
            {"statusStopped", "stopped"},
            {"restartToApply", "restart to apply"},
            {"statusRecording", "recording sample..."},
            {"statusPreparingRecord", "preparing audio route..."},
            {"statusRecordFailed", "record failed"},
            {"statusNoRecording", "no recording"},
            {"statusPlaying", "playing sample"},
            {"statusTuningGain", "tuning gain..."},
            {"statusBundlingDiagnostics", "bundling diagnostics..."},
            {"statusDiagnosticBundleReady", "diagnostic bundle ready"},
            {"statusTuneFailed", "gain tune failed"},
            {"backendSwitched", "Backend switched to relay: {0}"},
            {"backendSelectionReason", "Backend reason"},
            {"statusPlayFailed", "play failed"},
            {"statusRecorded", "recorded sample"},
            {"statusRecordPending", "record pending"},
            {"statusWebrtcOk", "webrtc ok"},
            {"statusReachable", "reachable"},
            {"statusWebrtcPending", "webrtc pending"},
            {"statusNotReady", "not ready"},
            {"idleDetails", "Install VB-CABLE manually, then press Start. Start uses WebRTC/Opus; Test Cable keeps the legacy diagnostic route."},
            {"startDetails", "Receiving iPad microphone over WebRTC/Opus and writing to VB-CABLE. Select CABLE Output as the microphone in Tencent Meeting."},
            {"recordDetails", "Recording CABLE Output now. Press Stop recording when you are done."},
            {"preparingRecordDetails", "Starting WebRTC and waiting until CABLE Output is actually receiving audio. Start speaking after this changes to recording."},
            {"recordNotReadyDetails", "Recording has started, but the WebRTC receiver was not confirmed fresh yet. If the first words are missing, wait for the recording state before speaking."},
            {"stoppingRecord", "Stopping recording, capturing delayed audio tail, and writing WAV files..."},
            {"noRecordingDetails", "No recording is available yet. Press Record first."},
            {"playingDetails", "Playing recording:\r\n{0}\r\n\r\nRaw capture:\r\n{1}"},
            {"gainTuneDetails", "Gain tune recommended Mic gain {0}. Review the per-gain results below, then restart Start if the bridge is already running."},
            {"gainTuneNoRecommendation", "Gain tune did not find a usable setting. Check iPad source level and CABLE route."},
            {"diagnosticBundleDetails", "Diagnostic bundle:\r\n{0}\r\n\r\nFiles included: {1}"},
            {"realPcm", "real PCM received"},
            {"noRealPcm", "no verified real PCM"},
            {"unavailable", "unavailable"},
            {"cableInputMissing", "CABLE Input missing"},
            {"cableOutputActive", "CABLE Output active"},
            {"selectCableOutput", "select CABLE Output"},
            {"cableOutputMissing", "CABLE Output missing"},
            {"meetingAudioVerified", "meeting audio verified"},
            {"meetingQualityReady", "meeting quality ready"},
            {"meetingQualityNeedsTuning", "meeting quality needs tuning"},
            {"meetingEchoRisk", "meeting route ready / echo risk"},
            {"meetingLoopbackTooQuiet", "meeting capture too quiet"},
            {"meetingAudioUnverified", "meeting audio unverified"},
            {"meetingNoLoopbackAudio", "no CABLE Output audio"},
            {"cableOutputCapture", "CABLE Output capture"},
            {"recordedNonSilence", "recorded non-silence"},
            {"recordedTooQuiet", "recorded too quiet"},
            {"silent", "silent"},
            {"rawWav", "Raw WAV"},
            {"playbackWav", "Playback WAV"},
            {"monitorClipping", "monitor clipping"},
            {"monitorClippedWarning", "Playback WAV is clipped by Listen gain. Lower Listen gain and record again before judging quality."},
            {"peak", " peak / RMS "},
            {"clip", " clipped "},
            {"limited", " limited "},
            {"underflows", " underflows "},
            {"underflowRatio", " ratio "},
            {"frameRatio", " frame ratio "},
            {"drops", " drops "},
            {"overflow", " overflow "},
            {"catchup", " catch-up "},
            {"packets", " pkts / "},
            {"frames", " frames"},
            {"milliseconds", " ms"},
            {"qualityFullReady", "full quality ready"},
            {"qualityWindowsReady", "Windows route ready"},
            {"qualityWindowsReadyAecRisk", "Windows route ready / echo risk"},
            {"qualitySourceTooQuiet", "source too quiet"},
            {"qualitySilent", "no microphone level"},
            {"qualityLevelTooHot", "level too hot"},
            {"qualityContinuityUnstable", "continuity unstable"},
            {"qualityLimiterActive", "limiter active"},
            {"qualityHighLatency", "high latency"},
            {"qualityAecUnverified", "AEC unverified"},
            {"qualityNeedsTuning", "quality needs tuning"},
            {"qualityStatus", "Quality"},
            {"readiness", "Readiness"},
            {"nextAction", "Next"},
            {"nextActionFixIpad", "fix iPad source"},
            {"nextActionFixLoopback", "fix meeting level"},
            {"nextActionLowerGain", "lower Windows gain"},
            {"nextActionRaiseGain", "raise gain modestly"},
            {"nextActionVerifyRoute", "verify CABLE route"},
            {"nextActionCheckTransport", "check WebRTC transport"},
            {"nextActionStabilize", "stabilize buffer"},
            {"nextActionVerifyAec", "verify AEC"},
            {"nextActionReady", "ready / monitor"},
            {"diagnosticCaptures", "Diagnostic captures"},
            {"latestDiagnosticJson", "Latest diagnostic JSON"},
            {"latestDiagnosticSummary", "Latest diagnostic summary"},
            {"latestDiagnosticText", "Latest diagnostic text"},
            {"layeredAttribution", "Layer diagnosis"},
            {"receiverRaw", "WebRTC raw"},
            {"processed", "processed"},
            {"cableOutput", "CABLE Output"},
            {"file", "file"},
            {"attributionIpadQuiet", "iPad source too quiet"},
            {"attributionIpadSilent", "iPad/WebRTC silent"},
            {"attributionWindowsHot", "Windows processing too hot"},
            {"attributionWindowsLoss", "Windows processing loss"},
            {"attributionCableSilent", "CABLE Output silent"},
            {"attributionCableLoss", "CABLE Output loss"},
            {"attributionRouteLow", "route level too low"},
            {"attributionRouteOk", "audio level route OK"},
            {"readinessFullQuality", "full quality ready"},
            {"readinessWindowsQuality", "Windows quality ready"},
            {"readinessRouteOnly", "route ready / quality not ready"},
            {"readinessTransportOnly", "transport ready / route unverified"},
            {"readinessNotReady", "not ready"},
            {"primaryIssue", "primary issue"},
            {"primaryRecommendation", "primary recommendation"},
            {"levelState", "level"},
            {"continuityState", "continuity"},
            {"latencyState", "latency"},
            {"aecState", "AEC"},
            {"lowCut", "low cut"},
            {"gateGain", "gain"},
            {"recommendedGain", "recommended gain"},
            {"safeGain", "safe gain"},
            {"gainActionHoldSource", "hold gain / fix iPad source first"},
            {"gainActionRaise", "raise modestly"},
            {"gainActionLower", "lower gain"},
            {"gainActionKeep", "keep gain"},
            {"recommendedListenGain", "recommended listen gain"},
            {"recommendedPrebuffer", "recommended prebuffer"},
            {"gainRisk", "gain risk"},
            {"gainRiskNoise", "gain will mostly amplify noise/echo"},
            {"sourceLift", "source lift"},
            {"approximately", "about "},
            {"nextGain", "next"},
            {"listenNext", "listen"},
            {"recommendations", "Recommendations"},
            {"stateOk", "ok"},
            {"stateLow", "low"},
            {"stateSilent", "silent"},
            {"stateTooHot", "too hot"},
            {"stateDropping", "dropping"},
            {"stateUnderflowing", "underflowing"},
            {"stateHighLatency", "high latency"},
            {"stateBuffered", "buffered"},
            {"stateLowLatency", "low latency"},
            {"stateVerified", "verified"},
            {"stateDisabled", "disabled"},
            {"stateUnverified", "unverified"},
            {"recRaiseGain", "Microphone level is low. Move the iPad closer first; only raise Mic gain modestly."},
            {"recMoveCloser", "The source level is too low for Windows gain alone. Move the iPad closer before raising Mic gain further."},
            {"recCheckIpadMic", "Check that the iPad microphone is active and close enough to your voice."},
            {"recLowerGain", "Microphone is near clipping. Lower Mic gain until clipped samples stay at 0."},
            {"recContinuity", "Audio continuity is unstable. Close other audio-heavy apps or restart the bridge if underflows/drops keep rising."},
            {"recLatency", "Audio is stable but delayed. After stability is confirmed, test a lower playback prebuffer."},
            {"recGate", "Noise gate is active too often. Lower Gate or set it to 0 if quiet words are cut off."},
            {"recLimiter", "Soft limiter is active. Lower Mic gain if speech still sounds compressed or harsh."},
            {"recHeadset", "For Tencent Meeting, use headphones or keep the iPad speaker off until AEC is verified."},
            {"recMeetingVerify", "Run Test Cable or Record before Tencent Meeting to verify CABLE Output audio."},
            {"recMeetingNoAudio", "CABLE Output was silent in loopback; check VB-CABLE selection and restart the bridge."},
            {"recMeetingLoopbackTooQuiet", "Tencent Meeting capture is too quiet. Improve iPad-side source level before adding Windows gain."},
            {"recAec", "Echo still needs iPad-side voice processing/AEC; Windows gain and VB-CABLE cannot remove acoustic echo."}
        };

        private static readonly Dictionary<string, string> Zh = new Dictionary<string, string>
        {
            {"appTitle", "SensorBridge 麦克风"},
            {"subtitle", "通过 WebRTC/Opus 接收 iPad 麦克风并写入 VB-CABLE，显示真实状态"},
            {"baseUrl", "后端地址"},
            {"output", "写入设备"},
            {"message", "消息"},
            {"language", "语言"},
            {"start", "启动"},
            {"stop", "停止"},
            {"refresh", "刷新"},
            {"testCable", "检测线路"},
            {"qualityCheck", "音质检查"},
            {"tuneGain", "调优"},
            {"micGain", "麦克风增益"},
            {"listenGain", "试听增益"},
            {"noiseGate", "噪声门"},
            {"prebuffer", "\u9884\u7f13\u51b2"},
            {"useRecommended", "\u4f7f\u7528"},
            {"seconds", "秒"},
            {"record", "录音"},
            {"stopRecording", "停止录音"},
            {"play", "播放"},
            {"recordHint", "试听增益只影响播放 WAV，不影响腾讯会议。"},
            {"backend", "后端"},
            {"ipadUpstream", "iPad 上行"},
            {"windowsReceiver", "Windows 接收"},
            {"inputLevel", "输入"},
            {"outputLevel", "输出"},
            {"buffer", "缓冲"},
            {"vbcable", "VB-CABLE"},
            {"tencentMeeting", "腾讯会议"},
            {"trayOpen", "打开"},
            {"trayRecord", "录制样本"},
            {"trayPlay", "播放样本"},
            {"trayTune", "调优增益"},
            {"trayOpenCaptures", "打开诊断文件夹"},
            {"trayBundleDiagnostics", "打包诊断"},
            {"trayExit", "退出"},
            {"statusNotStarted", "未启动"},
            {"statusStarting", "正在启动 WebRTC..."},
            {"statusRefreshing", "正在刷新..."},
            {"statusFailed", "失败"},
            {"statusTestingCable", "正在检测线路..."},
            {"statusTestFailed", "检测失败"},
            {"statusStreaming", "WebRTC 传输中"},
            {"statusStopped", "已停止"},
            {"restartToApply", "重启后生效"},
            {"statusRecording", "正在录音..."},
            {"statusPreparingRecord", "正在准备音频链路..."},
            {"statusRecordFailed", "录音失败"},
            {"statusNoRecording", "没有录音"},
            {"statusPlaying", "正在播放样本"},
            {"statusTuningGain", "正在调优增益..."},
            {"statusBundlingDiagnostics", "正在打包诊断..."},
            {"statusDiagnosticBundleReady", "诊断包已生成"},
            {"statusTuneFailed", "增益调优失败"},
            {"backendSwitched", "后端已切换到 relay：{0}"},
            {"backendSelectionReason", "后端原因"},
            {"statusPlayFailed", "播放失败"},
            {"statusRecorded", "已录制样本"},
            {"statusRecordPending", "录音未就绪"},
            {"statusWebrtcOk", "WebRTC 正常"},
            {"statusReachable", "已连接"},
            {"statusWebrtcPending", "WebRTC 等待中"},
            {"statusNotReady", "未就绪"},
            {"idleDetails", "请先手动安装 VB-CABLE，然后点击启动。启动使用 WebRTC/Opus；检测线路保留旧的诊断路径。"},
            {"startDetails", "正在通过 WebRTC/Opus 接收 iPad 麦克风并写入 VB-CABLE。腾讯会议里请选择 CABLE Output 作为麦克风。"},
            {"recordDetails", "正在从 CABLE Output 录音。完成后请点击停止录音。"},
            {"preparingRecordDetails", "正在启动 WebRTC 并等待 CABLE Output 真正收到音频。状态变成正在录音后再开始说话。"},
            {"recordNotReadyDetails", "已开始录音，但 WebRTC 接收状态还没有确认 fresh。如果开头语句丢失，请等状态变成正在录音后再说话。"},
            {"stoppingRecord", "正在停止录音、收取延迟尾音，并写入 WAV 文件..."},
            {"noRecordingDetails", "还没有可播放的录音。请先点击录音。"},
            {"playingDetails", "正在播放录音：\r\n{0}\r\n\r\n原始录音：\r\n{1}"},
            {"gainTuneDetails", "增益调优建议 Mic gain {0}。请查看下面每档结果；如果桥接已经在运行，需要重启 Start 后生效。"},
            {"gainTuneNoRecommendation", "增益调优没有找到可用设置。请检查 iPad 源头音量和 CABLE 链路。"},
            {"diagnosticBundleDetails", "诊断包：\r\n{0}\r\n\r\n包含文件数：{1}"},
            {"realPcm", "收到真实 PCM"},
            {"noRealPcm", "未确认真实 PCM"},
            {"unavailable", "不可用"},
            {"cableInputMissing", "缺少 CABLE Input"},
            {"cableOutputActive", "CABLE Output 有声音"},
            {"selectCableOutput", "请选择 CABLE Output"},
            {"cableOutputMissing", "缺少 CABLE Output"},
            {"meetingAudioVerified", "\u4f1a\u8bae\u97f3\u9891\u5df2\u9a8c\u8bc1"},
            {"meetingQualityReady", "会议音质已就绪"},
            {"meetingQualityNeedsTuning", "会议音质需要调整"},
            {"meetingEchoRisk", "会议链路可用 / 回声风险"},
            {"meetingLoopbackTooQuiet", "会议录音太小"},
            {"meetingAudioUnverified", "\u4f1a\u8bae\u97f3\u9891\u672a\u9a8c\u8bc1"},
            {"meetingNoLoopbackAudio", "\u672a\u68c0\u6d4b\u5230 CABLE Output \u58f0\u97f3"},
            {"cableOutputCapture", "CABLE Output 录音"},
            {"recordedNonSilence", "录到非静音"},
            {"recordedTooQuiet", "录音太小"},
            {"silent", "静音"},
            {"rawWav", "原始 WAV"},
            {"playbackWav", "播放 WAV"},
            {"monitorClipping", "监听削波"},
            {"monitorClippedWarning", "播放 WAV 被试听增益放大到削波。请降低试听增益并重新录音后再判断音质。"},
            {"peak", " 峰值 / RMS "},
            {"clip", " 削波 "},
            {"limited", " 限幅 "},
            {"underflows", " 欠载 "},
            {"underflowRatio", " 比例 "},
            {"frameRatio", " 帧比例 "},
            {"drops", " 丢帧 "},
            {"overflow", " 溢出 "},
            {"catchup", " 追赶 "},
            {"packets", " 包 / "},
            {"frames", " 帧"},
            {"milliseconds", " 毫秒"},
            {"qualityFullReady", "完整音质就绪"},
            {"qualityWindowsReady", "Windows 链路就绪"},
            {"qualityWindowsReadyAecRisk", "Windows \u94fe\u8def\u53ef\u7528 / \u56de\u58f0\u98ce\u9669"},
            {"qualitySourceTooQuiet", "源头声音太小"},
            {"qualitySilent", "没有麦克风电平"},
            {"qualityLevelTooHot", "电平过载"},
            {"qualityContinuityUnstable", "连续性不稳"},
            {"qualityLimiterActive", "限幅器介入"},
            {"qualityHighLatency", "延迟偏高"},
            {"qualityAecUnverified", "回声消除未验证"},
            {"qualityNeedsTuning", "音质需要调整"},
            {"qualityStatus", "音质"},
            {"readiness", "就绪状态"},
            {"nextAction", "下一步"},
            {"nextActionFixIpad", "改善 iPad 源头"},
            {"nextActionFixLoopback", "改善会议音量"},
            {"nextActionLowerGain", "降低 Windows 增益"},
            {"nextActionRaiseGain", "小幅提高增益"},
            {"nextActionVerifyRoute", "验证 CABLE 链路"},
            {"nextActionCheckTransport", "检查 WebRTC 传输"},
            {"nextActionStabilize", "稳定缓冲"},
            {"nextActionVerifyAec", "验证回声消除"},
            {"nextActionReady", "可用 / 继续观察"},
            {"diagnosticCaptures", "分层录音"},
            {"latestDiagnosticJson", "最新诊断 JSON"},
            {"latestDiagnosticSummary", "最新诊断摘要"},
            {"latestDiagnosticText", "最新诊断文本"},
            {"layeredAttribution", "分层判断"},
            {"receiverRaw", "WebRTC 原始"},
            {"processed", "处理后"},
            {"cableOutput", "CABLE Output"},
            {"file", "文件"},
            {"attributionIpadQuiet", "iPad 源头太小"},
            {"attributionIpadSilent", "iPad/WebRTC 静音"},
            {"attributionWindowsHot", "Windows 处理过载"},
            {"attributionWindowsLoss", "Windows 处理损失"},
            {"attributionCableSilent", "CABLE Output 静音"},
            {"attributionCableLoss", "CABLE Output 损失"},
            {"attributionRouteLow", "链路音量太低"},
            {"attributionRouteOk", "音频链路音量正常"},
            {"readinessFullQuality", "完整音质就绪"},
            {"readinessWindowsQuality", "Windows 音质就绪"},
            {"readinessRouteOnly", "链路可用 / 音质未就绪"},
            {"readinessTransportOnly", "传输可用 / 链路未验证"},
            {"readinessNotReady", "未就绪"},
            {"primaryIssue", "主要问题"},
            {"primaryRecommendation", "主要建议"},
            {"levelState", "电平"},
            {"continuityState", "连续性"},
            {"latencyState", "\u5ef6\u8fdf"},
            {"aecState", "回声消除"},
            {"lowCut", "低切"},
            {"gateGain", "增益"},
            {"recommendedGain", "建议增益"},
            {"safeGain", "安全增益"},
            {"gainActionHoldSource", "先别加增益 / 先改善 iPad 源头"},
            {"gainActionRaise", "小幅提高"},
            {"gainActionLower", "降低增益"},
            {"gainActionKeep", "保持增益"},
            {"recommendedListenGain", "建议监听增益"},
            {"recommendedPrebuffer", "\u5efa\u8bae\u9884\u7f13\u51b2"},
            {"gainRisk", "\u589e\u76ca\u98ce\u9669"},
            {"gainRiskNoise", "\u7ee7\u7eed\u589e\u76ca\u4e3b\u8981\u4f1a\u653e\u5927\u566a\u58f0/\u56de\u58f0"},
            {"sourceLift", "\u6e90\u5934\u63d0\u5347"},
            {"approximately", "\u7ea6 "},
            {"nextGain", "下一步"},
            {"listenNext", "试听"},
            {"recommendations", "建议"},
            {"stateOk", "正常"},
            {"stateLow", "偏低"},
            {"stateSilent", "静音"},
            {"stateTooHot", "过载"},
            {"stateDropping", "丢帧"},
            {"stateUnderflowing", "欠载"},
            {"stateHighLatency", "\u9ad8\u5ef6\u8fdf"},
            {"stateBuffered", "\u7f13\u51b2\u4e2d"},
            {"stateLowLatency", "\u4f4e\u5ef6\u8fdf"},
            {"stateVerified", "已验证"},
            {"stateDisabled", "已关闭"},
            {"stateUnverified", "未验证"},
            {"recRaiseGain", "麦克风电平偏低。请先让 iPad 靠近声源，再小幅提高麦克风增益。"},
            {"recMoveCloser", "源头声音太小，单靠 Windows 增益会主要放大噪声和回声。请先把 iPad 靠近说话位置。"},
            {"recCheckIpadMic", "请确认 iPad 麦克风已启用，并把 iPad 靠近说话位置。"},
            {"recLowerGain", "麦克风接近削波。请降低麦克风增益，直到削波计数保持为 0。"},
            {"recContinuity", "音频连续性不稳定。如果欠载/丢帧持续增加，请关闭占用音频的程序或重启桥接。"},
            {"recLatency", "\u97f3\u9891\u5df2\u7a33\u5b9a\u4f46\u5ef6\u8fdf\u504f\u9ad8\u3002\u7a33\u5b9a\u6027\u786e\u8ba4\u540e\uff0c\u53ef\u5c1d\u8bd5\u964d\u4f4e\u64ad\u653e\u9884\u7f13\u51b2\u3002"},
            {"recGate", "噪声门触发比例过高。如果轻声说话被切掉，请降低噪声门或设为 0。"},
            {"recLimiter", "软限幅正在介入。如果人声仍然发闷或刺耳，请降低麦克风增益。"},
            {"recHeadset", "\u817e\u8baf\u4f1a\u8bae\u6d4b\u8bd5\u65f6\uff0c\u8bf7\u4f7f\u7528\u8033\u673a\u6216\u5173\u95ed iPad \u626c\u58f0\u5668\uff0c\u76f4\u5230 AEC \u5df2\u9a8c\u8bc1\u3002"},
            {"recMeetingVerify", "\u8fdb\u5165\u817e\u8baf\u4f1a\u8bae\u524d\uff0c\u8bf7\u5148\u8fd0\u884c\u68c0\u6d4b\u7ebf\u8def\u6216\u5f55\u97f3\u6765\u9a8c\u8bc1 CABLE Output \u6709\u58f0\u97f3\u3002"},
            {"recMeetingNoAudio", "CABLE Output \u95ed\u73af\u68c0\u6d4b\u4e3a\u9759\u97f3\uff1b\u8bf7\u68c0\u67e5 VB-CABLE \u9009\u62e9\u5e76\u91cd\u542f\u6865\u63a5\u3002"},
            {"recMeetingLoopbackTooQuiet", "腾讯会议实际录音太小。请先提升 iPad 端源头音量，再考虑 Windows 增益。"},
            {"recAec", "回声仍需要 iPad 端语音处理/AEC；Windows 增益和 VB-CABLE 不能消除声学回声。"}
        };

        public static string Get(string language, string key)
        {
            Dictionary<string, string> table = language == "zh-CN" ? Zh : En;
            string value;
            if (table.TryGetValue(key, out value))
            {
                return value;
            }
            return En.TryGetValue(key, out value) ? value : key;
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly AppOptions _options;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();
        private string _language;
        private Label _titleLabel;
        private Label _subtitleLabel;
        private Label _urlLabel;
        private Label _outputLabel;
        private Label _languageLabel;
        private Label _recordLabel;
        private Label _micGainLabel;
        private Label _listenGainLabel;
        private Label _noiseGateLabel;
        private Label _prebufferLabel;
        private Label _secondsLabel;
        private Label _recordHint;
        private Label _serviceTitle;
        private Label _ipadTitle;
        private Label _volumeTitle;
        private Label _latencyTitle;
        private Label _endpointTitle;
        private Label _appsTitle;
        private TextBox _baseUrlText;
        private TextBox _outputDeviceText;
        private TextBox _micGainText;
        private TextBox _monitorGainText;
        private TextBox _noiseGateText;
        private TextBox _prebufferText;
        private ComboBox _languageCombo;
        private Button _startButton;
        private Button _stopButton;
        private Button _refreshButton;
        private Button _testButton;
        private Button _recordButton;
        private Button _playButton;
        private Button _tuneButton;
        private Button _applyPrebufferButton;
        private TextBox _recordSecondsText;
        private Label _serviceValue;
        private Label _ipadValue;
        private Label _volumeValue;
        private Label _latencyValue;
        private Label _endpointValue;
        private Label _appsValue;
        private TextBox _details;
        private NotifyIcon _trayIcon;
        private ContextMenuStrip _trayMenu;
        private Process _pumpProcess;
        private Process _recordProcess;
        private SoundPlayer _player;
        private string _lastRecordingPath;
        private string _lastPlaybackPath;
        private string _recordStopPath;
        private string _recordStdoutPath;
        private string _recordStderrPath;
        private ManualResetEvent _recordStdoutDone;
        private ManualResetEvent _recordStderrDone;
        private bool _preparingRecording;
        private string _viewMode;
        private Dictionary<string, object> _lastStatusPayload;
        private Dictionary<string, object> _lastCapturePayload;
        private Dictionary<string, object> _lastGainTunePayload;

        private sealed class BridgeReadinessBaseline
        {
            public string LastWindowsReceiverStatsAt = "";
            public int AudioPacketsReceived = -1;
        }
        private bool _allowExit;

        public MainForm(AppOptions options)
        {
            _options = options;
            _language = options.Language == "zh-CN" ? "zh-CN" : "en-US";
            Text = "SensorBridge Microphone";
            MinimumSize = new Size(900, 610);
            Size = new Size(1020, 700);
            StartPosition = FormStartPosition.CenterScreen;
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            BackColor = Color.FromArgb(246, 247, 249);
            Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            _json.MaxJsonLength = Int32.MaxValue;
            BuildLayout();
            BuildTrayIcon();
            ApplyLanguage();
        }

        private void BuildLayout()
        {
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.RowCount = 4;
            root.ColumnCount = 1;
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 74));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 94));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 150));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Controls.Add(root);

            Panel header = new Panel();
            header.Dock = DockStyle.Fill;
            header.BackColor = Color.FromArgb(24, 88, 98);
            header.Padding = new Padding(22, 13, 22, 8);
            root.Controls.Add(header, 0, 0);

            _titleLabel = new Label();
            _titleLabel.ForeColor = Color.White;
            _titleLabel.Font = new Font("Segoe UI Semibold", 19F, FontStyle.Bold, GraphicsUnit.Point);
            _titleLabel.AutoSize = true;
            _titleLabel.Location = new Point(0, 4);
            header.Controls.Add(_titleLabel);

            _subtitleLabel = new Label();
            _subtitleLabel.ForeColor = Color.FromArgb(218, 242, 240);
            _subtitleLabel.AutoSize = true;
            _subtitleLabel.Location = new Point(2, 43);
            header.Controls.Add(_subtitleLabel);

            Panel toolbar = new Panel();
            toolbar.Dock = DockStyle.Fill;
            toolbar.BackColor = Color.White;
            toolbar.Padding = new Padding(20, 12, 20, 10);
            root.Controls.Add(toolbar, 0, 1);

            _urlLabel = new Label();
            _urlLabel.AutoSize = true;
            _urlLabel.Location = new Point(0, 11);
            toolbar.Controls.Add(_urlLabel);

            _baseUrlText = new TextBox();
            _baseUrlText.Text = _options.BaseUrl;
            _baseUrlText.Width = 300;
            _baseUrlText.Location = new Point(72, 8);
            toolbar.Controls.Add(_baseUrlText);

            _outputLabel = new Label();
            _outputLabel.AutoSize = true;
            _outputLabel.Location = new Point(386, 11);
            toolbar.Controls.Add(_outputLabel);

            _outputDeviceText = new TextBox();
            _outputDeviceText.Text = _options.OutputDevice;
            _outputDeviceText.Width = 130;
            _outputDeviceText.Location = new Point(438, 8);
            toolbar.Controls.Add(_outputDeviceText);

            _micGainLabel = new Label();
            _micGainLabel.AutoSize = true;
            _micGainLabel.Location = new Point(580, 11);
            toolbar.Controls.Add(_micGainLabel);

            _micGainText = new TextBox();
            _micGainText.Text = _options.MicGain;
            _micGainText.Width = 42;
            _micGainText.Location = new Point(642, 8);
            toolbar.Controls.Add(_micGainText);

            _startButton = new Button();
            _startButton.Text = "Start";
            _startButton.Width = 82;
            _startButton.Height = 28;
            _startButton.Location = new Point(690, 6);
            _startButton.Click += delegate { StartPump(); };
            toolbar.Controls.Add(_startButton);

            _stopButton = new Button();
            _stopButton.Text = "Stop";
            _stopButton.Width = 74;
            _stopButton.Height = 28;
            _stopButton.Location = new Point(776, 6);
            _stopButton.Click += delegate { StopPump(); };
            toolbar.Controls.Add(_stopButton);

            _refreshButton = new Button();
            _refreshButton.Text = "Refresh";
            _refreshButton.Width = 78;
            _refreshButton.Height = 28;
            _refreshButton.Location = new Point(854, 6);
            _refreshButton.Click += delegate { RunStatus(false); };
            toolbar.Controls.Add(_refreshButton);

            _testButton = new Button();
            _testButton.Text = "Test Cable";
            _testButton.Width = 82;
            _testButton.Height = 28;
            _testButton.Location = new Point(936, 6);
            _testButton.Click += delegate { RunLoopbackTest(); };
            toolbar.Controls.Add(_testButton);

            _recordLabel = new Label();
            _recordLabel.AutoSize = true;
            _recordLabel.Location = new Point(0, 48);
            toolbar.Controls.Add(_recordLabel);

            _recordSecondsText = new TextBox();
            _recordSecondsText.Text = "10";
            _recordSecondsText.Width = 42;
            _recordSecondsText.Location = new Point(92, 45);
            _recordSecondsText.Visible = false;
            toolbar.Controls.Add(_recordSecondsText);

            _secondsLabel = new Label();
            _secondsLabel.AutoSize = true;
            _secondsLabel.Location = new Point(140, 48);
            _secondsLabel.Visible = false;
            toolbar.Controls.Add(_secondsLabel);

            _recordButton = new Button();
            _recordButton.Text = "Record";
            _recordButton.Width = 86;
            _recordButton.Height = 28;
            _recordButton.Location = new Point(92, 43);
            _recordButton.Click += delegate { RecordSample(); };
            toolbar.Controls.Add(_recordButton);

            _playButton = new Button();
            _playButton.Text = "Play";
            _playButton.Width = 74;
            _playButton.Height = 28;
            _playButton.Location = new Point(186, 43);
            _playButton.Click += delegate { PlayLastRecording(); };
            toolbar.Controls.Add(_playButton);

            _tuneButton = new Button();
            _tuneButton.Text = "Tune";
            _tuneButton.Width = 68;
            _tuneButton.Height = 28;
            _tuneButton.Location = new Point(266, 43);
            _tuneButton.Click += delegate { RunGainTune(); };
            toolbar.Controls.Add(_tuneButton);

            _recordHint = new Label();
            _recordHint.Size = new Size(124, 20);
            _recordHint.AutoEllipsis = true;
            _recordHint.ForeColor = Color.FromArgb(92, 104, 116);
            _recordHint.Location = new Point(340, 48);
            toolbar.Controls.Add(_recordHint);

            _listenGainLabel = new Label();
            _listenGainLabel.AutoSize = true;
            _listenGainLabel.Location = new Point(470, 48);
            toolbar.Controls.Add(_listenGainLabel);

            _monitorGainText = new TextBox();
            _monitorGainText.Text = _options.MonitorGain;
            _monitorGainText.Width = 42;
            _monitorGainText.Location = new Point(548, 45);
            toolbar.Controls.Add(_monitorGainText);

            _noiseGateLabel = new Label();
            _noiseGateLabel.AutoSize = true;
            _noiseGateLabel.Location = new Point(600, 48);
            toolbar.Controls.Add(_noiseGateLabel);

            _noiseGateText = new TextBox();
            _noiseGateText.Text = _options.NoiseGate;
            _noiseGateText.Width = 42;
            _noiseGateText.Location = new Point(662, 45);
            toolbar.Controls.Add(_noiseGateText);

            _prebufferLabel = new Label();
            _prebufferLabel.AutoSize = true;
            _prebufferLabel.Location = new Point(714, 48);
            toolbar.Controls.Add(_prebufferLabel);

            _prebufferText = new TextBox();
            _prebufferText.Text = _options.PlaybackPrebufferMs;
            _prebufferText.Width = 48;
            _prebufferText.Location = new Point(784, 45);
            toolbar.Controls.Add(_prebufferText);

            _applyPrebufferButton = new Button();
            _applyPrebufferButton.Width = 48;
            _applyPrebufferButton.Height = 24;
            _applyPrebufferButton.Location = new Point(834, 43);
            _applyPrebufferButton.Click += delegate { ApplyRecommendedSettings(); };
            toolbar.Controls.Add(_applyPrebufferButton);

            _languageLabel = new Label();
            _languageLabel.AutoSize = true;
            _languageLabel.Location = new Point(884, 48);
            toolbar.Controls.Add(_languageLabel);

            _languageCombo = new ComboBox();
            _languageCombo.DropDownStyle = ComboBoxStyle.DropDownList;
            _languageCombo.Width = 72;
            _languageCombo.Location = new Point(946, 45);
            _languageCombo.Items.Add("English");
            _languageCombo.Items.Add("中文");
            _languageCombo.SelectedIndex = _language == "zh-CN" ? 1 : 0;
            _languageCombo.SelectedIndexChanged += delegate
            {
                _language = _languageCombo.SelectedIndex == 1 ? "zh-CN" : "en-US";
                ApplyLanguage();
                RenderCurrentView();
            };
            toolbar.Controls.Add(_languageCombo);

            TableLayoutPanel statusGrid = new TableLayoutPanel();
            statusGrid.Dock = DockStyle.Fill;
            statusGrid.Padding = new Padding(18, 10, 18, 10);
            statusGrid.ColumnCount = 3;
            statusGrid.RowCount = 2;
            for (int i = 0; i < 3; i++)
            {
                statusGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.333F));
            }
            statusGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
            statusGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
            root.Controls.Add(statusGrid, 0, 2);

            _serviceValue = AddCard(statusGrid, 0, 0, out _serviceTitle);
            _ipadValue = AddCard(statusGrid, 1, 0, out _ipadTitle);
            _volumeValue = AddCard(statusGrid, 2, 0, out _volumeTitle);
            _latencyValue = AddCard(statusGrid, 0, 1, out _latencyTitle);
            _endpointValue = AddCard(statusGrid, 1, 1, out _endpointTitle);
            _appsValue = AddCard(statusGrid, 2, 1, out _appsTitle);

            _details = new TextBox();
            _details.Dock = DockStyle.Fill;
            _details.Multiline = true;
            _details.ReadOnly = true;
            _details.ScrollBars = ScrollBars.Both;
            _details.Font = new Font("Consolas", 9F, FontStyle.Regular, GraphicsUnit.Point);
            _details.BackColor = Color.White;
            root.Controls.Add(_details, 0, 3);

            ApplyLanguage();
            RenderIdle();
        }

        private void BuildTrayIcon()
        {
            _trayMenu = new ContextMenuStrip();
            _trayMenu.Items.Add("Open", null, delegate { RestoreFromTray(); });
            _trayMenu.Items.Add("Start", null, delegate
            {
                RestoreFromTray();
                StartPump();
            });
            _trayMenu.Items.Add("Stop", null, delegate { StopPump(); });
            _trayMenu.Items.Add("Record sample", null, delegate
            {
                RestoreFromTray();
                RecordSample();
            });
            _trayMenu.Items.Add("Play sample", null, delegate
            {
                RestoreFromTray();
                PlayLastRecording();
            });
            _trayMenu.Items.Add("Refresh", null, delegate
            {
                RestoreFromTray();
                RunStatus(false);
            });
            _trayMenu.Items.Add("Tune gain", null, delegate
            {
                RestoreFromTray();
                RunGainTune();
            });
            _trayMenu.Items.Add("Open diagnostics folder", null, delegate { OpenCapturesFolder(); });
            _trayMenu.Items.Add("Bundle diagnostics", null, delegate
            {
                RestoreFromTray();
                BundleDiagnostics();
            });
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add("Exit", null, delegate
            {
                _allowExit = true;
                Close();
            });

            _trayIcon = new NotifyIcon();
            _trayIcon.Text = "SensorBridge Microphone";
            _trayIcon.Icon = Icon == null ? SystemIcons.Application : Icon;
            _trayIcon.ContextMenuStrip = _trayMenu;
            _trayIcon.Visible = true;
            _trayIcon.DoubleClick += delegate { RestoreFromTray(); };
        }

        private string T(string key)
        {
            return LocalizedText.Get(_language, key);
        }

        private void ApplyLanguage()
        {
            Text = T("appTitle");
            if (_titleLabel != null) { _titleLabel.Text = T("appTitle"); }
            if (_subtitleLabel != null) { _subtitleLabel.Text = T("subtitle"); }
            if (_urlLabel != null) { _urlLabel.Text = T("baseUrl"); }
            if (_outputLabel != null) { _outputLabel.Text = T("output"); }
            if (_languageLabel != null) { _languageLabel.Text = T("language"); }
            if (_startButton != null) { _startButton.Text = T("start"); }
            if (_stopButton != null) { _stopButton.Text = T("stop"); }
            if (_refreshButton != null) { _refreshButton.Text = T("refresh"); }
            if (_testButton != null) { _testButton.Text = T("testCable"); }
            if (_recordLabel != null) { _recordLabel.Text = T("qualityCheck"); }
            if (_micGainLabel != null) { _micGainLabel.Text = T("micGain"); }
            if (_listenGainLabel != null) { _listenGainLabel.Text = T("listenGain"); }
            if (_noiseGateLabel != null) { _noiseGateLabel.Text = T("noiseGate"); }
            if (_prebufferLabel != null) { _prebufferLabel.Text = T("prebuffer"); }
            if (_applyPrebufferButton != null) { _applyPrebufferButton.Text = T("useRecommended"); }
            if (_secondsLabel != null) { _secondsLabel.Text = T("seconds"); }
            if (_recordButton != null) { _recordButton.Text = _preparingRecording ? T("statusPreparingRecord") : (IsRecording() ? T("stopRecording") : T("record")); }
            if (_playButton != null) { _playButton.Text = T("play"); }
            if (_tuneButton != null) { _tuneButton.Text = T("tuneGain"); }
            if (_recordHint != null) { _recordHint.Text = T("recordHint"); }
            if (_serviceTitle != null) { _serviceTitle.Text = T("backend"); }
            if (_ipadTitle != null) { _ipadTitle.Text = T("ipadUpstream"); }
            if (_volumeTitle != null) { _volumeTitle.Text = T("windowsReceiver"); }
            if (_latencyTitle != null) { _latencyTitle.Text = T("buffer"); }
            if (_endpointTitle != null) { _endpointTitle.Text = T("vbcable"); }
            if (_appsTitle != null) { _appsTitle.Text = T("tencentMeeting"); }
            if (_trayIcon != null) { _trayIcon.Text = T("appTitle"); }
            if (_trayMenu != null && _trayMenu.Items.Count >= 11)
            {
                _trayMenu.Items[0].Text = T("trayOpen");
                _trayMenu.Items[1].Text = T("start");
                _trayMenu.Items[2].Text = T("stop");
                _trayMenu.Items[3].Text = T("trayRecord");
                _trayMenu.Items[4].Text = T("trayPlay");
                _trayMenu.Items[5].Text = T("refresh");
                _trayMenu.Items[6].Text = T("trayTune");
                _trayMenu.Items[7].Text = T("trayOpenCaptures");
                _trayMenu.Items[8].Text = T("trayBundleDiagnostics");
                _trayMenu.Items[10].Text = T("trayExit");
            }
        }

        private void RenderCurrentView()
        {
            if (_viewMode == "status" && _lastStatusPayload != null)
            {
                RenderStatus(_lastStatusPayload);
            }
            else if (_viewMode == "capture" && _lastCapturePayload != null)
            {
                RenderCaptureStatus(_lastCapturePayload);
            }
            else if (_viewMode == "gain_tune" && _lastGainTunePayload != null)
            {
                RenderGainTuneStatus(_lastGainTunePayload);
            }
            else
            {
                RenderIdle();
            }
        }

        private void UpdateRecommendedPrebufferButton(Dictionary<string, object> payload, Dictionary<string, object> quality)
        {
            if (_applyPrebufferButton == null)
            {
                return;
            }
            if (quality == null || quality.Count == 0)
            {
                _applyPrebufferButton.Enabled = false;
                return;
            }
            Dictionary<string, object> receiver = DictionaryValue(payload, "windows_receiver");
            double recommendedPrebuffer = DoubleValue(quality, "recommendedPlaybackPrebufferMs");
            double recommendedGain = DoubleValue(quality, "recommendedMicGainStep");
            double recommendedMonitorGain = DoubleValue(quality, "recommendedMonitorGain");
            double runningPrebuffer = DoubleValue(receiver, "playbackPrebufferMs");
            double runningGain = DoubleValue(receiver, "outputGain");
            double desiredMonitorGain = TextBoxDouble(_monitorGainText, 0.0);
            bool canApplyGain = !Bool(quality, "sourceTooQuietForGainOnly");
            bool gainWouldChange = canApplyGain && recommendedGain >= 0.05 && runningGain > 0.0 && Math.Abs(recommendedGain - runningGain) >= 0.001;
            bool prebufferWouldChange = recommendedPrebuffer >= 100.0 && runningPrebuffer >= 100.0 && Math.Abs(recommendedPrebuffer - runningPrebuffer) >= 1.0;
            bool monitorGainWouldChange = recommendedMonitorGain >= 1.0 && Math.Abs(recommendedMonitorGain - desiredMonitorGain) >= 0.001;
            _applyPrebufferButton.Enabled = gainWouldChange || prebufferWouldChange || monitorGainWouldChange;
        }

        private void ApplyRecommendedSettings()
        {
            Dictionary<string, object> quality = DictionaryValue(_lastStatusPayload, "quality");
            double recommendedGain = DoubleValue(quality, "recommendedMicGainStep");
            if (!Bool(quality, "sourceTooQuietForGainOnly") && recommendedGain >= 0.05 && _micGainText != null)
            {
                _micGainText.Text = recommendedGain.ToString("0.###", CultureInfo.InvariantCulture);
            }
            double recommendedPrebuffer = DoubleValue(quality, "recommendedPlaybackPrebufferMs");
            if (recommendedPrebuffer >= 100.0 && _prebufferText != null)
            {
                _prebufferText.Text = recommendedPrebuffer.ToString("0.###", CultureInfo.InvariantCulture);
            }
            double recommendedMonitorGain = DoubleValue(quality, "recommendedMonitorGain");
            if (recommendedMonitorGain >= 1.0 && _monitorGainText != null)
            {
                _monitorGainText.Text = recommendedMonitorGain.ToString("0.###", CultureInfo.InvariantCulture);
            }
            RenderCurrentView();
        }

        private bool BridgeSettingsRestartPending(Dictionary<string, object> payload, Dictionary<string, object> quality)
        {
            return PendingBridgeSettingNames(payload, quality).Count > 0;
        }

        private string BridgeSettingsRestartHint(Dictionary<string, object> payload, Dictionary<string, object> quality)
        {
            List<string> names = PendingBridgeSettingNames(payload, quality);
            if (names.Count == 0)
            {
                return "";
            }
            return Join(T("restartToApply"), ": ", String.Join(", ", names.ToArray()));
        }

        private List<string> PendingBridgeSettingNames(Dictionary<string, object> payload, Dictionary<string, object> quality)
        {
            Dictionary<string, object> receiver = DictionaryValue(payload, "windows_receiver");
            List<string> names = new List<string>();

            double runningGain = DoubleValue(receiver, "outputGain");
            double desiredGain = TextBoxDouble(_micGainText, runningGain);
            if (runningGain > 0.0 && Math.Abs(desiredGain - runningGain) >= 0.001)
            {
                names.Add(T("micGain"));
            }

            double runningGate = DoubleValue(quality, "noiseGateThreshold");
            double desiredGate = TextBoxDouble(_noiseGateText, runningGate);
            if (Math.Abs(desiredGate - runningGate) >= 0.001)
            {
                names.Add(T("noiseGate"));
            }

            double runningPrebuffer = DoubleValue(receiver, "playbackPrebufferMs");
            double desiredPrebuffer = TextBoxDouble(_prebufferText, runningPrebuffer);
            if (runningPrebuffer >= 100.0 && Math.Abs(desiredPrebuffer - runningPrebuffer) >= 1.0)
            {
                names.Add(T("prebuffer"));
            }

            return names;
        }

        private static Label AddCard(TableLayoutPanel grid, int column, int row, out Label titleLabel)
        {
            Panel card = new Panel();
            card.Dock = DockStyle.Fill;
            card.Margin = new Padding(5);
            card.BackColor = Color.White;
            grid.Controls.Add(card, column, row);

            Panel accent = new Panel();
            accent.Dock = DockStyle.Left;
            accent.Width = 4;
            accent.BackColor = Color.FromArgb(31, 153, 132);
            card.Controls.Add(accent);

            Label cardTitle = new Label();
            cardTitle.Location = new Point(16, 8);
            cardTitle.Size = new Size(260, 16);
            cardTitle.ForeColor = Color.FromArgb(92, 104, 116);
            cardTitle.Font = new Font("Segoe UI Semibold", 8.5F, FontStyle.Bold, GraphicsUnit.Point);
            cardTitle.AutoEllipsis = true;
            card.Controls.Add(cardTitle);

            Label value = new Label();
            value.Text = "-";
            value.Location = new Point(16, 29);
            value.Size = new Size(260, 20);
            value.ForeColor = Color.FromArgb(28, 39, 50);
            value.AutoEllipsis = true;
            card.Controls.Add(value);
            card.Resize += delegate
            {
                int width = Math.Max(60, card.ClientSize.Width - 28);
                cardTitle.Width = width;
                value.Width = width;
            };
            titleLabel = cardTitle;
            return value;
        }

        private void RunStatus(bool startRequested)
        {
            _startButton.Enabled = false;
            _refreshButton.Enabled = false;
            _testButton.Enabled = false;
            _recordButton.Enabled = false;
            _tuneButton.Enabled = false;
            _serviceValue.Text = startRequested ? T("statusStarting") : T("statusRefreshing");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> payload = RunBridge();
                    Ui(delegate
                    {
                        RenderStatus(payload);
                    });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceValue.Text = T("statusFailed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate
                    {
                        _startButton.Enabled = true;
                        _refreshButton.Enabled = true;
                        _testButton.Enabled = true;
                        _recordButton.Enabled = true;
                        _tuneButton.Enabled = true;
                    });
                }
            });
        }

        private void RunLoopbackTest()
        {
            _startButton.Enabled = false;
            _refreshButton.Enabled = false;
            _testButton.Enabled = false;
            _recordButton.Enabled = false;
            _tuneButton.Enabled = false;
            _serviceValue.Text = T("statusTestingCable");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> payload = RunBridgeCommand("vbcable-loopback-check", Math.Max(5, _options.Frames), true);
                    Ui(delegate { RenderStatus(payload); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceValue.Text = T("statusTestFailed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate
                    {
                        _startButton.Enabled = true;
                        _refreshButton.Enabled = true;
                        _testButton.Enabled = true;
                        _recordButton.Enabled = true;
                        _tuneButton.Enabled = true;
                    });
                }
            });
        }

        private void RunGainTune()
        {
            _startButton.Enabled = false;
            _refreshButton.Enabled = false;
            _testButton.Enabled = false;
            _recordButton.Enabled = false;
            _playButton.Enabled = false;
            _tuneButton.Enabled = false;
            _serviceValue.Text = T("statusTuningGain");
            _details.Text = T("statusTuningGain");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> payload = RunBridgeCommand("gain-tune", Math.Max(3, _options.Frames), true, "--gain-values 0.75,1.0,1.25");
                    Ui(delegate { RenderGainTuneStatus(payload); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceValue.Text = T("statusTuneFailed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate
                    {
                        _startButton.Enabled = true;
                        _refreshButton.Enabled = true;
                        _testButton.Enabled = true;
                        _recordButton.Enabled = true;
                        _playButton.Enabled = true;
                        _tuneButton.Enabled = true;
                    });
                }
            });
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (WindowState == FormWindowState.Minimized)
            {
                HideToTray();
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!_allowExit && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                HideToTray();
                return;
            }
            base.OnFormClosing(e);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                StopRecordingForExit();
                StopPump();
                if (_trayIcon != null)
                {
                    _trayIcon.Visible = false;
                    _trayIcon.Dispose();
                    _trayIcon = null;
                }
                if (_trayMenu != null)
                {
                    _trayMenu.Dispose();
                    _trayMenu = null;
                }
                if (_player != null)
                {
                    _player.Stop();
                    _player.Dispose();
                    _player = null;
                }
            }
            base.Dispose(disposing);
        }

        private void StopRecordingForExit()
        {
            if (!IsRecording())
            {
                return;
            }
            try
            {
                File.WriteAllText(_recordStopPath, "stop");
                if (!_recordProcess.WaitForExit(5000))
                {
                    _recordProcess.Kill();
                    _recordProcess.WaitForExit(3000);
                }
            }
            catch
            {
            }
            _recordProcess = null;
        }

        private void HideToTray()
        {
            Hide();
            ShowInTaskbar = false;
            if (_trayIcon != null)
            {
                _trayIcon.Visible = true;
            }
        }

        private void RestoreFromTray()
        {
            ShowInTaskbar = true;
            Show();
            WindowState = FormWindowState.Normal;
            Activate();
        }

        private Dictionary<string, object> RunBridge()
        {
            return RunBridgeCommand("webrtc-loopback-check", Math.Max(3, _options.Frames), true);
        }

        private Dictionary<string, object> RunBridgeCommand(string command, int frames, bool captureOutput)
        {
            return RunBridgeCommand(command, frames, captureOutput, "");
        }

        private Dictionary<string, object> RunBridgeCommand(string command, int frames, bool captureOutput, string extraArguments)
        {
            string baseUrl = ResolvePreferredBaseUrlForCommand(command);
            return RunBridgeCommandRaw(command, frames, captureOutput, extraArguments, baseUrl);
        }

        private Dictionary<string, object> RunBridgeCommandRaw(string command, int frames, bool captureOutput, string extraArguments, string baseUrlOverride)
        {
            string bridge = Path.Combine(_options.ProjectRoot, "bridge.py");
            if (!File.Exists(bridge))
            {
                throw new FileNotFoundException("bridge.py not found", bridge);
            }

            ProcessStartInfo info = new ProcessStartInfo();
            string python = ResolvePython();
            info.FileName = python == "py" ? "py" : python;
            info.Arguments = BuildBridgeArguments(python, bridge, command, frames, Convert.ToString(frames), extraArguments, baseUrlOverride);
            info.WorkingDirectory = _options.ProjectRoot;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = captureOutput;
            info.RedirectStandardError = captureOutput;

            using (Process process = Process.Start(info))
            {
                string output = captureOutput ? process.StandardOutput.ReadToEnd() : "";
                string error = captureOutput ? process.StandardError.ReadToEnd() : "";
                process.WaitForExit();
                if (String.IsNullOrWhiteSpace(output))
                {
                    throw new InvalidOperationException(error.Length > 0 ? error : "bridge.py returned no output");
                }
                Dictionary<string, object> payload = _json.Deserialize<Dictionary<string, object>>(ExtractJson(output));
                if (process.ExitCode != 0 && payload == null)
                {
                    throw new InvalidOperationException(error.Length > 0 ? error : output);
                }
                return payload;
            }
        }

        private string ResolvePreferredBaseUrlForCommand(string command)
        {
            string current = NormalizeBaseUrl(_baseUrlText.Text);
            if (ShouldSkipBackendPreflight(command) || String.IsNullOrWhiteSpace(_options.RelayUrl))
            {
                return current;
            }
            try
            {
                Dictionary<string, object> payload = RunBridgeCommandRaw("connection-check", 1, true, "", current);
                string preferred = NormalizeBaseUrl(Value(payload, "preferredBaseUrl"));
                if (Bool(payload, "ok") &&
                    !String.IsNullOrWhiteSpace(preferred) &&
                    !String.Equals(preferred, current, StringComparison.OrdinalIgnoreCase))
                {
                    string reason = Value(payload, "backendSelectionReason");
                    Ui(delegate
                    {
                        _baseUrlText.Text = preferred;
                        if (_details != null && !String.IsNullOrWhiteSpace(_details.Text))
                        {
                            _details.Text = String.Format(T("backendSwitched"), preferred) +
                                "\r\n" + T("backendSelectionReason") + ": " + reason +
                                "\r\n" + _details.Text;
                        }
                    });
                    return preferred;
                }
            }
            catch
            {
            }
            return current;
        }

        private static bool ShouldSkipBackendPreflight(string command)
        {
            string value = (command ?? "").Trim().ToLowerInvariant().Replace("_", "-");
            return value == "connection-check" ||
                value == "diagnostic-bundle" ||
                value == "desktop-shortcut-status" ||
                value == "shortcut-status";
        }

        private string BuildBridgeArguments(string python, string bridge, string command, int frames)
        {
            return BuildBridgeArguments(python, bridge, command, frames, Convert.ToString(frames), "", "");
        }

        private string BuildBridgeArguments(string python, string bridge, string command, int frames, string durationSeconds)
        {
            return BuildBridgeArguments(python, bridge, command, frames, durationSeconds, "", "");
        }

        private string BuildBridgeArguments(string python, string bridge, string command, int frames, string durationSeconds, string extraArguments)
        {
            return BuildBridgeArguments(python, bridge, command, frames, durationSeconds, extraArguments, "");
        }

        private string BuildBridgeArguments(string python, string bridge, string command, int frames, string durationSeconds, string extraArguments, string baseUrlOverride)
        {
            string baseUrl = String.IsNullOrWhiteSpace(baseUrlOverride) ? _baseUrlText.Text : baseUrlOverride;
            return (python == "py" ? "-3 " : "") +
                Quote(bridge) +
                " --base-url " + Quote(baseUrl) +
                " --relay-url " + Quote(_options.RelayUrl) +
                " --output-device " + Quote(_outputDeviceText.Text) +
                " --output-gain " + NumericOption(_micGainText, "1.0", 0.05, 20.0) +
                " --low-cut-hz 80" +
                " --noise-gate-threshold " + NumericOption(_noiseGateText, "0.0", 0.0, 5000.0) +
                " --playback-prebuffer-ms " + NumericOption(_prebufferText, "1500", 100.0, 5000.0) +
                " --playback-max-buffer-ms 5000" +
                " --frames " + frames +
                " --duration-seconds " + durationSeconds +
                (String.IsNullOrWhiteSpace(extraArguments) ? "" : " " + extraArguments) +
                " " + command;
        }

        private void StartPump()
        {
            if (_pumpProcess != null && !_pumpProcess.HasExited)
            {
                _serviceValue.Text = T("statusStreaming");
                return;
            }

            string bridge = Path.Combine(_options.ProjectRoot, "bridge.py");
            string python = ResolvePython();
            string baseUrl = ResolvePreferredBaseUrlForCommand("webrtc-microphone");
            StopExistingProjectBridgePumps();
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = python == "py" ? "py" : python;
            info.Arguments = BuildBridgeArguments(python, bridge, "webrtc-microphone", 0, "0", "", baseUrl);
            info.WorkingDirectory = _options.ProjectRoot;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = false;
            info.RedirectStandardError = false;
            _pumpProcess = Process.Start(info);
            _serviceValue.Text = T("statusStreaming");
            _details.Text = T("startDetails");
        }

        private void RecordSample()
        {
            if (IsRecording())
            {
                StopRecording();
                return;
            }
            if (_preparingRecording)
            {
                return;
            }
            StartRecording();
        }

        private bool IsRecording()
        {
            return _recordProcess != null && !_recordProcess.HasExited;
        }

        private void StartRecording()
        {
            _preparingRecording = true;
            string baseUrl = ResolvePreferredBaseUrlForCommand("webrtc-microphone");
            BridgeReadinessBaseline baseline = CaptureBridgeReadinessBaseline(baseUrl);
            if (_pumpProcess == null || _pumpProcess.HasExited)
            {
                StartPump();
            }
            _startButton.Enabled = false;
            _refreshButton.Enabled = false;
            _testButton.Enabled = false;
            _recordButton.Enabled = false;
            _playButton.Enabled = false;
            _tuneButton.Enabled = false;
            _recordButton.Text = T("statusPreparingRecord");
            _serviceValue.Text = T("statusPreparingRecord");
            _details.Text = T("preparingRecordDetails");

            ThreadPool.QueueUserWorkItem(delegate
            {
                bool ready = WaitForBridgeReady(baseUrl, 10000, baseline);
                Ui(delegate
                {
                    _preparingRecording = false;
                    StartRecordingProcess(ready);
                });
            });
        }

        private void StartRecordingProcess(bool bridgeReady)
        {
            try
            {
                string bridge = Path.Combine(_options.ProjectRoot, "bridge.py");
                string python = ResolvePython();
                string captureDir = Path.Combine(_options.ProjectRoot, "captures");
                Directory.CreateDirectory(captureDir);
                string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                string capturePath = Path.Combine(captureDir, "gui_mic_quality_" + stamp + ".wav");
                _recordStopPath = Path.Combine(captureDir, "gui_mic_quality_" + stamp + ".stop");
                _recordStdoutPath = Path.Combine(captureDir, "gui_mic_quality_" + stamp + ".json");
                _recordStderrPath = Path.Combine(captureDir, "gui_mic_quality_" + stamp + ".err.log");
                File.Delete(_recordStopPath);
                File.Delete(_recordStdoutPath);
                File.Delete(_recordStderrPath);

                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = python == "py" ? "py" : python;
                info.Arguments = BuildBridgeArguments(
                    python,
                    bridge,
                    "vbcable-output-record",
                    0,
                    "0",
                    "--capture-path " + Quote(capturePath) + " --stop-file " + Quote(_recordStopPath) + " --monitor-gain " + NumericOption(_monitorGainText, "4.0", 1.0, 20.0) + " --tail-seconds 4");
                info.WorkingDirectory = _options.ProjectRoot;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.RedirectStandardOutput = true;
                info.RedirectStandardError = true;
                _recordProcess = Process.Start(info);
                _recordStdoutDone = new ManualResetEvent(false);
                _recordStderrDone = new ManualResetEvent(false);
                BeginStreamToFile(_recordProcess.StandardOutput, _recordStdoutPath, _recordStdoutDone);
                BeginStreamToFile(_recordProcess.StandardError, _recordStderrPath, _recordStderrDone);

                _startButton.Enabled = false;
                _refreshButton.Enabled = false;
                _testButton.Enabled = false;
                _playButton.Enabled = false;
                _tuneButton.Enabled = false;
                _recordButton.Enabled = true;
                _recordButton.Text = T("stopRecording");
                _serviceValue.Text = T("statusRecording");
                _details.Text = bridgeReady ? T("recordDetails") : T("recordNotReadyDetails");
            }
            catch (Exception exc)
            {
                _serviceValue.Text = T("statusRecordFailed");
                _details.Text = exc.ToString();
                _recordProcess = null;
                _preparingRecording = false;
                ApplyLanguage();
            }
        }

        private void StopRecording()
        {
            if (!IsRecording())
            {
                return;
            }
            _recordButton.Enabled = false;
            _serviceValue.Text = T("stoppingRecord");
            _details.Text = T("stoppingRecord");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    File.WriteAllText(_recordStopPath, "stop");
                    if (!_recordProcess.WaitForExit(20000))
                    {
                        _recordProcess.Kill();
                        _recordProcess.WaitForExit(3000);
                    }
                    WaitForStreamFile(_recordStdoutDone, 3000);
                    WaitForStreamFile(_recordStderrDone, 3000);
                    string output = File.Exists(_recordStdoutPath) ? File.ReadAllText(_recordStdoutPath) : "";
                    string error = File.Exists(_recordStderrPath) ? File.ReadAllText(_recordStderrPath) : "";
                    if (String.IsNullOrWhiteSpace(output))
                    {
                        throw new InvalidOperationException(error.Length > 0 ? error : "record process returned no output");
                    }
                    Dictionary<string, object> payload = _json.Deserialize<Dictionary<string, object>>(ExtractJson(output));
                    Ui(delegate { RenderCaptureStatus(payload); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceValue.Text = T("statusRecordFailed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate
                    {
                        _recordProcess = null;
                        _recordStdoutDone = null;
                        _recordStderrDone = null;
                        _startButton.Enabled = true;
                        _refreshButton.Enabled = true;
                        _testButton.Enabled = true;
                        _recordButton.Enabled = true;
                        _playButton.Enabled = true;
                        _tuneButton.Enabled = true;
                        _recordButton.Text = T("record");
                    });
                }
            });
        }

        private static void BeginStreamToFile(StreamReader reader, string path, ManualResetEvent done)
        {
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    using (reader)
                    using (StreamWriter writer = new StreamWriter(path, false, Encoding.UTF8))
                    {
                        writer.Write(reader.ReadToEnd());
                    }
                }
                catch
                {
                }
                finally
                {
                    if (done != null)
                    {
                        done.Set();
                    }
                }
            });
        }

        private static void WaitForStreamFile(ManualResetEvent done, int timeoutMilliseconds)
        {
            if (done != null)
            {
                done.WaitOne(timeoutMilliseconds);
            }
        }

        private BridgeReadinessBaseline CaptureBridgeReadinessBaseline(string baseUrl)
        {
            BridgeReadinessBaseline baseline = new BridgeReadinessBaseline();
            try
            {
                Dictionary<string, object> status = GetJson(NormalizeBaseUrl(baseUrl) + "/api/v2/webrtc/status");
                baseline.LastWindowsReceiverStatsAt = Value(status, "lastWindowsReceiverStatsAt");
                baseline.AudioPacketsReceived = IntValue(status, "audioPacketsReceived");
            }
            catch
            {
            }
            return baseline;
        }

        private bool WaitForBridgeReady(string baseUrl, int timeoutMilliseconds, BridgeReadinessBaseline baseline)
        {
            DateTime deadline = DateTime.UtcNow.AddMilliseconds(timeoutMilliseconds);
            while (DateTime.UtcNow < deadline)
            {
                try
                {
                    Dictionary<string, object> status = GetJson(NormalizeBaseUrl(baseUrl) + "/api/v2/webrtc/status");
                    bool windowsFresh = Bool(status, "windowsReceiverStatsFresh");
                    bool micFresh = Bool(status, "microphoneUpstreamStatsFresh");
                    string receiverState = Value(status, "windowsReceiverState");
                    string upstreamState = Value(status, "microphoneUpstreamState");
                    string lastWindowsStatsAt = Value(status, "lastWindowsReceiverStatsAt");
                    int packets = IntValue(status, "audioPacketsReceived");
                    bool currentStats = String.IsNullOrWhiteSpace(baseline.LastWindowsReceiverStatsAt) ||
                        !String.Equals(lastWindowsStatsAt, baseline.LastWindowsReceiverStatsAt, StringComparison.OrdinalIgnoreCase) ||
                        (baseline.AudioPacketsReceived >= 0 && packets > baseline.AudioPacketsReceived);
                    if (windowsFresh && micFresh &&
                        currentStats &&
                        receiverState.IndexOf("receiving", StringComparison.OrdinalIgnoreCase) >= 0 &&
                        upstreamState.IndexOf("sending", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        return true;
                    }
                }
                catch
                {
                }
                Thread.Sleep(250);
            }
            return false;
        }

        private Dictionary<string, object> GetJson(string url)
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.Method = "GET";
            request.Timeout = 1500;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            using (StreamReader reader = new StreamReader(response.GetResponseStream()))
            {
                return _json.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
            }
        }

        private static string NormalizeBaseUrl(string baseUrl)
        {
            string text = (baseUrl ?? "").Trim().TrimEnd('/');
            if (text.Length == 0)
            {
                return "http://192.168.0.24:27180";
            }
            if (!text.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
                !text.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                text = "http://" + text;
            }
            return text;
        }

        private void PlayLastRecording()
        {
            string path = !String.IsNullOrWhiteSpace(_lastPlaybackPath) ? _lastPlaybackPath : _lastRecordingPath;
            if (String.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                _serviceValue.Text = T("statusNoRecording");
                _details.Text = T("noRecordingDetails");
                return;
            }
            try
            {
                if (_player != null)
                {
                    _player.Stop();
                    _player.Dispose();
                }
                _player = new SoundPlayer(path);
                _player.LoadAsync();
                _player.Play();
                _serviceValue.Text = T("statusPlaying");
                _details.Text = String.Format(T("playingDetails"), path, _lastRecordingPath);
            }
            catch (Exception exc)
            {
                _serviceValue.Text = T("statusPlayFailed");
                _details.Text = exc.ToString();
            }
        }

        private void OpenCapturesFolder()
        {
            try
            {
                string captureDir = Path.Combine(_options.ProjectRoot, "captures");
                Directory.CreateDirectory(captureDir);
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = captureDir;
                info.UseShellExecute = true;
                Process.Start(info);
            }
            catch (Exception exc)
            {
                _serviceValue.Text = T("statusFailed");
                _details.Text = exc.ToString();
            }
        }

        private void BundleDiagnostics()
        {
            _serviceValue.Text = T("statusBundlingDiagnostics");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> payload = RunBridgeCommand("diagnostic-bundle", 1, true);
                    Ui(delegate
                    {
                        _serviceValue.Text = T("statusDiagnosticBundleReady");
                        _details.Text = String.Format(T("diagnosticBundleDetails"), Value(payload, "bundlePath"), Value(payload, "filesIncluded"));
                        OpenBundlesFolder();
                    });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceValue.Text = T("statusFailed");
                        _details.Text = exc.ToString();
                    });
                }
            });
        }

        private void OpenBundlesFolder()
        {
            string bundleDir = Path.Combine(_options.ProjectRoot, "captures", "bundles");
            Directory.CreateDirectory(bundleDir);
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = bundleDir;
            info.UseShellExecute = true;
            Process.Start(info);
        }

        private void StopPump()
        {
            if (_pumpProcess != null && !_pumpProcess.HasExited)
            {
                StopProcessTree(_pumpProcess.Id);
                _pumpProcess.WaitForExit(3000);
            }
            StopExistingProjectBridgePumps();
            _pumpProcess = null;
            if (!IsDisposed && _serviceValue != null && !_serviceValue.IsDisposed)
            {
                _serviceValue.Text = T("statusStopped");
            }
        }

        private void StopExistingProjectBridgePumps()
        {
            string projectRoot = Path.GetFullPath(_options.ProjectRoot).TrimEnd(Path.DirectorySeparatorChar).ToLowerInvariant();
            foreach (int processId in FindBridgePumpProcessIds(projectRoot))
            {
                StopProcessTree(processId);
            }
        }

        private static List<int> FindBridgePumpProcessIds(string projectRoot)
        {
            List<int> ids = new List<int>();
            using (ManagementObjectSearcher searcher = new ManagementObjectSearcher("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='python.exe' OR Name='py.exe'"))
            using (ManagementObjectCollection results = searcher.Get())
            {
                foreach (ManagementObject result in results)
                {
                    string commandLine = Convert.ToString(result["CommandLine"]) ?? "";
                    string lower = commandLine.ToLowerInvariant();
                    if (lower.IndexOf("bridge.py", StringComparison.Ordinal) < 0 ||
                        lower.IndexOf("webrtc-microphone", StringComparison.Ordinal) < 0)
                    {
                        continue;
                    }
                    if (projectRoot.Length > 0 && lower.IndexOf(projectRoot, StringComparison.Ordinal) < 0 && lower.IndexOf(" bridge.py ", StringComparison.Ordinal) < 0)
                    {
                        continue;
                    }
                    ids.Add(Convert.ToInt32(result["ProcessId"]));
                }
            }
            return ids;
        }

        private static void StopProcessTree(int processId)
        {
            foreach (int childId in FindChildProcessIds(processId))
            {
                StopProcessTree(childId);
            }
            try
            {
                using (Process process = Process.GetProcessById(processId))
                {
                    process.Kill();
                    process.WaitForExit(3000);
                }
            }
            catch
            {
            }
        }

        private static List<int> FindChildProcessIds(int parentProcessId)
        {
            List<int> ids = new List<int>();
            using (ManagementObjectSearcher searcher = new ManagementObjectSearcher("SELECT ProcessId FROM Win32_Process WHERE ParentProcessId=" + parentProcessId))
            using (ManagementObjectCollection results = searcher.Get())
            {
                foreach (ManagementObject result in results)
                {
                    ids.Add(Convert.ToInt32(result["ProcessId"]));
                }
            }
            return ids;
        }

        private void RenderIdle()
        {
            _viewMode = "idle";
            _lastGainTunePayload = null;
            UpdateRecommendedPrebufferButton(null, null);
            _serviceValue.Text = T("statusNotStarted");
            _ipadValue.Text = "-";
            _volumeValue.Text = "-";
            _latencyValue.Text = "-";
            _endpointValue.Text = "-";
            _appsValue.Text = "-";
            _details.Text = T("idleDetails");
        }

        private void RenderStatus(Dictionary<string, object> payload)
        {
            _viewMode = "status";
            _lastStatusPayload = payload;
            _lastGainTunePayload = null;
            bool ok = Bool(payload, "ok");
            bool isWebRtc = Value(payload, "transport") == "webrtc_opus_microphone_upstream";
            Dictionary<string, object> quality = DictionaryValue(payload, "quality");
            Dictionary<string, object> meeting = DictionaryValue(payload, "tencent_meeting");
            UpdateRecommendedPrebufferButton(payload, isWebRtc ? quality : null);
            Dictionary<string, object> readiness = DictionaryValue(payload, "readiness");
            _serviceValue.Text = ok ? (isWebRtc ? WebRtcQualityHeadline(quality, meeting, readiness) : T("statusReachable")) : (isWebRtc ? T("statusWebrtcPending") : T("statusNotReady"));
            if (isWebRtc)
            {
                _ipadValue.Text = Join(Nested(payload, "ipad_upstream", "microphoneUpstreamPacketsSent"), T("packets"), Nested(payload, "ipad_upstream", "microphoneUpstreamState"));
                string sourceLift = Bool(quality, "sourceTooQuietForGainOnly") && DoubleValue(quality, "recommendedSourceLiftDb") > 0
                    ? Join(" / ", T("sourceLift"), " ", T("approximately"), Value(quality, "recommendedSourceLiftDb"), " dB")
                    : "";
                _volumeValue.Text = Join(T("outputLevel"), " peak ", Nested(payload, "windows_receiver", "outputPeakAbs"), DbfsSuffix(Nested(payload, "windows_receiver", "outputPeakDbfs")), T("peak"), Nested(payload, "windows_receiver", "outputRms"), DbfsSuffix(Nested(payload, "windows_receiver", "outputRmsDbfs")), " x", Nested(payload, "windows_receiver", "outputGain"), " / ", T("nextGain"), " x", Value(quality, "recommendedMicGainStep"), " / ", T("listenNext"), " x", Value(quality, "recommendedMonitorGain"), sourceLift);
                string restartHint = BridgeSettingsRestartPending(payload, quality) ? Join(" / ", BridgeSettingsRestartHint(payload, quality)) : "";
                _latencyValue.Text = Join(Nested(payload, "windows_receiver", "audioBufferMs"), T("milliseconds"), " / ", StateLabel(Value(quality, "latencyState")), restartHint, T("underflows"), Nested(payload, "windows_receiver", "playbackUnderflows"), T("frameRatio"), Value(quality, "playbackUnderflowFrameRatio"), T("drops"), Nested(payload, "windows_receiver", "playbackDroppedFrames"), " / ", StateLabel(Value(quality, "continuityState")));
            }
            else
            {
                _ipadValue.Text = Bool(payload, "real_ipad_microphone_data") ? T("realPcm") : T("noRealPcm");
                _volumeValue.Text = Join(Value(payload, "volume_percent"), "%", " RMS ", Value(payload, "rms"));
                _latencyValue.Text = String.IsNullOrWhiteSpace(Value(payload, "latency_ms")) ? T("unavailable") : Value(payload, "latency_ms") + T("milliseconds");
            }
            if (isWebRtc)
            {
                _endpointValue.Text = Bool(payload, "output_device_found") ? Value(payload, "output_device") : T("cableInputMissing");
                string appRoute = TencentMeetingStateLabel(meeting);
                _appsValue.Text = Join(appRoute, " / ", T("aecState"), " ", StateLabel(Value(quality, "echoCancellationState")));
            }
            else
            {
                _endpointValue.Text = Bool(payload, "vbcable_output_found") ? Value(payload, "vbcable_output_device") : T("cableInputMissing");
                if (Bool(payload, "ordinary_apps_can_record_cable_output"))
                {
                    _appsValue.Text = T("cableOutputActive");
                }
                else
                {
                    _appsValue.Text = Bool(payload, "meeting_microphone_found") ? T("selectCableOutput") : T("cableOutputMissing");
                }
            }
            if (isWebRtc)
            {
                string diagnosticPaths = SaveLatestWebRtcDiagnostics(payload);
                string details = BuildQualityDetails(payload, quality);
                if (!String.IsNullOrWhiteSpace(diagnosticPaths))
                {
                    details += "\r\n" + diagnosticPaths;
                }
                _details.Text = details;
            }
            else
            {
                _details.Text = _json.Serialize(payload);
            }
        }

        private void RenderGainTuneStatus(Dictionary<string, object> payload)
        {
            _viewMode = "gain_tune";
            _lastGainTunePayload = payload;
            UpdateRecommendedPrebufferButton(null, null);
            string recommendedGain = Value(payload, "recommendedGain");
            if (!String.IsNullOrWhiteSpace(recommendedGain) && _micGainText != null)
            {
                _micGainText.Text = recommendedGain;
            }
            _serviceValue.Text = Bool(payload, "ok") ? Join(T("tuneGain"), " x", recommendedGain) : T("statusTuneFailed");
            _ipadValue.Text = Value(payload, "base_url");
            _volumeValue.Text = Join(T("nextGain"), " x", recommendedGain);
            _latencyValue.Text = Join(T("nextAction"), ": ", Value(payload, "nextAction"));
            _endpointValue.Text = Value(payload, "outputDevice");
            _appsValue.Text = Bool(payload, "ok") ? T("meetingQualityNeedsTuning") : T("unavailable");
            _details.Text = BuildGainTuneDetails(payload);
        }

        private string BuildGainTuneDetails(Dictionary<string, object> payload)
        {
            StringBuilder builder = new StringBuilder();
            string recommendedGain = Value(payload, "recommendedGain");
            if (String.IsNullOrWhiteSpace(recommendedGain))
            {
                builder.AppendLine(T("gainTuneNoRecommendation"));
            }
            else
            {
                builder.AppendLine(String.Format(T("gainTuneDetails"), recommendedGain));
                builder.AppendLine(Join(T("message"), ": ", Value(payload, "recommendedReason")));
            }
            builder.AppendLine();
            builder.AppendLine("Runs:");
            foreach (Dictionary<string, object> run in DictionaryList(payload, "runs"))
            {
                builder.AppendLine(Join(
                    "- x", Value(run, "gain"),
                    " score ", Value(run, "score"),
                    " / ", Value(run, "readiness"),
                    " / ", Value(run, "qualityAttributionStage"),
                    " / CABLE active ", Value(run, "cableActiveRmsDbfs"), " dBFS",
                    " / peak ", Value(run, "processedPeakDbfs"), " dBFS",
                    " / ", Value(run, "safeMicGainAction")));
                builder.AppendLine(Join("  ", Value(run, "reason")));
                builder.AppendLine(Join("  JSON: ", Value(run, "jsonPath")));
                builder.AppendLine(Join("  WAV: ", Value(run, "capturePath")));
            }
            return builder.ToString();
        }

        private string SaveLatestWebRtcDiagnostics(Dictionary<string, object> payload)
        {
            try
            {
                string captureDir = Path.Combine(_options.ProjectRoot, "captures");
                Directory.CreateDirectory(captureDir);
                string statusPath = Path.Combine(captureDir, "latest_webrtc_status.json");
                string summaryPath = Path.Combine(captureDir, "latest_webrtc_summary.json");
                string textPath = Path.Combine(captureDir, "latest_webrtc_summary.txt");
                Dictionary<string, object> summary = BuildWebRtcSummary(payload);
                File.WriteAllText(statusPath, _json.Serialize(payload), Encoding.UTF8);
                File.WriteAllText(summaryPath, _json.Serialize(summary), Encoding.UTF8);
                File.WriteAllText(textPath, BuildWebRtcTextReport(summary), Encoding.UTF8);
                return "\r\n" + T("latestDiagnosticJson") + ": " + statusPath +
                    "\r\n" + T("latestDiagnosticSummary") + ": " + summaryPath +
                    "\r\n" + T("latestDiagnosticText") + ": " + textPath;
            }
            catch
            {
                return "";
            }
        }

        private Dictionary<string, object> BuildWebRtcSummary(Dictionary<string, object> payload)
        {
            Dictionary<string, object> readiness = DictionaryValue(payload, "readiness");
            Dictionary<string, object> receiver = DictionaryValue(payload, "windows_receiver");
            Dictionary<string, object> loopback = DictionaryValue(payload, "windows_loopback_capture");
            Dictionary<string, object> quality = DictionaryValue(payload, "quality");
            Dictionary<string, object> captures = DictionaryValue(payload, "diagnostic_captures");
            Dictionary<string, object> attribution = DictionaryValue(captures, "qualityAttribution");
            Dictionary<string, object> ipadStatus = DictionaryValue(payload, "ipad_webrtc_status");
            Dictionary<string, object> ipadUpstream = DictionaryValue(payload, "ipad_upstream");
            Dictionary<string, object> summary = new Dictionary<string, object>();
            summary["ok"] = Bool(payload, "ok");
            summary["readiness"] = new Dictionary<string, object>
            {
                {"state", Value(readiness, "state")},
                {"message", Value(readiness, "message")},
                {"nextAction", Value(readiness, "nextAction")},
                {"nextActionMessage", Value(readiness, "nextActionMessage")},
                {"audioRouteReady", Bool(readiness, "audioRouteReady")},
                {"loopbackQualityReady", Bool(readiness, "loopbackQualityReady")},
                {"windowsQualityReady", Bool(readiness, "windowsQualityReady")},
                {"fullQualityReady", Bool(readiness, "fullQualityReady")},
            };
            summary["levels"] = new Dictionary<string, object>
            {
                {"windowsRawRmsDbfs", Value(receiver, "receiverRmsDbfs")},
                {"windowsProcessedRmsDbfs", Value(receiver, "outputRmsDbfs")},
                {"cableOutputRmsDbfs", Value(loopback, "rmsDbfs")},
                {"cableOutputActiveRmsDbfs", Value(loopback, "activeRmsDbfs")},
                {"windowsRawPeakDbfs", Value(receiver, "receiverPeakDbfs")},
                {"windowsProcessedPeakDbfs", Value(receiver, "outputPeakDbfs")},
                {"cableOutputPeakDbfs", Value(loopback, "peakDbfs")},
                {"ipadInputRmsDbfs", Value(ipadStatus, "microphoneInputRmsDbfs")},
                {"ipadProcessedRmsDbfs", Value(ipadStatus, "microphoneProcessedRmsDbfs")},
            };
            summary["quality"] = new Dictionary<string, object>
            {
                {"primaryIssue", Value(quality, "primaryIssue")},
                {"safeMicGainAction", Value(quality, "safeMicGainAction")},
                {"safeMicGainCeiling", Value(quality, "safeMicGainCeiling")},
                {"safeMicGainCanReachTarget", Bool(quality, "safeMicGainCanReachTarget")},
                {"qualityAttributionStage", Value(attribution, "stage")},
            };
            summary["continuity"] = new Dictionary<string, object>
            {
                {"underflows", Value(receiver, "playbackUnderflows")},
                {"drops", Value(receiver, "playbackDroppedFrames")},
                {"packetsReceived", Value(receiver, "audioPacketsReceived")},
                {"upstreamState", Value(ipadUpstream, "microphoneUpstreamState")},
                {"upstreamPacketsSent", Value(ipadUpstream, "microphoneUpstreamPacketsSent")},
                {"upstreamStatsFresh", Bool(ipadUpstream, "microphoneUpstreamStatsFresh")},
            };
            summary["ipadProcessing"] = new Dictionary<string, object>
            {
                {"voiceProcessingEnabled", Bool(ipadStatus, "microphoneVoiceProcessingEnabled")},
                {"echoCancellationEnabled", Bool(ipadStatus, "microphoneEchoCancellationEnabled")},
                {"automaticGainControlEnabled", Bool(ipadStatus, "microphoneAutomaticGainControlEnabled")},
                {"noiseSuppressionEnabled", Bool(ipadStatus, "microphoneNoiseSuppressionEnabled")},
                {"audioSessionMode", Value(ipadStatus, "microphoneAudioSessionMode")},
                {"inputRoute", Value(ipadStatus, "microphoneInputRoute")},
                {"realIpadMicrophone", Bool(ipadStatus, "realIpadMicrophone")},
            };
            return summary;
        }

        private string BuildWebRtcTextReport(Dictionary<string, object> summary)
        {
            Dictionary<string, object> readiness = DictionaryValue(summary, "readiness");
            Dictionary<string, object> levels = DictionaryValue(summary, "levels");
            Dictionary<string, object> quality = DictionaryValue(summary, "quality");
            Dictionary<string, object> continuity = DictionaryValue(summary, "continuity");
            Dictionary<string, object> ipad = DictionaryValue(summary, "ipadProcessing");
            StringBuilder builder = new StringBuilder();
            builder.AppendLine("SensorBridge Microphone diagnostic summary");
            builder.AppendLine(Join("ok: ", Value(summary, "ok")));
            builder.AppendLine(Join("readiness: ", Value(readiness, "state")));
            builder.AppendLine(Join("nextAction: ", Value(readiness, "nextAction")));
            builder.AppendLine(Join("nextActionMessage: ", Value(readiness, "nextActionMessage")));
            builder.AppendLine();
            builder.AppendLine("Levels:");
            builder.AppendLine(Join("- Windows raw RMS: ", Value(levels, "windowsRawRmsDbfs"), " dBFS"));
            builder.AppendLine(Join("- Windows processed RMS: ", Value(levels, "windowsProcessedRmsDbfs"), " dBFS"));
            builder.AppendLine(Join("- CABLE Output RMS: ", Value(levels, "cableOutputRmsDbfs"), " dBFS"));
            builder.AppendLine(Join("- CABLE Output active RMS: ", Value(levels, "cableOutputActiveRmsDbfs"), " dBFS"));
            builder.AppendLine(Join("- iPad input RMS: ", Value(levels, "ipadInputRmsDbfs"), " dBFS"));
            builder.AppendLine(Join("- iPad processed RMS: ", Value(levels, "ipadProcessedRmsDbfs"), " dBFS"));
            builder.AppendLine();
            builder.AppendLine("Quality:");
            builder.AppendLine(Join("- primaryIssue: ", Value(quality, "primaryIssue")));
            builder.AppendLine(Join("- attribution: ", Value(quality, "qualityAttributionStage")));
            builder.AppendLine(Join("- safeMicGainAction: ", Value(quality, "safeMicGainAction")));
            builder.AppendLine(Join("- safeMicGainCeiling: ", Value(quality, "safeMicGainCeiling")));
            builder.AppendLine(Join("- safeMicGainCanReachTarget: ", Value(quality, "safeMicGainCanReachTarget")));
            builder.AppendLine();
            builder.AppendLine("Continuity:");
            builder.AppendLine(Join("- underflows/drops: ", Value(continuity, "underflows"), " / ", Value(continuity, "drops")));
            builder.AppendLine(Join("- packetsReceived: ", Value(continuity, "packetsReceived")));
            builder.AppendLine(Join("- upstream: ", Value(continuity, "upstreamState"), " packets=", Value(continuity, "upstreamPacketsSent"), " fresh=", Value(continuity, "upstreamStatsFresh")));
            builder.AppendLine();
            builder.AppendLine("iPad processing:");
            builder.AppendLine(Join("- voiceProcessing/AEC/AGC/NS: ", Value(ipad, "voiceProcessingEnabled"), " / ", Value(ipad, "echoCancellationEnabled"), " / ", Value(ipad, "automaticGainControlEnabled"), " / ", Value(ipad, "noiseSuppressionEnabled")));
            builder.AppendLine(Join("- session: ", Value(ipad, "audioSessionMode")));
            builder.AppendLine(Join("- inputRoute: ", Value(ipad, "inputRoute")));
            builder.AppendLine(Join("- realIpadMicrophone: ", Value(ipad, "realIpadMicrophone")));
            return builder.ToString();
        }

        private void RenderCaptureStatus(Dictionary<string, object> payload)
        {
            _viewMode = "capture";
            _lastCapturePayload = payload;
            UpdateRecommendedPrebufferButton(null, null);
            bool ok = Bool(payload, "ok");
            Dictionary<string, object> capture = DictionaryValue(payload, "capture");
            _serviceValue.Text = ok ? T("statusRecorded") : T("statusRecordPending");
            _ipadValue.Text = T("cableOutputCapture");
            string monitorClip = Bool(capture, "monitorClipped")
                ? Join(" / ", T("monitorClipping"), " ", Value(capture, "monitorClippedRatio"))
                : "";
            string sourceLift = Value(capture, "levelState") == "low" && DoubleValue(capture, "recommendedSourceLiftDb") > 0
                ? Join(" / ", T("sourceLift"), " ", T("approximately"), Value(capture, "recommendedSourceLiftDb"), " dB")
                : "";
            _volumeValue.Text = Join(Value(capture, "peakAbs"), DbfsSuffix(Value(capture, "peakDbfs")), T("peak"), Value(capture, "rms"), DbfsSuffix(Value(capture, "rmsDbfs")), sourceLift, monitorClip);
            _latencyValue.Text = Join(Value(payload, "duration_seconds"), " ", T("seconds"));
            _endpointValue.Text = Bool(payload, "meeting_input_device_found") ? Value(payload, "meeting_input_device") : T("cableOutputMissing");
            if (Bool(capture, "ordinaryAppsReceiveAudioFromEndpoint"))
            {
                _appsValue.Text = Value(capture, "levelState") == "low" ? T("recordedTooQuiet") : T("recordedNonSilence");
            }
            else
            {
                _appsValue.Text = T("silent");
            }
            _lastRecordingPath = Value(capture, "captureFile");
            _lastPlaybackPath = Value(capture, "playbackFile");
            string monitorWarning = Bool(capture, "monitorClipped")
                ? "\r\n\r\n" + T("monitorClippedWarning") + "\r\n" + T("monitorClipping") + ": " + Value(capture, "monitorClippedSamples") + " / " + Value(capture, "monitorClippedRatio") + DbfsSuffix(Value(capture, "monitorPeakDbfs"))
                : "";
            _details.Text = _json.Serialize(payload) +
                "\r\n\r\n" + T("rawWav") + ": " + _lastRecordingPath +
                "\r\n" + T("playbackWav") + ": " + _lastPlaybackPath +
                monitorWarning;
        }

        private string WebRtcQualityHeadline(Dictionary<string, object> quality, Dictionary<string, object> meeting, Dictionary<string, object> readiness)
        {
            string nextActionLabel = NextActionLabel(Value(readiness, "nextAction"));
            if (!String.IsNullOrWhiteSpace(nextActionLabel) && Value(readiness, "nextAction") != "ready_or_monitor")
            {
                return Join(T("statusWebrtcOk"), " / ", nextActionLabel);
            }
            string meetingState = Value(meeting, "state");
            if (meetingState == "no_loopback_audio" || meetingState == "selectable_unverified_audio" || meetingState == "not_selectable")
            {
                return Join(T("statusWebrtcOk"), " / ", TencentMeetingStateLabel(meeting));
            }
            string primaryIssue = Value(quality, "primaryIssue");
            string primaryIssueLabel = PrimaryIssueLabel(primaryIssue);
            if (!String.IsNullOrWhiteSpace(primaryIssueLabel))
            {
                return Join(T("statusWebrtcOk"), " / ", primaryIssueLabel);
            }
            if (Bool(quality, "fullShortTermReady"))
            {
                return Join(T("statusWebrtcOk"), " / ", T("qualityFullReady"));
            }
            if (Bool(quality, "windowsShortTermReady"))
            {
                string echoState = Value(quality, "echoCancellationState");
                if (!String.IsNullOrWhiteSpace(echoState) && echoState != "verified")
                {
                    return Join(T("statusWebrtcOk"), " / ", T("qualityWindowsReadyAecRisk"));
                }
                return Join(T("statusWebrtcOk"), " / ", T("qualityWindowsReady"));
            }
            if (quality != null && quality.Count > 0)
            {
                return Join(T("statusWebrtcOk"), " / ", T("qualityNeedsTuning"));
            }
            return T("statusWebrtcOk");
        }

        private string BuildQualityDetails(Dictionary<string, object> payload, Dictionary<string, object> quality)
        {
            if (quality == null || quality.Count == 0)
            {
                return _json.Serialize(payload);
            }
            StringBuilder builder = new StringBuilder();
            Dictionary<string, object> meeting = DictionaryValue(payload, "tencent_meeting");
            string primaryIssue = Value(quality, "primaryIssue");
            string primaryIssueText = PrimaryIssueLabel(primaryIssue);
            if (String.IsNullOrWhiteSpace(primaryIssueText)) { primaryIssueText = primaryIssue; }
            string primaryRecommendation = Value(quality, "primaryRecommendation");
            string primaryRecommendationText = PrimaryRecommendationLabel(primaryRecommendation);
            if (String.IsNullOrWhiteSpace(primaryRecommendationText)) { primaryRecommendationText = primaryRecommendation; }
            builder.AppendLine(Join(T("qualityStatus"), ": ", WebRtcQualityHeadline(quality, meeting, DictionaryValue(payload, "readiness"))));
            Dictionary<string, object> readiness = DictionaryValue(payload, "readiness");
            if (readiness.Count > 0)
            {
                builder.AppendLine(Join(T("readiness"), ": ", ReadinessStateLabel(Value(readiness, "state"))));
                builder.AppendLine(Join(T("nextAction"), ": ", NextActionLabel(Value(readiness, "nextAction"))));
                if (!String.IsNullOrWhiteSpace(Value(readiness, "message")))
                {
                    builder.AppendLine(Join(T("message"), ": ", Value(readiness, "message")));
                }
            }
            builder.AppendLine(Join(T("primaryIssue"), ": ", primaryIssueText));
            builder.AppendLine(Join(T("primaryRecommendation"), ": ", primaryRecommendationText));
            builder.AppendLine(Join(T("levelState"), ": ", StateLabel(Value(quality, "levelState"))));
            builder.AppendLine(Join(T("inputLevel"), ": peak ", Value(quality, "inputPeakAbs"), DbfsSuffix(Value(quality, "inputPeakDbfs")), " / RMS ", Nested(payload, "windows_receiver", "receiverRms"), DbfsSuffix(Nested(payload, "windows_receiver", "receiverRmsDbfs"))));
            builder.AppendLine(Join(T("outputLevel"), ": peak ", Value(quality, "outputPeakAbs"), DbfsSuffix(Value(quality, "outputPeakDbfs")), " / RMS ", Value(quality, "outputRms"), DbfsSuffix(Value(quality, "outputRmsDbfs"))));
            Dictionary<string, object> loopback = DictionaryValue(payload, "windows_loopback_capture");
            if (loopback.Count > 0 && Bool(loopback, "enabled"))
            {
                string loopbackLift = DoubleValue(loopback, "recommendedSourceLiftDb") > 0
                    ? Join(" / ", T("sourceLift"), " ", T("approximately"), Value(loopback, "recommendedSourceLiftDb"), " dB")
                    : "";
                builder.AppendLine(Join(T("cableOutputCapture"), ": ", StateLabel(Value(loopback, "levelState")), " / RMS ", Value(loopback, "rmsDbfs"), " dBFS / active ", Value(loopback, "activeRmsDbfs"), " dBFS", loopbackLift));
            }
            Dictionary<string, object> diagnosticCaptures = DictionaryValue(payload, "diagnostic_captures");
            if (Bool(diagnosticCaptures, "enabled"))
            {
                Dictionary<string, object> layers = DictionaryValue(diagnosticCaptures, "layers");
                builder.AppendLine(Join(T("diagnosticCaptures"), ":"));
                AppendDiagnosticCaptureLine(builder, layers, "receiver_raw", T("receiverRaw"));
                AppendDiagnosticCaptureLine(builder, layers, "processed", T("processed"));
                AppendDiagnosticCaptureLine(builder, layers, "cable_output", T("cableOutput"));
                Dictionary<string, object> attribution = DictionaryValue(diagnosticCaptures, "qualityAttribution");
                if (attribution.Count > 0)
                {
                    builder.AppendLine(Join(T("layeredAttribution"), ": ", AttributionStageLabel(Value(attribution, "stage"))));
                    if (!String.IsNullOrWhiteSpace(Value(attribution, "message")))
                    {
                        builder.AppendLine(Join(T("message"), ": ", Value(attribution, "message")));
                    }
                }
            }
            if (Bool(quality, "sustainedOutputTooQuiet"))
            {
                builder.AppendLine(Join(T("outputLevel"), ": ", T("qualitySourceTooQuiet"), " / RMS ", Value(quality, "outputRmsDbfs"), " dBFS"));
            }
            if (Bool(quality, "sourceTooQuietForGainOnly") && DoubleValue(quality, "recommendedSourceLiftDb") > 0)
            {
                builder.AppendLine(Join(T("sourceLift"), ": ", T("approximately"), Value(quality, "recommendedSourceLiftDb"), " dB"));
            }
            builder.AppendLine(Join(T("continuityState"), ": ", StateLabel(Value(quality, "continuityState"))));
            builder.AppendLine(Join(T("latencyState"), ": ", StateLabel(Value(quality, "latencyState")), " / ", Value(quality, "effectivePlaybackLatencyMs"), T("milliseconds")));
            builder.AppendLine(Join(T("buffer"), ": ", Nested(payload, "windows_receiver", "playbackPrebufferMs"), " / ", Nested(payload, "windows_receiver", "playbackMaxBufferMs"), T("milliseconds")));
            if (BridgeSettingsRestartPending(payload, quality))
            {
                builder.AppendLine(BridgeSettingsRestartHint(payload, quality));
            }
            builder.AppendLine(Join(T("underflows"), ": ", Nested(payload, "windows_receiver", "playbackUnderflows"), T("underflowRatio"), Value(quality, "playbackUnderflowRatio"), T("frameRatio"), Value(quality, "playbackUnderflowFrameRatio")));
            builder.AppendLine(Join(T("drops"), ": ", Nested(payload, "windows_receiver", "playbackDroppedFrames"), T("underflowRatio"), Value(quality, "playbackDroppedRatio"), T("overflow"), Value(quality, "playbackOverflowDroppedFrames"), T("catchup"), Value(quality, "playbackCatchupDroppedFrames")));
            builder.AppendLine(Join(T("aecState"), ": ", StateLabel(Value(quality, "echoCancellationState"))));
            builder.AppendLine(Join(T("tencentMeeting"), ": ", TencentMeetingStateLabel(meeting)));
            builder.AppendLine(Join(T("lowCut"), ": ", Value(quality, "lowCutHz"), " Hz"));
            builder.AppendLine(Join(T("noiseGate"), ": ", Value(quality, "noiseGateThreshold"), " / ", T("gateGain"), " ", Value(quality, "noiseGateGain")));
            builder.AppendLine(Join(T("recommendedGain"), ": ", Value(quality, "recommendedMicGain"), " / ", T("nextGain"), " ", Value(quality, "recommendedMicGainStep")));
            builder.AppendLine(Join(T("safeGain"), ": ", GainActionLabel(Value(quality, "safeMicGainAction")), " / ceiling ", Value(quality, "safeMicGainCeiling"), " / RMS ", Value(quality, "estimatedSafeGainRmsDbfs"), " dBFS"));
            builder.AppendLine(Join(T("recommendedListenGain"), ": ", Value(quality, "recommendedMonitorGain")));
            builder.AppendLine(Join(T("recommendedPrebuffer"), ": ", Value(quality, "recommendedPlaybackPrebufferMs"), T("milliseconds")));
            if (Bool(quality, "gainOnlyLikelyToAmplifyNoise"))
            {
                builder.AppendLine(Join(T("gainRisk"), ": ", T("gainRiskNoise")));
            }

            List<string> recommendations = LocalizedQualityRecommendations(quality, meeting);
            if (recommendations.Count > 0)
            {
                builder.AppendLine();
                builder.AppendLine(T("recommendations") + ":");
                foreach (string recommendation in recommendations)
                {
                    builder.AppendLine("- " + recommendation);
                }
            }

            builder.AppendLine();
            builder.AppendLine(_json.Serialize(payload));
            return builder.ToString();
        }

        private void AppendDiagnosticCaptureLine(StringBuilder builder, Dictionary<string, object> layers, string key, string label)
        {
            Dictionary<string, object> layer = DictionaryValue(layers, key);
            if (layer.Count == 0)
            {
                return;
            }
            builder.AppendLine(Join("  ", label, ": ", T("file"), " ", Value(layer, "path"), " / frames ", Value(layer, "frames")));
        }

        private List<string> LocalizedQualityRecommendations(Dictionary<string, object> quality, Dictionary<string, object> meeting)
        {
            List<string> recommendations = new List<string>();
            string levelState = Value(quality, "levelState");
            string continuityState = Value(quality, "continuityState");
            string echoState = Value(quality, "echoCancellationState");
            if (levelState == "low" || levelState == "silent")
            {
                recommendations.Add(Bool(quality, "sourceTooQuietForGainOnly") ? T("recMoveCloser") : T("recRaiseGain"));
            }
            else if (levelState == "too_hot")
            {
                recommendations.Add(T("recLowerGain"));
            }
            if (!String.IsNullOrWhiteSpace(continuityState) && continuityState != "ok")
            {
                recommendations.Add(T("recContinuity"));
            }
            else if (Value(quality, "latencyState") == "high_latency")
            {
                recommendations.Add(T("recLatency"));
            }
            if (DoubleValue(quality, "noiseGateActivityRatio") > 0.3)
            {
                recommendations.Add(T("recGate"));
            }
            if (DoubleValue(quality, "outputLimitedSamples") > 0)
            {
                recommendations.Add(T("recLimiter"));
            }
            if (Bool(quality, "windowsShortTermReady") && !String.IsNullOrWhiteSpace(echoState) && echoState != "verified")
            {
                recommendations.Add(T("recHeadset"));
            }
            string meetingState = Value(meeting, "state");
            if (meetingState == "selectable_unverified_audio")
            {
                recommendations.Add(T("recMeetingVerify"));
            }
            else if (meetingState == "no_loopback_audio")
            {
                recommendations.Add(T("recMeetingNoAudio"));
            }
            if (meetingState == "verified_audio" && !Bool(meeting, "loopbackQualityReadyForTencentMeeting"))
            {
                recommendations.Add(T("recMeetingLoopbackTooQuiet"));
            }
            if (!String.IsNullOrWhiteSpace(echoState) && echoState != "verified")
            {
                recommendations.Add(T("recAec"));
            }
            return recommendations;
        }

        private string StateLabel(string state)
        {
            if (state == "ok") { return T("stateOk"); }
            if (state == "low") { return T("stateLow"); }
            if (state == "silent") { return T("stateSilent"); }
            if (state == "too_hot") { return T("stateTooHot"); }
            if (state == "dropping") { return T("stateDropping"); }
            if (state == "underflowing") { return T("stateUnderflowing"); }
            if (state == "high_latency") { return T("stateHighLatency"); }
            if (state == "buffered") { return T("stateBuffered"); }
            if (state == "low_latency") { return T("stateLowLatency"); }
            if (state == "verified") { return T("stateVerified"); }
            if (state == "disabled") { return T("stateDisabled"); }
            if (state == "unverified") { return T("stateUnverified"); }
            return String.IsNullOrWhiteSpace(state) ? T("unavailable") : state;
        }

        private string ReadinessStateLabel(string state)
        {
            if (state == "full_quality_ready") { return T("readinessFullQuality"); }
            if (state == "windows_quality_ready") { return T("readinessWindowsQuality"); }
            if (state == "route_ready_quality_not_ready") { return T("readinessRouteOnly"); }
            if (state == "transport_ready_route_not_verified") { return T("readinessTransportOnly"); }
            if (state == "not_ready") { return T("readinessNotReady"); }
            return String.IsNullOrWhiteSpace(state) ? T("unavailable") : state;
        }

        private string NextActionLabel(string action)
        {
            if (action == "fix_ipad_source") { return T("nextActionFixIpad"); }
            if (action == "fix_meeting_loopback_level") { return T("nextActionFixLoopback"); }
            if (action == "lower_windows_gain") { return T("nextActionLowerGain"); }
            if (action == "raise_windows_gain_modestly") { return T("nextActionRaiseGain"); }
            if (action == "verify_cable_route") { return T("nextActionVerifyRoute"); }
            if (action == "check_transport") { return T("nextActionCheckTransport"); }
            if (action == "stabilize_buffer") { return T("nextActionStabilize"); }
            if (action == "verify_aec") { return T("nextActionVerifyAec"); }
            if (action == "ready_or_monitor") { return T("nextActionReady"); }
            return String.IsNullOrWhiteSpace(action) ? T("unavailable") : action;
        }

        private string AttributionStageLabel(string stage)
        {
            if (stage == "ipad_source_too_quiet") { return T("attributionIpadQuiet"); }
            if (stage == "ipad_or_webrtc_silent") { return T("attributionIpadSilent"); }
            if (stage == "windows_processing_too_hot") { return T("attributionWindowsHot"); }
            if (stage == "windows_processing_loss") { return T("attributionWindowsLoss"); }
            if (stage == "cable_loopback_silent") { return T("attributionCableSilent"); }
            if (stage == "cable_loopback_loss") { return T("attributionCableLoss"); }
            if (stage == "route_level_too_low") { return T("attributionRouteLow"); }
            if (stage == "audio_level_route_ok") { return T("attributionRouteOk"); }
            return String.IsNullOrWhiteSpace(stage) ? T("unavailable") : stage;
        }

        private string GainActionLabel(string action)
        {
            if (action == "hold_source_first") { return T("gainActionHoldSource"); }
            if (action == "raise_modestly") { return T("gainActionRaise"); }
            if (action == "lower_gain") { return T("gainActionLower"); }
            if (action == "keep_gain") { return T("gainActionKeep"); }
            return String.IsNullOrWhiteSpace(action) ? T("unavailable") : action;
        }

        private string PrimaryIssueLabel(string issue)
        {
            if (issue == "none" || String.IsNullOrWhiteSpace(issue)) { return ""; }
            if (issue == "source_too_quiet") { return T("qualitySourceTooQuiet"); }
            if (issue == "silent") { return T("qualitySilent"); }
            if (issue == "level_too_hot") { return T("qualityLevelTooHot"); }
            if (issue == "continuity_unstable") { return T("qualityContinuityUnstable"); }
            if (issue == "limiter_active") { return T("qualityLimiterActive"); }
            if (issue == "high_latency") { return T("qualityHighLatency"); }
            if (issue == "aec_unverified") { return T("qualityAecUnverified"); }
            if (issue == "level_low") { return T("stateLow"); }
            return issue;
        }

        private string PrimaryRecommendationLabel(string recommendation)
        {
            if (recommendation == "none" || String.IsNullOrWhiteSpace(recommendation)) { return ""; }
            if (recommendation == "move_ipad_closer") { return T("recMoveCloser"); }
            if (recommendation == "check_ipad_microphone") { return T("recCheckIpadMic"); }
            if (recommendation == "lower_mic_gain") { return T("recLowerGain"); }
            if (recommendation == "raise_prebuffer_or_restart_bridge") { return T("recContinuity"); }
            if (recommendation == "lower_mic_gain_if_harsh") { return T("recLimiter"); }
            if (recommendation == "lower_prebuffer_after_stable") { return T("recLatency"); }
            if (recommendation == "use_headphones_or_enable_ipad_aec") { return T("recHeadset"); }
            if (recommendation == "move_ipad_closer_or_raise_gain_modestly") { return T("recRaiseGain"); }
            return recommendation;
        }

        private string TencentMeetingStateLabel(Dictionary<string, object> status)
        {
            string state = Value(status, "state");
            if (state == "verified_audio")
            {
                if (Bool(status, "fullQualityReadyForTencentMeeting")) { return T("meetingQualityReady"); }
                if (!Bool(status, "loopbackQualityReadyForTencentMeeting")) { return T("meetingLoopbackTooQuiet"); }
                if (!Bool(status, "windowsQualityReadyForTencentMeeting")) { return T("meetingQualityNeedsTuning"); }
                if (Value(status, "qualityPrimaryIssue") == "aec_unverified") { return T("meetingEchoRisk"); }
                return T("meetingAudioVerified");
            }
            if (state == "selectable_unverified_audio") { return T("meetingAudioUnverified"); }
            if (state == "no_loopback_audio") { return T("meetingNoLoopbackAudio"); }
            if (state == "not_selectable") { return T("cableOutputMissing"); }
            return T("unavailable");
        }

        private static string Value(Dictionary<string, object> root, string key)
        {
            object value;
            return root != null && root.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : "";
        }

        private static bool Bool(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value) || value == null)
            {
                return false;
            }
            if (value is bool)
            {
                return (bool)value;
            }
            bool parsed;
            return Boolean.TryParse(Convert.ToString(value), out parsed) && parsed;
        }

        private static double DoubleValue(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value) || value == null)
            {
                return 0.0;
            }
            try
            {
                return Convert.ToDouble(value, CultureInfo.InvariantCulture);
            }
            catch
            {
                double parsed;
                return Double.TryParse(Convert.ToString(value), NumberStyles.Float, CultureInfo.InvariantCulture, out parsed) ? parsed : 0.0;
            }
        }

        private static int IntValue(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value) || value == null)
            {
                return -1;
            }
            try
            {
                return Convert.ToInt32(value, CultureInfo.InvariantCulture);
            }
            catch
            {
                int parsed;
                return Int32.TryParse(Convert.ToString(value), NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed) ? parsed : -1;
            }
        }

        private static List<Dictionary<string, object>> DictionaryList(Dictionary<string, object> root, string key)
        {
            List<Dictionary<string, object>> values = new List<Dictionary<string, object>>();
            object raw;
            if (root == null || !root.TryGetValue(key, out raw) || raw == null)
            {
                return values;
            }
            IEnumerable items = raw as IEnumerable;
            if (items == null || raw is string)
            {
                return values;
            }
            foreach (object item in items)
            {
                Dictionary<string, object> dictionary = item as Dictionary<string, object>;
                if (dictionary != null)
                {
                    values.Add(dictionary);
                }
            }
            return values;
        }

        private static Dictionary<string, object> DictionaryValue(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value) || value == null)
            {
                return new Dictionary<string, object>();
            }
            Dictionary<string, object> dictionary = value as Dictionary<string, object>;
            return dictionary ?? new Dictionary<string, object>();
        }

        private static string Nested(Dictionary<string, object> root, string parentKey, string key)
        {
            object parent;
            if (root == null || !root.TryGetValue(parentKey, out parent) || parent == null) { return ""; }
            Dictionary<string, object> dictionary = parent as Dictionary<string, object>;
            if (dictionary == null) { return ""; }
            return Value(dictionary, key);
        }

        private static string DbfsSuffix(string value)
        {
            return String.IsNullOrWhiteSpace(value) ? "" : " (" + value + " dBFS)";
        }

        private static bool BoolNested(Dictionary<string, object> root, string parentKey, string key)
        {
            object parent;
            if (root == null || !root.TryGetValue(parentKey, out parent) || parent == null) { return false; }
            Dictionary<string, object> dictionary = parent as Dictionary<string, object>;
            return dictionary != null && Bool(dictionary, key);
        }

        private static string Join(params string[] parts)
        {
            StringBuilder builder = new StringBuilder();
            foreach (string part in parts)
            {
                if (!String.IsNullOrWhiteSpace(part))
                {
                    builder.Append(part);
                }
            }
            return builder.Length == 0 ? "-" : builder.ToString();
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? "").Replace("\"", "\\\"") + "\"";
        }

        private static string NumericOption(TextBox textBox, string fallback, double minimum, double maximum)
        {
            double value;
            string text = textBox == null ? "" : textBox.Text;
            if (!Double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) &&
                !Double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value))
            {
                value = Double.Parse(fallback, CultureInfo.InvariantCulture);
            }
            value = Math.Max(minimum, Math.Min(maximum, value));
            return value.ToString("0.###", CultureInfo.InvariantCulture);
        }

        private static double TextBoxDouble(TextBox textBox, double fallback)
        {
            double value;
            string text = textBox == null ? "" : textBox.Text;
            if (!Double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) &&
                !Double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value))
            {
                return fallback;
            }
            return value;
        }

        private static string ResolvePython()
        {
            if (CommandWorks("py", "-3 --version"))
            {
                return "py";
            }
            if (CommandWorks("python", "--version"))
            {
                return "python";
            }
            throw new InvalidOperationException("No usable Python launcher was found. Install Python 3 or repair the py launcher.");
        }

        private static bool CommandWorks(string fileName, string arguments)
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = fileName;
                info.Arguments = arguments;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.RedirectStandardOutput = true;
                info.RedirectStandardError = true;
                using (Process process = Process.Start(info))
                {
                    process.WaitForExit(3000);
                    return process.ExitCode == 0;
                }
            }
            catch
            {
                return false;
            }
        }

        private static string ExtractJson(string output)
        {
            int start = output.IndexOf('{');
            int end = output.LastIndexOf('}');
            if (start < 0 || end <= start)
            {
                throw new InvalidOperationException("No JSON object found in bridge.py output.");
            }
            return output.Substring(start, end - start + 1);
        }

        private void Ui(MethodInvoker action)
        {
            if (IsDisposed)
            {
                return;
            }
            if (InvokeRequired)
            {
                BeginInvoke(action);
            }
            else
            {
                action();
            }
        }
    }
}
