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

        public static AppOptions Parse(string[] args)
        {
            AppOptions options = new AppOptions();
            for (int i = 0; i < args.Length; i++)
            {
                string value = i + 1 < args.Length ? args[i + 1] : "";
                if (args[i] == "--project-root" && value.Length > 0) { options.ProjectRoot = Path.GetFullPath(value); i++; }
                else if (args[i] == "--ipad-base-url" && value.Length > 0) { options.IpadBaseUrl = value; i++; }
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
        private TextBox _baseUrlText;
        private CheckBox _cameraCheck;
        private CheckBox _microphoneCheck;
        private CheckBox _speakerCheck;
        private Button _startButton;
        private Button _stopButton;
        private Button _checkButton;
        private Button _docsButton;
        private Label _suiteStatus;
        private Label _cameraStatus;
        private Label _microphoneStatus;
        private Label _speakerStatus;
        private Label _meetingDevices;
        private TextBox _details;
        private NotifyIcon _trayIcon;
        private ContextMenuStrip _trayMenu;
        private bool _allowExit;

        public MainForm(AppOptions options)
        {
            _options = options;
            _json.MaxJsonLength = Int32.MaxValue;
            Text = "SensorBridge Meeting Suite";
            MinimumSize = new Size(900, 560);
            Size = new Size(980, 640);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(245, 247, 250);
            Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            BuildLayout();
            BuildTrayIcon();
            RenderIdle();
        }

        private void BuildLayout()
        {
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.RowCount = 5;
            root.ColumnCount = 1;
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 72));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 68));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 126));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 54));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Controls.Add(root);

            Panel header = new Panel();
            header.Dock = DockStyle.Fill;
            header.BackColor = Color.FromArgb(27, 92, 108);
            header.Padding = new Padding(22, 12, 22, 8);
            root.Controls.Add(header, 0, 0);

            Label title = new Label();
            title.Text = "SensorBridge Meeting Suite";
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 19F, FontStyle.Bold, GraphicsUnit.Point);
            title.AutoSize = true;
            title.Location = new Point(0, 4);
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "Camera, microphone, and speaker bridge for Tencent Meeting";
            subtitle.ForeColor = Color.FromArgb(220, 243, 240);
            subtitle.AutoSize = true;
            subtitle.Location = new Point(2, 43);
            header.Controls.Add(subtitle);

            Panel toolbar = new Panel();
            toolbar.Dock = DockStyle.Fill;
            toolbar.BackColor = Color.White;
            toolbar.Padding = new Padding(20, 14, 20, 10);
            root.Controls.Add(toolbar, 0, 1);

            Label urlLabel = new Label();
            urlLabel.Text = "iPhone/iPad URL";
            urlLabel.AutoSize = true;
            urlLabel.Location = new Point(0, 15);
            toolbar.Controls.Add(urlLabel);

            _baseUrlText = new TextBox();
            _baseUrlText.Text = _options.IpadBaseUrl;
            _baseUrlText.Width = 245;
            _baseUrlText.Location = new Point(104, 12);
            toolbar.Controls.Add(_baseUrlText);

            _cameraCheck = AddCheck(toolbar, "Camera", 365, _options.StartCamera);
            _microphoneCheck = AddCheck(toolbar, "Microphone", 445, _options.StartMicrophone);
            _speakerCheck = AddCheck(toolbar, "Speaker", 558, _options.StartSpeaker);

            _startButton = AddButton(toolbar, "Start all", 650, delegate { StartSuite(); });
            _stopButton = AddButton(toolbar, "Stop", 742, delegate { StopSuite(); });
            _checkButton = AddButton(toolbar, "Check", 812, delegate { RunReadinessCheck(); });
            _docsButton = AddButton(toolbar, "Setup", 882, delegate { OpenSetupDoc(); });

            TableLayoutPanel cards = new TableLayoutPanel();
            cards.Dock = DockStyle.Fill;
            cards.Padding = new Padding(18, 12, 18, 10);
            cards.ColumnCount = 4;
            cards.RowCount = 1;
            for (int i = 0; i < 4; i++) { cards.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25)); }
            root.Controls.Add(cards, 0, 2);

            _suiteStatus = AddCard(cards, 0, "Suite");
            _cameraStatus = AddCard(cards, 1, "Camera");
            _microphoneStatus = AddCard(cards, 2, "Microphone");
            _speakerStatus = AddCard(cards, 3, "Speaker");

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
        }

        private static CheckBox AddCheck(Control parent, string text, int x, bool isChecked)
        {
            CheckBox check = new CheckBox();
            check.Text = text;
            check.Checked = isChecked;
            check.AutoSize = true;
            check.Location = new Point(x, 15);
            parent.Controls.Add(check);
            return check;
        }

        private static Button AddButton(Control parent, string text, int x, EventHandler click)
        {
            Button button = new Button();
            button.Text = text;
            button.Width = text.Length > 5 ? 84 : 62;
            button.Height = 30;
            button.Location = new Point(x, 10);
            button.Click += click;
            parent.Controls.Add(button);
            return button;
        }

        private static Label AddCard(TableLayoutPanel grid, int column, string title)
        {
            Panel card = new Panel();
            card.Dock = DockStyle.Fill;
            card.Margin = new Padding(6);
            card.BackColor = Color.White;
            grid.Controls.Add(card, column, 0);

            Label titleLabel = new Label();
            titleLabel.Text = title;
            titleLabel.Location = new Point(14, 12);
            titleLabel.Size = new Size(190, 18);
            titleLabel.ForeColor = Color.FromArgb(86, 99, 112);
            titleLabel.Font = new Font("Segoe UI Semibold", 8.5F, FontStyle.Bold, GraphicsUnit.Point);
            card.Controls.Add(titleLabel);

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
                titleLabel.Width = width;
                value.Width = width;
            };
            return value;
        }

        private void BuildTrayIcon()
        {
            _trayMenu = new ContextMenuStrip();
            _trayMenu.Items.Add("Open", null, delegate { RestoreFromTray(); });
            _trayMenu.Items.Add("Start", null, delegate { RestoreFromTray(); StartSuite(); });
            _trayMenu.Items.Add("Stop", null, delegate { StopSuite(); });
            _trayMenu.Items.Add("Check", null, delegate { RestoreFromTray(); RunReadinessCheck(); });
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add("Exit", null, delegate { _allowExit = true; Close(); });

            _trayIcon = new NotifyIcon();
            _trayIcon.Text = "SensorBridge Meeting Suite";
            _trayIcon.Icon = Icon == null ? SystemIcons.Application : Icon;
            _trayIcon.ContextMenuStrip = _trayMenu;
            _trayIcon.Visible = true;
            _trayIcon.DoubleClick += delegate { RestoreFromTray(); };
        }

        private void RenderIdle()
        {
            _suiteStatus.Text = "not started";
            _cameraStatus.Text = _cameraCheck.Checked ? "enabled" : "disabled";
            _microphoneStatus.Text = _microphoneCheck.Checked ? "enabled" : "disabled";
            _speakerStatus.Text = _speakerCheck.Checked ? "enabled" : "disabled";
            _meetingDevices.Text = "Tencent Meeting: Camera = SensorBridge Camera | Microphone = CABLE Output | Speaker = CABLE Input";
            _details.Text = "Press Start all to launch the selected bridges. Use Check before joining a Tencent Meeting.";
        }

        private void StartSuite()
        {
            SetButtons(false);
            _suiteStatus.Text = "starting...";
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    string output = RunPowerShellScript("Start-SensorBridgeMeeting.ps1", BuildStartArguments());
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
                        _suiteStatus.Text = "start failed";
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
            args.Append(" -IpadBaseUrl ").Append(Quote(_baseUrlText.Text));
            args.Append(" -CameraPort ").Append(_options.CameraPort);
            if (!_cameraCheck.Checked) { args.Append(" -NoCamera"); }
            if (!_microphoneCheck.Checked) { args.Append(" -NoMicrophone"); }
            if (!_speakerCheck.Checked) { args.Append(" -NoSpeaker"); }
            return args.ToString();
        }

        private void RenderStarted(List<Dictionary<string, object>> processes, string output)
        {
            _suiteStatus.Text = processes.Count > 0 ? "running" : "no process started";
            _cameraStatus.Text = ComponentState(processes, "camera");
            _microphoneStatus.Text = ComponentState(processes, "microphone");
            _speakerStatus.Text = ComponentState(processes, "speaker");
            _details.Text = output.Trim();
        }

        private static string ComponentState(List<Dictionary<string, object>> processes, string name)
        {
            foreach (Dictionary<string, object> process in processes)
            {
                if (String.Equals(Value(process, "name"), name, StringComparison.OrdinalIgnoreCase))
                {
                    return "pid " + Value(process, "pid");
                }
            }
            return "not started";
        }

        private void StopSuite()
        {
            List<int> pids;
            lock (_childProcessIds)
            {
                pids = new List<int>(_childProcessIds);
                _childProcessIds.Clear();
            }

            foreach (int pid in pids)
            {
                try
                {
                    Process process = Process.GetProcessById(pid);
                    if (!process.HasExited)
                    {
                        process.Kill();
                        process.WaitForExit(3000);
                    }
                }
                catch
                {
                    // Process already exited or is inaccessible.
                }
            }
            RenderIdle();
            _suiteStatus.Text = "stopped";
        }

        private void RunReadinessCheck()
        {
            SetButtons(false);
            _suiteStatus.Text = "checking...";
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    string output = RunPowerShellScript("Test-SensorBridgeMeeting.ps1", " -IpadBaseUrl " + Quote(_baseUrlText.Text));
                    Dictionary<string, object> payload = _json.Deserialize<Dictionary<string, object>>(ExtractJson(output));
                    Ui(delegate { RenderReadiness(payload, output); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _suiteStatus.Text = "check failed";
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
            _suiteStatus.Text = Bool(payload, "ok") ? "ready to configure meeting" : "not ready";
            Dictionary<string, object> components = Dict(payload, "components");
            _cameraStatus.Text = Bool(components, "camera") ? "present" : "missing";
            _microphoneStatus.Text = Bool(components, "microphone") ? "present" : "missing";
            _speakerStatus.Text = Bool(components, "speaker") ? "present" : "missing";
            Dictionary<string, object> ipad = Dict(payload, "ipad");
            string ipadLine = Bool(ipad, "healthReachable") ? "iPhone/iPad reachable" : "iPhone/iPad not reachable";
            _details.Text = ipadLine + Environment.NewLine + output.Trim();
        }

        private string RunPowerShellScript(string scriptName, string arguments)
        {
            string scriptPath = Path.Combine(_options.ProjectRoot, "meeting-suite", scriptName);
            if (!File.Exists(scriptPath)) { throw new FileNotFoundException(scriptName + " was not found.", scriptPath); }

            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "powershell.exe";
            info.Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(scriptPath) + arguments;
            info.WorkingDirectory = _options.ProjectRoot;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;

            using (Process process = Process.Start(info))
            {
                string output = process.StandardOutput.ReadToEnd();
                string error = process.StandardError.ReadToEnd();
                process.WaitForExit();
                if (process.ExitCode != 0)
                {
                    throw new InvalidOperationException(String.IsNullOrWhiteSpace(error) ? output : error);
                }
                return output;
            }
        }

        private List<Dictionary<string, object>> ParseProcessList(string output)
        {
            string json = output.Trim();
            object parsed = _json.DeserializeObject(json);
            ArrayList array = parsed as ArrayList;
            if (array == null)
            {
                Dictionary<string, object> single = parsed as Dictionary<string, object>;
                List<Dictionary<string, object>> singleton = new List<Dictionary<string, object>>();
                if (single != null) { singleton.Add(single); }
                return singleton;
            }
            List<Dictionary<string, object>> items = new List<Dictionary<string, object>>();
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
                StopSuite();
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
            _stopButton.Enabled = true;
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
