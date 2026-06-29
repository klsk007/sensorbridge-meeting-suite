using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace SensorBridge.Meeting.App
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            bool createdNew;
            using (Mutex mutex = new Mutex(true, "SensorBridge.Meeting.App.SingleInstance", out createdNew))
            {
                if (!createdNew)
                {
                    MessageBox.Show("SensorBridge Meeting Suite is already running.", "SensorBridge Meeting Suite", MessageBoxButtons.OK, MessageBoxIcon.Information);
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
        public string IpadBaseUrl = "http://192.168.0.24:27180";
        public int CameraPort = 8765;
        public bool StartCamera = true;
        public bool StartMicrophone = true;
        public bool StartSpeaker = true;
        public string Language = "en";
        public string MicrophoneOutputDevice = "CABLE Output";
        public string SpeakerCaptureDevice = "CABLE Input";

        public static AppOptions Parse(string[] args)
        {
            AppOptions options = new AppOptions();
            for (int i = 0; i < args.Length; i++)
            {
                string value = i + 1 < args.Length ? args[i + 1] : "";
                if (args[i] == "--project-root" && value.Length > 0) { options.ProjectRoot = Path.GetFullPath(value); i++; }
                else if (args[i] == "--ipad-base-url" && value.Length > 0) { options.IpadBaseUrl = value; i++; }
                else if (args[i] == "--language" && value.Length > 0) { options.Language = NormalizeLanguage(value); i++; }
                else if ((args[i] == "--meeting-microphone-device" || args[i] == "--microphone-output-device" || args[i] == "--cable-input-device") && value.Length > 0) { options.MicrophoneOutputDevice = value; i++; }
                else if ((args[i] == "--meeting-speaker-device" || args[i] == "--speaker-capture-device") && value.Length > 0) { options.SpeakerCaptureDevice = value; i++; }
                else if (args[i] == "--camera-port" && value.Length > 0)
                {
                    int parsed;
                    if (Int32.TryParse(value, out parsed)) { options.CameraPort = parsed; }
                    i++;
                }
                else if (args[i] == "--no-camera") { options.StartCamera = false; }
                else if (args[i] == "--no-microphone") { options.StartMicrophone = false; }
                else if (args[i] == "--no-speaker") { options.StartSpeaker = false; }
            }
            return options;
        }

        private static string NormalizeLanguage(string value)
        {
            return "en";
        }

        private static string ResolveDefaultProjectRoot()
        {
            string current = AppDomain.CurrentDomain.BaseDirectory;
            for (int depth = 0; depth < 10 && !String.IsNullOrEmpty(current); depth++)
            {
                if (File.Exists(Path.Combine(current, "meeting-suite", "Start-SensorBridgeMeeting.ps1")) &&
                    Directory.Exists(Path.Combine(current, "sensorbridge-windows-clean")) &&
                    Directory.Exists(Path.Combine(current, "sensorbridge-microphone-windows")) &&
                    Directory.Exists(Path.Combine(current, "sensorbridge-speaker-windows")))
                {
                    return Path.GetFullPath(current);
                }
                DirectoryInfo parent = Directory.GetParent(current);
                if (parent == null) { break; }
                current = parent.FullName;
            }
            return Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", ".."));
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly AppOptions _options;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();
        private readonly List<int> _childProcessIds = new List<int>();
        private string _language;
        private Label _titleLabel;
        private Label _subtitleLabel;
        private Label _urlLabel;
        private Label _microphoneOutputLabel;
        private Label _speakerCaptureLabel;
        private ComboBox _microphoneOutputCombo;
        private ComboBox _speakerCaptureCombo;
        private TextBox _baseUrlText;
        private CheckBox _cameraCheck;
        private CheckBox _microphoneCheck;
        private CheckBox _speakerCheck;
        private Button _startButton;
        private Button _stopButton;
        private Button _checkButton;
        private Button _docsButton;
        private Button _refreshAudioButton;
        private Button _talkButton;
        private Label _suiteTitleLabel;
        private Label _cameraTitleLabel;
        private Label _microphoneTitleLabel;
        private Label _speakerTitleLabel;
        private Label _suiteStatus;
        private Label _cameraStatus;
        private Label _microphoneStatus;
        private Label _speakerStatus;
        private Label _meetingDevices;
        private TextBox _details;
        private NotifyIcon _trayIcon;
        private ContextMenuStrip _trayMenu;
        private ToolStripMenuItem _trayOpenItem;
        private ToolStripMenuItem _trayStartItem;
        private ToolStripMenuItem _trayStopItem;
        private ToolStripMenuItem _trayCheckItem;
        private ToolStripMenuItem _trayExitItem;
        private ToolTip _toolTip;
        private readonly string _pushToTalkControlPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "SensorBridge",
            "meeting",
            "push_to_talk.json");
        private bool _allowExit;
        private bool _stopInProgress;
        private bool _talkButtonPressed;
        private string _suiteStateKey = "not_started";
        private string _cameraStatusKey = "";
        private string _microphoneStatusKey = "";
        private string _speakerStatusKey = "";
        private string _cameraStatusValue = "";
        private string _microphoneStatusValue = "";
        private string _speakerStatusValue = "";

        private sealed class AudioDeviceLists
        {
            public readonly List<string> Inputs = new List<string>();
            public readonly List<string> Outputs = new List<string>();
        }

        private sealed class ProcessCaptureResult
        {
            public int ExitCode;
            public string Output = "";
            public string Error = "";
        }

        public MainForm(AppOptions options)
        {
            _options = options;
            _language = options.Language;
            _json.MaxJsonLength = Int32.MaxValue;
            Text = "SensorBridge Meeting Suite";
            MinimumSize = new Size(1120, 680);
            Size = new Size(1180, 760);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(245, 247, 250);
            Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            BuildLayout();
            BuildTrayIcon();
            ApplyLanguage();
            RenderIdle();
        }

        private void BuildLayout()
        {
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.RowCount = 5;
            root.ColumnCount = 1;
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 78));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 160));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 128));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Controls.Add(root);

            Panel header = new Panel();
            header.Dock = DockStyle.Fill;
            header.BackColor = Color.FromArgb(27, 92, 108);
            header.Padding = new Padding(22, 12, 22, 8);
            root.Controls.Add(header, 0, 0);

            _titleLabel = new Label();
            _titleLabel.ForeColor = Color.White;
            _titleLabel.Font = new Font("Segoe UI Semibold", 19F, FontStyle.Bold, GraphicsUnit.Point);
            _titleLabel.AutoSize = true;
            _titleLabel.Location = new Point(0, 4);
            header.Controls.Add(_titleLabel);

            _subtitleLabel = new Label();
            _subtitleLabel.ForeColor = Color.FromArgb(220, 243, 240);
            _subtitleLabel.AutoSize = true;
            _subtitleLabel.Location = new Point(2, 46);
            header.Controls.Add(_subtitleLabel);

            Panel toolbar = new Panel();
            toolbar.Dock = DockStyle.Fill;
            toolbar.BackColor = Color.White;
            toolbar.Padding = new Padding(20, 10, 20, 8);
            root.Controls.Add(toolbar, 0, 1);

            TableLayoutPanel toolbarGrid = new TableLayoutPanel();
            toolbarGrid.Dock = DockStyle.Fill;
            toolbarGrid.ColumnCount = 1;
            toolbarGrid.RowCount = 3;
            toolbarGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
            toolbarGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
            toolbarGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            toolbar.Controls.Add(toolbarGrid);

            FlowLayoutPanel deviceRow = new FlowLayoutPanel();
            deviceRow.Dock = DockStyle.Fill;
            deviceRow.WrapContents = false;
            deviceRow.AutoScroll = true;
            deviceRow.FlowDirection = FlowDirection.LeftToRight;
            toolbarGrid.Controls.Add(deviceRow, 0, 0);

            _urlLabel = AddInlineLabel(deviceRow);

            _baseUrlText = new TextBox();
            _baseUrlText.Text = _options.IpadBaseUrl;
            _baseUrlText.Width = 245;
            _baseUrlText.Margin = new Padding(0, 6, 16, 0);
            deviceRow.Controls.Add(_baseUrlText);

            _cameraCheck = AddCheck(deviceRow, _options.StartCamera);
            _microphoneCheck = AddCheck(deviceRow, _options.StartMicrophone);
            _speakerCheck = AddCheck(deviceRow, _options.StartSpeaker);
            _microphoneCheck.CheckedChanged += delegate
            {
                if (!_microphoneCheck.Checked) { SetPushToTalk(false); }
                UpdateTalkButtonEnabled();
            };

            FlowLayoutPanel audioRow = new FlowLayoutPanel();
            audioRow.Dock = DockStyle.Fill;
            audioRow.WrapContents = false;
            audioRow.AutoScroll = false;
            audioRow.FlowDirection = FlowDirection.LeftToRight;
            toolbarGrid.Controls.Add(audioRow, 0, 1);

            _microphoneOutputLabel = AddInlineLabel(audioRow);
            _microphoneOutputCombo = AddDeviceCombo(audioRow, _options.MicrophoneOutputDevice);
            _speakerCaptureLabel = AddInlineLabel(audioRow);
            _speakerCaptureCombo = AddDeviceCombo(audioRow, _options.SpeakerCaptureDevice);
            _refreshAudioButton = AddButton(audioRow, delegate { RefreshAudioDevices(true); });
            _refreshAudioButton.Width = 150;

            FlowLayoutPanel actionRow = new FlowLayoutPanel();
            actionRow.Dock = DockStyle.Fill;
            actionRow.WrapContents = false;
            actionRow.AutoScroll = true;
            actionRow.FlowDirection = FlowDirection.LeftToRight;
            toolbarGrid.Controls.Add(actionRow, 0, 2);

            _startButton = AddButton(actionRow, delegate { StartSuite(); });
            _stopButton = AddButton(actionRow, delegate { StopSuite(); });
            _checkButton = AddButton(actionRow, delegate { RunReadinessCheck(); });
            _docsButton = AddButton(actionRow, delegate { OpenSetupDoc(); });
            _talkButton = AddButton(actionRow, delegate { });
            _talkButton.Width = 130;
            _talkButton.UseVisualStyleBackColor = false;
            _talkButton.MouseDown += delegate(object sender, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Left) { SetPushToTalk(true); }
            };
            _talkButton.MouseUp += delegate { SetPushToTalk(false); };
            _talkButton.MouseLeave += delegate
            {
                if (_talkButtonPressed) { SetPushToTalk(false); }
            };
            _talkButton.KeyDown += delegate(object sender, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter)
                {
                    SetPushToTalk(true);
                    e.Handled = true;
                }
            };
            _talkButton.KeyUp += delegate(object sender, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter)
                {
                    SetPushToTalk(false);
                    e.Handled = true;
                }
            };

            TableLayoutPanel cards = new TableLayoutPanel();
            cards.Dock = DockStyle.Fill;
            cards.Padding = new Padding(18, 12, 18, 10);
            cards.ColumnCount = 4;
            cards.RowCount = 1;
            for (int i = 0; i < 4; i++) { cards.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25)); }
            root.Controls.Add(cards, 0, 2);

            _suiteStatus = AddCard(cards, 0, out _suiteTitleLabel);
            _cameraStatus = AddCard(cards, 1, out _cameraTitleLabel);
            _microphoneStatus = AddCard(cards, 2, out _microphoneTitleLabel);
            _speakerStatus = AddCard(cards, 3, out _speakerTitleLabel);

            Panel meetingPanel = new Panel();
            meetingPanel.Dock = DockStyle.Fill;
            meetingPanel.BackColor = Color.FromArgb(232, 240, 243);
            meetingPanel.Padding = new Padding(22, 10, 22, 10);
            root.Controls.Add(meetingPanel, 0, 3);

            _meetingDevices = new Label();
            _meetingDevices.Dock = DockStyle.Fill;
            _meetingDevices.TextAlign = ContentAlignment.MiddleLeft;
            _meetingDevices.Font = new Font("Segoe UI Semibold", 9.5F, FontStyle.Bold, GraphicsUnit.Point);
            meetingPanel.Controls.Add(_meetingDevices);

            _details = new TextBox();
            _details.Dock = DockStyle.Fill;
            _details.Multiline = true;
            _details.ReadOnly = true;
            _details.ScrollBars = ScrollBars.Both;
            _details.BackColor = Color.White;
            _details.Font = new Font("Consolas", 9F, FontStyle.Regular, GraphicsUnit.Point);
            root.Controls.Add(_details, 0, 4);

            _toolTip = new ToolTip();
        }

        private static Label AddInlineLabel(Control parent)
        {
            Label label = new Label();
            label.AutoSize = true;
            label.Margin = new Padding(0, 9, 8, 0);
            parent.Controls.Add(label);
            return label;
        }

        private static CheckBox AddCheck(Control parent, bool isChecked)
        {
            CheckBox check = new CheckBox();
            check.Checked = isChecked;
            check.AutoSize = true;
            check.Margin = new Padding(0, 8, 16, 0);
            parent.Controls.Add(check);
            return check;
        }

        private static ComboBox AddDeviceCombo(Control parent, string text)
        {
            ComboBox combo = new ComboBox();
            combo.DropDownStyle = ComboBoxStyle.DropDown;
            combo.Width = 245;
            combo.Margin = new Padding(0, 5, 18, 0);
            combo.Items.Add(text);
            combo.Text = text;
            parent.Controls.Add(combo);
            return combo;
        }

        private static Button AddButton(Control parent, EventHandler click)
        {
            Button button = new Button();
            button.Width = 190;
            button.Height = 34;
            button.Margin = new Padding(0, 6, 10, 0);
            button.Click += click;
            parent.Controls.Add(button);
            return button;
        }

        private static Label AddCard(TableLayoutPanel grid, int column, out Label titleLabel)
        {
            Panel card = new Panel();
            card.Dock = DockStyle.Fill;
            card.Margin = new Padding(6);
            card.BackColor = Color.White;
            grid.Controls.Add(card, column, 0);

            Label title = new Label();
            title.Location = new Point(14, 12);
            title.Size = new Size(190, 18);
            title.ForeColor = Color.FromArgb(86, 99, 112);
            title.Font = new Font("Segoe UI Semibold", 8.5F, FontStyle.Bold, GraphicsUnit.Point);
            card.Controls.Add(title);
            titleLabel = title;

            Label value = new Label();
            value.Text = "-";
            value.Location = new Point(14, 42);
            value.Size = new Size(190, 42);
            value.AutoEllipsis = true;
            value.ForeColor = Color.FromArgb(24, 38, 50);
            card.Controls.Add(value);
            card.Resize += delegate
            {
                int width = Math.Max(80, card.ClientSize.Width - 28);
                title.Width = width;
                value.Width = width;
            };
            return value;
        }

        private void BuildTrayIcon()
        {
            _trayMenu = new ContextMenuStrip();
            _trayOpenItem = new ToolStripMenuItem("", null, delegate { RestoreFromTray(); });
            _trayStartItem = new ToolStripMenuItem("", null, delegate { RestoreFromTray(); StartSuite(); });
            _trayStopItem = new ToolStripMenuItem("", null, delegate { StopSuite(); });
            _trayCheckItem = new ToolStripMenuItem("", null, delegate { RestoreFromTray(); RunReadinessCheck(); });
            _trayExitItem = new ToolStripMenuItem("", null, delegate { _allowExit = true; Close(); });
            _trayMenu.Items.Add(_trayOpenItem);
            _trayMenu.Items.Add(_trayStartItem);
            _trayMenu.Items.Add(_trayStopItem);
            _trayMenu.Items.Add(_trayCheckItem);
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add(_trayExitItem);

            _trayIcon = new NotifyIcon();
            _trayIcon.Text = "SensorBridge Meeting Suite";
            _trayIcon.Icon = Icon == null ? SystemIcons.Application : Icon;
            _trayIcon.ContextMenuStrip = _trayMenu;
            _trayIcon.Visible = true;
            _trayIcon.DoubleClick += delegate { RestoreFromTray(); };
        }

        private void ApplyLanguage()
        {
            Text = T("app_title");
            if (_titleLabel != null) { _titleLabel.Text = T("app_title"); }
            if (_subtitleLabel != null) { _subtitleLabel.Text = T("subtitle"); }
            if (_urlLabel != null) { _urlLabel.Text = T("url_label"); }
            if (_microphoneOutputLabel != null) { _microphoneOutputLabel.Text = T("microphone_output_label"); }
            if (_speakerCaptureLabel != null) { _speakerCaptureLabel.Text = T("speaker_capture_label"); }
            if (_cameraCheck != null) { _cameraCheck.Text = T("camera_check"); }
            if (_microphoneCheck != null) { _microphoneCheck.Text = T("microphone_check"); }
            if (_speakerCheck != null) { _speakerCheck.Text = T("speaker_check"); }
            if (_startButton != null) { _startButton.Text = T("btn_start"); _startButton.Width = _language == "zh" ? 220 : 220; }
            if (_stopButton != null) { _stopButton.Text = T("btn_stop"); _stopButton.Width = _language == "zh" ? 160 : 190; }
            if (_checkButton != null) { _checkButton.Text = T("btn_check"); _checkButton.Width = _language == "zh" ? 150 : 190; }
            if (_docsButton != null) { _docsButton.Text = T("btn_setup"); _docsButton.Width = _language == "zh" ? 220 : 230; }
            if (_refreshAudioButton != null) { _refreshAudioButton.Text = T("btn_refresh_audio"); _refreshAudioButton.Width = _language == "zh" ? 160 : 185; }
            UpdateTalkButtonVisual();
            if (_suiteTitleLabel != null) { _suiteTitleLabel.Text = T("card_suite"); }
            if (_cameraTitleLabel != null) { _cameraTitleLabel.Text = T("card_camera"); }
            if (_microphoneTitleLabel != null) { _microphoneTitleLabel.Text = T("card_microphone"); }
            if (_speakerTitleLabel != null) { _speakerTitleLabel.Text = T("card_speaker"); }
            if (_meetingDevices != null) { _meetingDevices.Text = T("meeting_devices"); }
            if (_trayIcon != null) { _trayIcon.Text = T("app_title"); }
            if (_trayOpenItem != null) { _trayOpenItem.Text = T("tray_open"); }
            if (_trayStartItem != null) { _trayStartItem.Text = T("tray_start"); }
            if (_trayStopItem != null) { _trayStopItem.Text = T("tray_stop"); }
            if (_trayCheckItem != null) { _trayCheckItem.Text = T("tray_check"); }
            if (_trayExitItem != null) { _trayExitItem.Text = T("tray_exit"); }
            if (_toolTip != null)
            {
                _toolTip.SetToolTip(_startButton, T("tip_start"));
                _toolTip.SetToolTip(_stopButton, T("tip_stop"));
                _toolTip.SetToolTip(_checkButton, T("tip_check"));
                _toolTip.SetToolTip(_docsButton, T("tip_setup"));
                _toolTip.SetToolTip(_microphoneOutputCombo, T("tip_microphone_output"));
                _toolTip.SetToolTip(_speakerCaptureCombo, T("tip_speaker_capture"));
                _toolTip.SetToolTip(_refreshAudioButton, T("tip_refresh_audio"));
                _toolTip.SetToolTip(_talkButton, T("tip_talk"));
            }
            RefreshStatusLabels();
        }

        private string T(string key)
        {
            if (_language == "zh")
            {
                switch (key)
                {
                    case "app_title": return "SensorBridge 会议套件";
                    case "subtitle": return "把 iPhone/iPad 变成会议摄像头、麦克风和扬声器";
                    case "url_label": return "iPhone/iPad 地址";
                    case "language_label": return "界面语言";
                    case "microphone_output_label": return "会议麦克风选择";
                    case "speaker_capture_label": return "会议扬声器选择";
                    case "camera_check": return "摄像头";
                    case "microphone_check": return "麦克风";
                    case "speaker_check": return "扬声器";
                    case "btn_start": return "按勾选项启动/重启";
                    case "btn_stop": return "停止并清理进程";
                    case "btn_check": return "检查设备环境";
                    case "btn_setup": return "打开腾讯会议设置说明";
                    case "btn_refresh_audio": return "刷新音频设备";
                    case "btn_audio_refreshing": return "正在刷新...";
                    case "btn_talk": return "按住发言";
                    case "btn_talking": return "正在发言";
                    case "tip_start": return "先清理上一轮桥接进程，再按当前勾选项启动摄像头、麦克风、扬声器。";
                    case "tip_stop": return "停止本项目启动的桥接进程，并清理虚拟摄像头发送器。";
                    case "tip_check": return "检查 iPhone/iPad 是否在线，以及当前选择的 Windows 虚拟摄像头和音频设备是否存在。";
                    case "tip_setup": return "打开腾讯会议设备选择说明，查看应该选择哪些摄像头、麦克风和扬声器。";
                    case "tip_language": return "切换界面显示语言，不影响设备桥接。";
                    case "tip_microphone_output": return "这里按会议软件里看到的麦克风设备选择，默认选 CABLE Output。程序会自动把 iPhone/iPad 麦克风写入对应的 CABLE Input。";
                    case "tip_speaker_capture": return "这里按会议软件里看到的扬声器设备选择，默认选 CABLE Input。程序会自动从对应的 CABLE Output 抓取声音送到 iPhone/iPad。";
                    case "tip_refresh_audio": return "从 Python sounddevice 读取当前 Windows 音频设备；默认名称不匹配时，从列表中手动选择。";
                    case "tip_talk": return "启动后按住时打开虚拟麦克风，松开后立即静音。";
                    case "card_suite": return "整体状态";
                    case "card_camera": return "摄像头";
                    case "card_microphone": return "麦克风";
                    case "card_speaker": return "扬声器";
                    case "meeting_devices": return "腾讯会议中选择：摄像头 = SensorBridge Camera | 麦克风 = Cable Microphone（真实名 CABLE Output）| 扬声器 = Cable Speaker（真实名 CABLE Input）";
                    case "idle_details": return "这两个框按会议软件里看到的设备选：麦克风通常选 CABLE Output，扬声器通常选 CABLE Input。程序会自动换算内部桥接方向。";
                    case "audio_refresh_ok": return "音频设备已刷新。会议麦克风选择显示 Windows 录音设备；会议扬声器选择显示 Windows 播放设备。";
                    case "audio_refresh_failed": return "音频设备列表读取失败。可以先保留默认值，或手动输入设备名。";
                    case "starting_details": return "正在先清理上一轮进程，然后按当前勾选项启动...";
                    case "stopping_details": return "正在停止 SensorBridge 相关进程...";
                    case "tray_open": return "打开窗口";
                    case "tray_start": return "启动全部桥接";
                    case "tray_stop": return "停止并清理";
                    case "tray_check": return "检查设备环境";
                    case "tray_exit": return "退出并清理";
                    case "status_not_started": return "未启动";
                    case "status_enabled": return "已勾选";
                    case "status_disabled": return "未勾选";
                    case "status_starting": return "正在启动...";
                    case "status_start_failed": return "启动失败";
                    case "status_running": return "运行中";
                    case "status_no_process_started": return "未启动进程";
                    case "status_stopping": return "正在停止...";
                    case "status_stopped": return "已停止";
                    case "status_stop_failed": return "停止失败";
                    case "status_checking": return "正在检查...";
                    case "status_check_failed": return "检查失败";
                    case "status_ready_to_configure": return "可配置会议";
                    case "status_not_ready": return "未就绪";
                    case "status_present": return "已找到";
                    case "status_missing": return "缺失";
                    case "status_pid": return "进程";
                    case "ipad_reachable": return "iPhone/iPad 已连接";
                    case "ipad_not_reachable": return "iPhone/iPad 未连接";
                }
            }
            switch (key)
            {
                case "app_title": return "SensorBridge Meeting Suite";
                case "subtitle": return "Use iPhone/iPad as meeting camera, microphone, and speaker";
                case "url_label": return "iPhone/iPad URL";
                case "language_label": return "Language";
                case "microphone_output_label": return "Meeting microphone";
                case "speaker_capture_label": return "Meeting speaker";
                case "camera_check": return "Camera";
                case "microphone_check": return "Microphone";
                case "speaker_check": return "Speaker";
                case "btn_start": return "Start/restart selected";
                case "btn_stop": return "Stop and clean processes";
                case "btn_check": return "Check device readiness";
                case "btn_setup": return "Open Tencent setup guide";
                case "btn_refresh_audio": return "Refresh audio devices";
                case "btn_audio_refreshing": return "Refreshing...";
                case "btn_talk": return "Hold to talk";
                case "btn_talking": return "Talking...";
                case "tip_start": return "Clean the previous bridge run first, then start the currently selected camera, microphone, and speaker.";
                case "tip_stop": return "Stop bridge processes started by this project and clean the virtual camera sender.";
                case "tip_check": return "Check iPhone/iPad reachability and the currently selected Windows virtual camera/audio devices.";
                case "tip_setup": return "Open the Tencent Meeting device selection guide.";
                case "tip_language": return "Switch the display language. Device bridging is unchanged.";
                case "tip_microphone_output": return "Choose the microphone device shown in the meeting app. Usually CABLE Output. The bridge writes iPhone/iPad mic audio into the matching CABLE Input internally.";
                case "tip_speaker_capture": return "Choose the speaker device shown in the meeting app. Usually CABLE Input. The bridge captures the matching CABLE Output internally.";
                case "tip_refresh_audio": return "Reads the current Windows audio devices through Python sounddevice. If the default name is different, choose the matching device manually.";
                case "tip_talk": return "After startup, hold this button to open the virtual microphone. Release it to mute.";
                case "card_suite": return "Suite";
                case "card_camera": return "Camera";
                case "card_microphone": return "Microphone";
                case "card_speaker": return "Speaker";
                case "meeting_devices": return "Tencent Meeting: Camera = SensorBridge Camera | Microphone = Cable Microphone (real name CABLE Output) | Speaker = Cable Speaker (real name CABLE Input)";
                case "idle_details": return "Choose devices as they appear in the meeting app: microphone is usually CABLE Output, speaker is usually CABLE Input. The bridge converts the internal direction automatically.";
                case "audio_refresh_ok": return "Audio devices refreshed. Meeting microphone lists Windows recording devices; meeting speaker lists Windows playback devices.";
                case "audio_refresh_failed": return "Could not read the audio device list. Keep the default values or type a device name manually.";
                case "starting_details": return "Cleaning the previous run first, then starting the selected devices...";
                case "stopping_details": return "Stopping SensorBridge meeting processes...";
                case "tray_open": return "Open";
                case "tray_start": return "Start bridges";
                case "tray_stop": return "Stop and clean";
                case "tray_check": return "Check devices";
                case "tray_exit": return "Exit and clean";
                case "status_not_started": return "not started";
                case "status_enabled": return "enabled";
                case "status_disabled": return "disabled";
                case "status_starting": return "starting...";
                case "status_start_failed": return "start failed";
                case "status_running": return "running";
                case "status_no_process_started": return "no process started";
                case "status_stopping": return "stopping...";
                case "status_stopped": return "stopped";
                case "status_stop_failed": return "stop failed";
                case "status_checking": return "checking...";
                case "status_check_failed": return "check failed";
                case "status_ready_to_configure": return "ready to configure meeting";
                case "status_not_ready": return "not ready";
                case "status_present": return "present";
                case "status_missing": return "missing";
                case "status_pid": return "pid";
                case "ipad_reachable": return "iPhone/iPad reachable";
                case "ipad_not_reachable": return "iPhone/iPad not reachable";
            }
            return key;
        }

        private void SetSuiteState(string key)
        {
            _suiteStateKey = key;
            if (_suiteStatus != null) { _suiteStatus.Text = T("status_" + key); }
            UpdateTalkButtonEnabled();
        }

        private void SetCameraStatus(string key, string value)
        {
            _cameraStatusKey = key;
            _cameraStatusValue = value ?? "";
            if (_cameraStatus != null) { _cameraStatus.Text = FormatComponentStatus(_cameraStatusKey, _cameraStatusValue); }
        }

        private void SetMicrophoneStatus(string key, string value)
        {
            _microphoneStatusKey = key;
            _microphoneStatusValue = value ?? "";
            if (_microphoneStatus != null) { _microphoneStatus.Text = FormatComponentStatus(_microphoneStatusKey, _microphoneStatusValue); }
        }

        private void SetSpeakerStatus(string key, string value)
        {
            _speakerStatusKey = key;
            _speakerStatusValue = value ?? "";
            if (_speakerStatus != null) { _speakerStatus.Text = FormatComponentStatus(_speakerStatusKey, _speakerStatusValue); }
        }

        private void RefreshStatusLabels()
        {
            if (_suiteStatus != null) { _suiteStatus.Text = T("status_" + _suiteStateKey); }
            if (_cameraStatus != null) { _cameraStatus.Text = FormatComponentStatus(_cameraStatusKey, _cameraStatusValue); }
            if (_microphoneStatus != null) { _microphoneStatus.Text = FormatComponentStatus(_microphoneStatusKey, _microphoneStatusValue); }
            if (_speakerStatus != null) { _speakerStatus.Text = FormatComponentStatus(_speakerStatusKey, _speakerStatusValue); }
        }

        private string FormatComponentStatus(string key, string value)
        {
            if (String.IsNullOrEmpty(key)) { return "-"; }
            if (key == "pid_or_not_started")
            {
                return String.IsNullOrEmpty(value) ? T("status_not_started") : T("status_pid") + " " + value;
            }
            return T("status_" + key);
        }

        private void RenderIdle()
        {
            SetPushToTalk(false);
            SetSuiteState("not_started");
            SetCameraStatus(_cameraCheck.Checked ? "enabled" : "disabled", "");
            SetMicrophoneStatus(_microphoneCheck.Checked ? "enabled" : "disabled", "");
            SetSpeakerStatus(_speakerCheck.Checked ? "enabled" : "disabled", "");
            _meetingDevices.Text = T("meeting_devices");
            _details.Text = T("idle_details");
        }

        private void SetPushToTalk(bool talking)
        {
            if (talking && (_talkButton == null || !_talkButton.Enabled || _microphoneCheck == null || !_microphoneCheck.Checked))
            {
                return;
            }
            _talkButtonPressed = talking;
            WritePushToTalkControl(talking);
            UpdateTalkButtonVisual();
        }

        private void WritePushToTalkControl(bool talking)
        {
            string directory = Path.GetDirectoryName(_pushToTalkControlPath);
            if (!String.IsNullOrWhiteSpace(directory)) { Directory.CreateDirectory(directory); }
            string payload = "{\"talking\":" + (talking ? "true" : "false") +
                ",\"updatedAt\":\"" + DateTimeOffset.UtcNow.ToString("o") + "\"}";
            File.WriteAllText(_pushToTalkControlPath, payload, new UTF8Encoding(false));
        }

        private void UpdateTalkButtonVisual()
        {
            if (_talkButton == null) { return; }
            _talkButton.Text = T(_talkButtonPressed ? "btn_talking" : "btn_talk");
            _talkButton.Width = _language == "zh" ? 130 : 135;
            _talkButton.BackColor = _talkButtonPressed ? Color.FromArgb(35, 123, 86) : SystemColors.Control;
            _talkButton.ForeColor = _talkButtonPressed ? Color.White : SystemColors.ControlText;
        }

        private void UpdateTalkButtonEnabled()
        {
            if (_talkButton == null) { return; }
            bool canTalk = _suiteStateKey == "running" && !_stopInProgress && _microphoneCheck != null && _microphoneCheck.Checked;
            _talkButton.Enabled = canTalk;
            if (!canTalk && _talkButtonPressed)
            {
                _talkButtonPressed = false;
                WritePushToTalkControl(false);
            }
            UpdateTalkButtonVisual();
        }

        private void RefreshAudioDevices(bool showStatus)
        {
            if (_refreshAudioButton != null)
            {
                _refreshAudioButton.Enabled = false;
                _refreshAudioButton.Text = T("btn_audio_refreshing");
            }
            if (showStatus) { _details.Text = T("btn_audio_refreshing"); }

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    AudioDeviceLists devices = LoadAudioDevices();
                    Ui(delegate
                    {
                        PopulateDeviceCombo(_microphoneOutputCombo, devices.Inputs, _options.MicrophoneOutputDevice);
                        PopulateDeviceCombo(_speakerCaptureCombo, devices.Outputs, _options.SpeakerCaptureDevice);
                        if (showStatus)
                        {
                            _details.Text = T("audio_refresh_ok") + Environment.NewLine +
                                "Outputs: " + devices.Outputs.Count + Environment.NewLine +
                                "Inputs: " + devices.Inputs.Count;
                        }
                    });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        EnsureDefaultAudioDeviceText();
                        if (showStatus)
                        {
                            _details.Text = T("audio_refresh_failed") + Environment.NewLine + exc.Message;
                        }
                    });
                }
                finally
                {
                    Ui(delegate
                    {
                        if (_refreshAudioButton != null)
                        {
                            _refreshAudioButton.Enabled = true;
                            _refreshAudioButton.Text = T("btn_refresh_audio");
                        }
                    });
                }
            });
        }

        private void EnsureDefaultAudioDeviceText()
        {
            if (_microphoneOutputCombo != null && String.IsNullOrWhiteSpace(_microphoneOutputCombo.Text))
            {
                _microphoneOutputCombo.Text = _options.MicrophoneOutputDevice;
            }
            if (_speakerCaptureCombo != null && String.IsNullOrWhiteSpace(_speakerCaptureCombo.Text))
            {
                _speakerCaptureCombo.Text = _options.SpeakerCaptureDevice;
            }
        }

        private AudioDeviceLists LoadAudioDevices()
        {
            string code = "import json,sounddevice as sd;hs=sd.query_hostapis();print(json.dumps([{'index':i,'name':str(d.get('name','')),'hostapi_name':str(hs[int(d.get('hostapi',-1) or -1)].get('name','')) if 0 <= int(d.get('hostapi',-1) or -1) < len(hs) else '','max_input_channels':int(d.get('max_input_channels',0) or 0),'max_output_channels':int(d.get('max_output_channels',0) or 0),'default_samplerate':float(d.get('default_samplerate',0) or 0)} for i,d in enumerate(sd.query_devices())]))";
            string[] files = new string[] { "py.exe", "python.exe" };
            string[] arguments = new string[] { "-3 -c " + Quote(code), "-c " + Quote(code) };
            Exception lastError = null;
            for (int i = 0; i < files.Length; i++)
            {
                try
                {
                    ProcessCaptureResult result = RunProcessCapture(files[i], arguments[i], _options.ProjectRoot, 15000);
                    if (result.ExitCode == 0 && !String.IsNullOrWhiteSpace(result.Output))
                    {
                        return ParseAudioDevices(result.Output);
                    }
                    lastError = new InvalidOperationException((result.Error + Environment.NewLine + result.Output).Trim());
                }
                catch (Exception exc)
                {
                    lastError = exc;
                }
            }
            throw new InvalidOperationException(lastError == null ? "Python sounddevice did not return audio devices." : lastError.Message);
        }

        private AudioDeviceLists ParseAudioDevices(string json)
        {
            object parsed = _json.DeserializeObject(json.Trim());
            IEnumerable items = parsed as IEnumerable;
            if (items == null) { throw new InvalidOperationException("Audio device list was not a JSON array."); }

            AudioDeviceLists lists = new AudioDeviceLists();
            foreach (object item in items)
            {
                Dictionary<string, object> device = item as Dictionary<string, object>;
                if (device == null) { continue; }
                string name = Value(device, "name").Trim();
                if (String.IsNullOrWhiteSpace(name)) { continue; }
                if (IntValue(device, "max_output_channels") > 0) { lists.Outputs.Add(name); }
                if (IntValue(device, "max_input_channels") > 0) { lists.Inputs.Add(name); }
            }
            List<string> outputs = SortDeviceNames(DeduplicateDeviceNames(lists.Outputs), _options.SpeakerCaptureDevice);
            List<string> inputs = SortDeviceNames(DeduplicateDeviceNames(lists.Inputs), _options.MicrophoneOutputDevice);
            lists.Outputs.Clear();
            lists.Outputs.AddRange(outputs);
            lists.Inputs.Clear();
            lists.Inputs.AddRange(inputs);
            return lists;
        }

        private static List<string> DeduplicateDeviceNames(List<string> names)
        {
            Dictionary<string, string> seen = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string raw in names)
            {
                string name = (raw ?? "").Trim();
                if (name.Length == 0 || seen.ContainsKey(name)) { continue; }
                seen.Add(name, name);
            }
            return new List<string>(seen.Values);
        }

        private static List<string> SortDeviceNames(List<string> names, string preferred)
        {
            names.Sort(delegate(string left, string right)
            {
                int score = DeviceSortScore(left, preferred).CompareTo(DeviceSortScore(right, preferred));
                if (score != 0) { return score; }
                return String.Compare(left, right, StringComparison.CurrentCultureIgnoreCase);
            });
            return names;
        }

        private static int DeviceSortScore(string name, string preferred)
        {
            string text = (name ?? "").ToLowerInvariant();
            string wanted = (preferred ?? "").ToLowerInvariant();
            if (text == wanted) { return 0; }
            if (wanted.Length > 0 && text.IndexOf(wanted, StringComparison.OrdinalIgnoreCase) >= 0) { return 1; }
            if (text.IndexOf("cable", StringComparison.OrdinalIgnoreCase) >= 0 || text.IndexOf("vb-audio", StringComparison.OrdinalIgnoreCase) >= 0) { return 2; }
            return 3;
        }

        private static void PopulateDeviceCombo(ComboBox combo, List<string> devices, string fallback)
        {
            if (combo == null) { return; }
            string current = GetDeviceText(combo, fallback);
            string selected = SelectDeviceText(current, devices, fallback);
            combo.BeginUpdate();
            combo.Items.Clear();
            if (!ContainsIgnoreCase(devices, fallback)) { combo.Items.Add(fallback); }
            foreach (string device in devices) { combo.Items.Add(device); }
            combo.EndUpdate();
            combo.Text = selected;
        }

        private static string SelectDeviceText(string current, List<string> devices, string fallback)
        {
            if (!String.IsNullOrWhiteSpace(current) && !String.Equals(current, fallback, StringComparison.OrdinalIgnoreCase))
            {
                return current;
            }
            foreach (string device in devices)
            {
                if (String.Equals(device, fallback, StringComparison.OrdinalIgnoreCase)) { return device; }
            }
            foreach (string device in devices)
            {
                if (device.IndexOf(fallback, StringComparison.OrdinalIgnoreCase) >= 0) { return device; }
            }
            return String.IsNullOrWhiteSpace(current) ? fallback : current;
        }

        private static bool ContainsIgnoreCase(List<string> values, string value)
        {
            foreach (string item in values)
            {
                if (String.Equals(item, value, StringComparison.OrdinalIgnoreCase)) { return true; }
            }
            return false;
        }

        private static string GetDeviceText(ComboBox combo, string fallback)
        {
            string text = combo == null ? "" : (combo.Text ?? "").Trim();
            return String.IsNullOrWhiteSpace(text) ? fallback : text;
        }

        private static string ResolveMicrophoneBridgePlaybackDevice(string meetingMicrophoneDevice)
        {
            string text = (meetingMicrophoneDevice ?? "").Trim();
            if (text.Length == 0) { return "CABLE Input"; }
            if (text.IndexOf("CABLE Output", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "CABLE Input";
            }
            if (text.StartsWith("Input", StringComparison.OrdinalIgnoreCase))
            {
                return ReplaceFirstIgnoreCase(text, "Input", "Output");
            }
            if (text.IndexOf(" Output", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return ReplaceFirstIgnoreCase(text, "Output", "Input");
            }
            if (text.IndexOf("VB-Audio", StringComparison.OrdinalIgnoreCase) >= 0 ||
                text.IndexOf("CABLE", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "CABLE Input";
            }
            return text;
        }

        private static string ResolveSpeakerBridgeCaptureDevice(string meetingSpeakerDevice)
        {
            string text = (meetingSpeakerDevice ?? "").Trim();
            if (text.Length == 0) { return "CABLE Output"; }
            if (text.IndexOf("CABLE Input", StringComparison.OrdinalIgnoreCase) >= 0 ||
                text.IndexOf("CABLE In", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "CABLE Output";
            }
            if (text.StartsWith("Output", StringComparison.OrdinalIgnoreCase))
            {
                return ReplaceFirstIgnoreCase(text, "Output", "Input");
            }
            if (text.IndexOf(" Input", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return ReplaceFirstIgnoreCase(text, "Input", "Output");
            }
            if (text.IndexOf("VB-Audio", StringComparison.OrdinalIgnoreCase) >= 0 ||
                text.IndexOf("CABLE", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "CABLE Output";
            }
            return text;
        }

        private static string ReplaceFirstIgnoreCase(string text, string oldValue, string newValue)
        {
            int index = text.IndexOf(oldValue, StringComparison.OrdinalIgnoreCase);
            if (index < 0) { return text; }
            return text.Substring(0, index) + newValue + text.Substring(index + oldValue.Length);
        }

        private string ValidateStartSelection()
        {
            if (!_microphoneCheck.Checked || !_speakerCheck.Checked) { return ""; }
            string meetingMicrophone = GetDeviceText(_microphoneOutputCombo, _options.MicrophoneOutputDevice);
            string meetingSpeaker = GetDeviceText(_speakerCaptureCombo, _options.SpeakerCaptureDevice);
            string microphoneCable = VirtualCableFamilyKey(meetingMicrophone);
            string speakerCable = VirtualCableFamilyKey(meetingSpeaker);
            if (microphoneCable.Length > 0 &&
                String.Equals(microphoneCable, speakerCable, StringComparison.OrdinalIgnoreCase))
            {
                if (_language == "zh")
                {
                    return "检测到麦克风和扬声器选的是同一条虚拟音频线：" + Environment.NewLine +
                        "麦克风 = " + meetingMicrophone + Environment.NewLine +
                        "扬声器 = " + meetingSpeaker + Environment.NewLine + Environment.NewLine +
                        "这会把 iPhone/iPad 麦克风声音和会议扬声器声音混在同一条 CABLE 里，容易在 iPad 上产生噪声、回声或断续播放。" + Environment.NewLine +
                        "请先只勾选麦克风或只勾选扬声器测试。要同时使用麦克风和扬声器，需要两条独立虚拟音频线，例如一条给麦克风，另一条给扬声器。";
                }
                return "The selected microphone and speaker use the same virtual audio cable:" + Environment.NewLine +
                    "Microphone = " + meetingMicrophone + Environment.NewLine +
                    "Speaker = " + meetingSpeaker + Environment.NewLine + Environment.NewLine +
                    "That mixes the iPhone/iPad microphone and meeting speaker audio into one CABLE route, which can create noise, echo, or choppy playback on the iPhone/iPad." + Environment.NewLine +
                    "Start only Microphone or only Speaker for testing. Full microphone plus speaker mode needs two separate virtual audio cables.";
            }
            return "";
        }

        private static string VirtualCableFamilyKey(string deviceName)
        {
            string text = (deviceName ?? "").ToLowerInvariant();
            if (text.IndexOf("cable", StringComparison.OrdinalIgnoreCase) < 0 &&
                text.IndexOf("vb-audio", StringComparison.OrdinalIgnoreCase) < 0)
            {
                return "";
            }
            string normalized = text.Replace("_", " ").Replace("-", " ");
            if (normalized.IndexOf("hi fi", StringComparison.OrdinalIgnoreCase) >= 0 ||
                normalized.IndexOf("hifi", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "vb-hifi-cable";
            }
            if (normalized.IndexOf("cable a", StringComparison.OrdinalIgnoreCase) >= 0) { return "vb-cable-a"; }
            if (normalized.IndexOf("cable b", StringComparison.OrdinalIgnoreCase) >= 0) { return "vb-cable-b"; }
            if (normalized.IndexOf("cable c", StringComparison.OrdinalIgnoreCase) >= 0) { return "vb-cable-c"; }
            if (normalized.IndexOf("cable d", StringComparison.OrdinalIgnoreCase) >= 0) { return "vb-cable-d"; }
            return "vb-cable";
        }

        private void StartSuite()
        {
            string validationError = ValidateStartSelection();
            string startArguments = BuildStartArguments();
            SetPushToTalk(false);
            SetButtons(false);
            SetSuiteState("starting");
            _details.Text = String.IsNullOrWhiteSpace(validationError)
                ? T("starting_details")
                : validationError + Environment.NewLine + Environment.NewLine + T("starting_details");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    StopSuiteNow();
                    string output = RunPowerShellScript("Start-SensorBridgeMeeting.ps1", startArguments);
                    List<Dictionary<string, object>> processes = ParseProcessList(output);
                    lock (_childProcessIds)
                    {
                        _childProcessIds.Clear();
                        foreach (Dictionary<string, object> process in processes)
                        {
                            int pid = IntValue(process, "pid");
                            if (pid > 0) { _childProcessIds.Add(pid); }
                        }
                    }
                    Ui(delegate { RenderStarted(processes, output); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        SetSuiteState("start_failed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate { SetButtons(true); });
                }
            });
        }

        private string BuildStartArguments()
        {
            StringBuilder args = new StringBuilder();
            string meetingMicrophone = GetDeviceText(_microphoneOutputCombo, _options.MicrophoneOutputDevice);
            string meetingSpeaker = GetDeviceText(_speakerCaptureCombo, _options.SpeakerCaptureDevice);
            args.Append(" -IpadBaseUrl ").Append(Quote(_baseUrlText.Text));
            args.Append(" -CameraPort ").Append(_options.CameraPort);
            args.Append(" -CableInputDevice ").Append(Quote(ResolveMicrophoneBridgePlaybackDevice(meetingMicrophone)));
            args.Append(" -SpeakerCaptureDevice ").Append(Quote(ResolveSpeakerBridgeCaptureDevice(meetingSpeaker)));
            args.Append(" -MicrophoneMode webrtc");
            args.Append(" -SpeakerMode webrtc");
            if (!_cameraCheck.Checked) { args.Append(" -NoCamera"); }
            if (!_microphoneCheck.Checked) { args.Append(" -NoMicrophone"); }
            if (!_speakerCheck.Checked) { args.Append(" -NoSpeaker"); }
            if (_microphoneCheck.Checked)
            {
                args.Append(" -PushToTalk");
                args.Append(" -PushToTalkControlPath ").Append(Quote(_pushToTalkControlPath));
            }
            return args.ToString();
        }

        private string BuildReadinessArguments()
        {
            StringBuilder args = new StringBuilder();
            string meetingMicrophone = GetDeviceText(_microphoneOutputCombo, _options.MicrophoneOutputDevice);
            string meetingSpeaker = GetDeviceText(_speakerCaptureCombo, _options.SpeakerCaptureDevice);
            args.Append(" -IpadBaseUrl ").Append(Quote(_baseUrlText.Text));
            args.Append(" -CableInputDevice ").Append(Quote(ResolveMicrophoneBridgePlaybackDevice(meetingMicrophone)));
            args.Append(" -SpeakerCaptureDevice ").Append(Quote(ResolveSpeakerBridgeCaptureDevice(meetingSpeaker)));
            return args.ToString();
        }

        private void RenderStarted(List<Dictionary<string, object>> processes, string output)
        {
            SetSuiteState(processes.Count > 0 ? "running" : "no_process_started");
            SetCameraStatus(_cameraCheck.Checked ? "pid_or_not_started" : "disabled", _cameraCheck.Checked ? ComponentProcessId(processes, "camera") : "");
            SetMicrophoneStatus(_microphoneCheck.Checked ? "pid_or_not_started" : "disabled", _microphoneCheck.Checked ? ComponentProcessId(processes, "microphone") : "");
            SetSpeakerStatus(_speakerCheck.Checked ? "pid_or_not_started" : "disabled", _speakerCheck.Checked ? ComponentProcessId(processes, "speaker") : "");
            _details.Text = output.Trim();
        }

        private static string ComponentProcessId(List<Dictionary<string, object>> processes, string name)
        {
            foreach (Dictionary<string, object> process in processes)
            {
                if (String.Equals(Value(process, "name"), name, StringComparison.OrdinalIgnoreCase))
                {
                    return Value(process, "pid");
                }
            }
            return "";
        }

        private void StopSuite()
        {
            if (_stopInProgress) { return; }
            _stopInProgress = true;
            SetPushToTalk(false);
            SetButtons(false);
            SetSuiteState("stopping");
            _details.Text = T("stopping_details");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    string output = StopSuiteNow();
                    Ui(delegate
                    {
                        RenderIdle();
                        SetSuiteState("stopped");
                        if (!String.IsNullOrWhiteSpace(output)) { _details.Text = output.Trim(); }
                    });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        SetSuiteState("stop_failed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate
                    {
                        _stopInProgress = false;
                        SetButtons(true);
                    });
                }
            });
        }

        private string StopSuiteNow()
        {
            List<int> pids;
            lock (_childProcessIds)
            {
                pids = new List<int>(_childProcessIds);
                _childProcessIds.Clear();
            }

            List<string> errors = new List<string>();
            foreach (int pid in pids)
            {
                try
                {
                    KillProcessTree(pid);
                }
                catch (Exception exc)
                {
                    errors.Add("taskkill " + pid + ": " + exc.Message);
                }
            }

            string output = "";
            try
            {
                output = RunPowerShellScript("Stop-SensorBridgeMeeting.ps1", BuildStopArguments(pids), 30000);
            }
            catch (Exception exc)
            {
                errors.Add(exc.ToString());
            }
            if (errors.Count > 0)
            {
                output += Environment.NewLine + String.Join(Environment.NewLine, errors.ToArray());
            }
            return output;
        }

        private static void KillProcessTree(int pid)
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "taskkill.exe";
            info.Arguments = "/PID " + pid + " /T /F";
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            using (Process process = Process.Start(info))
            {
                process.WaitForExit(5000);
            }
        }

        private static string BuildStopArguments(List<int> pids)
        {
            if (pids == null || pids.Count == 0) { return ""; }
            StringBuilder args = new StringBuilder();
            args.Append(" -Pids ");
            for (int i = 0; i < pids.Count; i++)
            {
                if (i > 0) { args.Append(" "); }
                args.Append(pids[i]);
            }
            return args.ToString();
        }

        private void RunReadinessCheck()
        {
            string readinessArguments = BuildReadinessArguments();
            SetButtons(false);
            SetSuiteState("checking");
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    string output = RunPowerShellScript("Test-SensorBridgeMeeting.ps1", readinessArguments);
                    Dictionary<string, object> payload = _json.Deserialize<Dictionary<string, object>>(ExtractJson(output));
                    Ui(delegate { RenderReadiness(payload, output); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        SetSuiteState("check_failed");
                        _details.Text = exc.ToString();
                    });
                }
                finally
                {
                    Ui(delegate { SetButtons(true); });
                }
            });
        }

        private void RenderReadiness(Dictionary<string, object> payload, string output)
        {
            SetSuiteState(Bool(payload, "ok") ? "ready_to_configure" : "not_ready");
            Dictionary<string, object> components = Dict(payload, "components");
            SetCameraStatus(Bool(components, "camera") ? "present" : "missing", "");
            SetMicrophoneStatus(Bool(components, "microphone") ? "present" : "missing", "");
            SetSpeakerStatus(Bool(components, "speaker") ? "present" : "missing", "");
            Dictionary<string, object> ipad = Dict(payload, "ipad");
            string ipadLine = Bool(ipad, "healthReachable") ? T("ipad_reachable") : T("ipad_not_reachable");
            _details.Text = ipadLine + Environment.NewLine + output.Trim();
        }

        private string RunPowerShellScript(string scriptName, string arguments)
        {
            return RunPowerShellScript(scriptName, arguments, 0);
        }

        private string RunPowerShellScript(string scriptName, string arguments, int timeoutMilliseconds)
        {
            string scriptPath = Path.Combine(_options.ProjectRoot, "meeting-suite", scriptName);
            if (!File.Exists(scriptPath)) { throw new FileNotFoundException(scriptName + " was not found.", scriptPath); }

            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "powershell.exe";
            info.Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(scriptPath) + arguments;
            info.WorkingDirectory = _options.ProjectRoot;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;

            using (Process process = Process.Start(info))
            {
                if (timeoutMilliseconds > 0 && !process.WaitForExit(timeoutMilliseconds))
                {
                    try { process.Kill(); }
                    catch { }
                    throw new TimeoutException(scriptName + " did not finish within " + timeoutMilliseconds + " ms.");
                }
                string output = process.StandardOutput.ReadToEnd();
                string error = process.StandardError.ReadToEnd();
                if (timeoutMilliseconds <= 0) { process.WaitForExit(); }
                if (process.ExitCode != 0)
                {
                    throw new InvalidOperationException(String.IsNullOrWhiteSpace(error) ? output : error);
                }
                return output;
            }
        }

        private static ProcessCaptureResult RunProcessCapture(string fileName, string arguments, string workingDirectory, int timeoutMilliseconds)
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = fileName;
            info.Arguments = arguments;
            info.WorkingDirectory = workingDirectory;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;

            using (Process process = Process.Start(info))
            {
                if (!process.WaitForExit(timeoutMilliseconds))
                {
                    try { process.Kill(); }
                    catch { }
                    throw new TimeoutException(fileName + " did not finish within " + timeoutMilliseconds + " ms.");
                }
                ProcessCaptureResult result = new ProcessCaptureResult();
                result.ExitCode = process.ExitCode;
                result.Output = process.StandardOutput.ReadToEnd();
                result.Error = process.StandardError.ReadToEnd();
                return result;
            }
        }

        private List<Dictionary<string, object>> ParseProcessList(string output)
        {
            string json = output.Trim();
            object parsed = _json.DeserializeObject(json);
            List<Dictionary<string, object>> items = new List<Dictionary<string, object>>();
            Dictionary<string, object> single = parsed as Dictionary<string, object>;
            if (single != null)
            {
                items.Add(single);
                return items;
            }
            IEnumerable array = parsed as IEnumerable;
            if (array == null || parsed is string)
            {
                return items;
            }
            foreach (object item in array)
            {
                Dictionary<string, object> dictionary = item as Dictionary<string, object>;
                if (dictionary != null) { items.Add(dictionary); }
            }
            return items;
        }

        private void OpenSetupDoc()
        {
            string doc = Path.Combine(_options.ProjectRoot, "docs", "TENCENT_MEETING_SETUP.md");
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = File.Exists(doc) ? doc : _options.ProjectRoot;
            info.UseShellExecute = true;
            Process.Start(info);
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (WindowState == FormWindowState.Minimized) { HideToTray(); }
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
                try { SetPushToTalk(false); }
                catch { }
                try { StopSuiteNow(); }
                catch { }
                if (_toolTip != null) { _toolTip.Dispose(); _toolTip = null; }
                if (_trayIcon != null) { _trayIcon.Visible = false; _trayIcon.Dispose(); _trayIcon = null; }
                if (_trayMenu != null) { _trayMenu.Dispose(); _trayMenu = null; }
            }
            base.Dispose(disposing);
        }

        private void HideToTray()
        {
            Hide();
            ShowInTaskbar = false;
            if (_trayIcon != null) { _trayIcon.Visible = true; }
        }

        private void RestoreFromTray()
        {
            ShowInTaskbar = true;
            Show();
            WindowState = FormWindowState.Normal;
            Activate();
        }

        private void SetButtons(bool enabled)
        {
            _startButton.Enabled = enabled;
            _checkButton.Enabled = enabled;
            _docsButton.Enabled = enabled;
            if (_refreshAudioButton != null) { _refreshAudioButton.Enabled = enabled; }
            _stopButton.Enabled = !_stopInProgress;
            UpdateTalkButtonEnabled();
        }

        private void Ui(MethodInvoker action)
        {
            if (IsDisposed) { return; }
            if (InvokeRequired) { BeginInvoke(action); }
            else { action(); }
        }

        private static Dictionary<string, object> Dict(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value)) { return new Dictionary<string, object>(); }
            Dictionary<string, object> dict = value as Dictionary<string, object>;
            return dict ?? new Dictionary<string, object>();
        }

        private static string Value(Dictionary<string, object> root, string key)
        {
            object value;
            return root != null && root.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : "";
        }

        private static bool Bool(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value) || value == null) { return false; }
            if (value is bool) { return (bool)value; }
            bool parsed;
            return Boolean.TryParse(Convert.ToString(value), out parsed) && parsed;
        }

        private static int IntValue(Dictionary<string, object> root, string key)
        {
            object value;
            if (root == null || !root.TryGetValue(key, out value) || value == null) { return -1; }
            try { return Convert.ToInt32(value); }
            catch { return -1; }
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? "").Replace("\"", "\\\"") + "\"";
        }

        private static string ExtractJson(string output)
        {
            int start = output.IndexOf('{');
            int end = output.LastIndexOf('}');
            if (start < 0 || end <= start) { throw new InvalidOperationException("No JSON object found in script output."); }
            return output.Substring(start, end - start + 1);
        }
    }
}
