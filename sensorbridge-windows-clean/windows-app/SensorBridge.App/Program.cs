using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using System.Web.Script.Serialization;

namespace SensorBridge.App
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            AppOptions options = AppOptions.Parse(args);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm(options));
        }
    }

    internal sealed class CropPictureBox : PictureBox
    {
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(BackColor);
            if (Image == null || ClientSize.Width <= 0 || ClientSize.Height <= 0)
            {
                return;
            }

            Rectangle dest = ClientRectangle;
            double sourceAspect = (double)Image.Width / Image.Height;
            double destAspect = (double)dest.Width / dest.Height;
            RectangleF source;
            if (sourceAspect > destAspect)
            {
                float width = (float)(Image.Height * destAspect);
                float left = (Image.Width - width) / 2F;
                source = new RectangleF(left, 0, width, Image.Height);
            }
            else
            {
                float height = (float)(Image.Width / destAspect);
                float top = (Image.Height - height) / 2F;
                source = new RectangleF(0, top, Image.Width, height);
            }

            e.Graphics.InterpolationMode = InterpolationMode.HighQualityBilinear;
            e.Graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            e.Graphics.DrawImage(Image, dest, source, GraphicsUnit.Pixel);
        }
    }

    internal sealed class AspectRatioPanel : Panel
    {
        public int AspectWidth { get; set; }
        public int AspectHeight { get; set; }

        public AspectRatioPanel()
        {
            AspectWidth = 16;
            AspectHeight = 9;
        }

        protected override void OnLayout(LayoutEventArgs levent)
        {
            base.OnLayout(levent);
            if (Controls.Count == 0 || AspectWidth <= 0 || AspectHeight <= 0)
            {
                return;
            }

            Control child = Controls[0];
            Rectangle area = ClientRectangle;
            double target = (double)AspectWidth / AspectHeight;
            int width = area.Width;
            int height = (int)Math.Round(width / target);
            if (height > area.Height)
            {
                height = area.Height;
                width = (int)Math.Round(height * target);
            }

            int left = area.Left + (area.Width - width) / 2;
            int top = area.Top + (area.Height - height) / 2;
            child.Bounds = new Rectangle(left, top, Math.Max(1, width), Math.Max(1, height));
        }
    }

    internal sealed class AviRecorder : IDisposable
    {
        private readonly List<IndexEntry> _index = new List<IndexEntry>();
        private BinaryWriter _writer;
        private long _riffSizePos;
        private long _hdrlListSizePos;
        private long _strlListSizePos;
        private long _moviListSizePos;
        private long _moviDataStart;
        private long _totalFramesPos;
        private long _streamLengthPos;
        private int _width;
        private int _height;
        private int _fps;
        private int _stride;
        private int _imageSize;
        private bool _closed;

        public int FrameCount { get; private set; }
        public string Path { get; private set; }

        public void Begin(string path, int width, int height, int fps)
        {
            Path = path;
            _width = width;
            _height = height;
            _fps = fps;
            _stride = ((_width * 3 + 3) / 4) * 4;
            _imageSize = _stride * _height;
            _writer = new BinaryWriter(File.Create(path));

            WriteFourCc("RIFF");
            _riffSizePos = _writer.BaseStream.Position;
            _writer.Write(0);
            WriteFourCc("AVI ");

            WriteFourCc("LIST");
            _hdrlListSizePos = _writer.BaseStream.Position;
            _writer.Write(0);
            WriteFourCc("hdrl");

            WriteFourCc("avih");
            _writer.Write(56);
            _writer.Write(1000000 / _fps);
            _writer.Write(_imageSize * _fps);
            _writer.Write(0);
            _writer.Write(0x10);
            _totalFramesPos = _writer.BaseStream.Position;
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(1);
            _writer.Write(_imageSize);
            _writer.Write(_width);
            _writer.Write(_height);
            for (int i = 0; i < 4; i++)
            {
                _writer.Write(0);
            }

            WriteFourCc("LIST");
            _strlListSizePos = _writer.BaseStream.Position;
            _writer.Write(0);
            WriteFourCc("strl");

            WriteFourCc("strh");
            _writer.Write(56);
            WriteFourCc("vids");
            WriteFourCc("DIB ");
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(1);
            _writer.Write(_fps);
            _writer.Write(0);
            _streamLengthPos = _writer.BaseStream.Position;
            _writer.Write(0);
            _writer.Write(_imageSize);
            _writer.Write(-1);
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(_width);
            _writer.Write(_height);

            WriteFourCc("strf");
            _writer.Write(40);
            _writer.Write(40);
            _writer.Write(_width);
            _writer.Write(_height);
            _writer.Write((short)1);
            _writer.Write((short)24);
            _writer.Write(0);
            _writer.Write(_imageSize);
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(0);
            _writer.Write(0);

            PatchSize(_strlListSizePos);
            PatchSize(_hdrlListSizePos);

            WriteFourCc("LIST");
            _moviListSizePos = _writer.BaseStream.Position;
            _writer.Write(0);
            WriteFourCc("movi");
            _moviDataStart = _writer.BaseStream.Position;
        }

        public void AddFrame(Image frame)
        {
            if (_writer == null || _closed)
            {
                return;
            }

            long chunkStart = _writer.BaseStream.Position;
            WriteFourCc("00db");
            _writer.Write(_imageSize);
            WriteFrameBytes(frame);
            if ((_imageSize & 1) == 1)
            {
                _writer.Write((byte)0);
            }
            _index.Add(new IndexEntry { Offset = (int)(chunkStart - _moviDataStart), Size = _imageSize });
            FrameCount++;
        }

        public void Dispose()
        {
            End();
        }

        public void End()
        {
            if (_writer == null || _closed)
            {
                return;
            }
            _closed = true;

            PatchSize(_moviListSizePos);
            WriteFourCc("idx1");
            _writer.Write(_index.Count * 16);
            foreach (IndexEntry entry in _index)
            {
                WriteFourCc("00db");
                _writer.Write(0x10);
                _writer.Write(entry.Offset);
                _writer.Write(entry.Size);
            }

            long end = _writer.BaseStream.Position;
            _writer.BaseStream.Position = _totalFramesPos;
            _writer.Write(FrameCount);
            _writer.BaseStream.Position = _streamLengthPos;
            _writer.Write(FrameCount);
            _writer.BaseStream.Position = _riffSizePos;
            _writer.Write((int)(end - 8));
            _writer.BaseStream.Position = end;
            _writer.Dispose();
        }

        private void WriteFrameBytes(Image frame)
        {
            using (Bitmap scaled = new Bitmap(_width, _height, PixelFormat.Format24bppRgb))
            {
                using (Graphics graphics = Graphics.FromImage(scaled))
                {
                    graphics.InterpolationMode = InterpolationMode.HighQualityBilinear;
                    graphics.DrawImage(frame, new Rectangle(0, 0, _width, _height));
                }

                BitmapData data = scaled.LockBits(new Rectangle(0, 0, _width, _height), ImageLockMode.ReadOnly, PixelFormat.Format24bppRgb);
                try
                {
                    byte[] row = new byte[Math.Abs(data.Stride)];
                    byte[] padding = new byte[_stride - (_width * 3)];
                    for (int y = _height - 1; y >= 0; y--)
                    {
                        IntPtr ptr = IntPtr.Add(data.Scan0, y * data.Stride);
                        Marshal.Copy(ptr, row, 0, row.Length);
                        _writer.Write(row, 0, _width * 3);
                        if (padding.Length > 0)
                        {
                            _writer.Write(padding);
                        }
                    }
                }
                finally
                {
                    scaled.UnlockBits(data);
                }
            }
        }

        private void PatchSize(long sizePosition)
        {
            long current = _writer.BaseStream.Position;
            _writer.BaseStream.Position = sizePosition;
            _writer.Write((int)(current - sizePosition - 4));
            _writer.BaseStream.Position = current;
        }

        private void WriteFourCc(string value)
        {
            _writer.Write(Encoding.ASCII.GetBytes(value));
        }

        private struct IndexEntry
        {
            public int Offset;
            public int Size;
        }
    }

    internal sealed class AppOptions
    {
        public string ProjectRoot = ResolveDefaultProjectRoot();
        public int Port = 8765;
        public string HostName = "127.0.0.1";
        public string UpstreamUrl = "http://192.168.0.24:27180";

        private static string ResolveDefaultProjectRoot()
        {
            string current = AppDomain.CurrentDomain.BaseDirectory;
            string manifestRoot = ResolveManifestProjectRoot(current);
            if (!String.IsNullOrEmpty(manifestRoot))
            {
                return manifestRoot;
            }
            for (int depth = 0; depth < 6 && !String.IsNullOrEmpty(current); depth++)
            {
                if (IsProjectRoot(current))
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
            return Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", ".."));
        }

        private static string ResolveManifestProjectRoot(string appDirectory)
        {
            try
            {
                string manifestPath = Path.Combine(appDirectory, "install-manifest.json");
                if (!File.Exists(manifestPath))
                {
                    return "";
                }
                JavaScriptSerializer serializer = new JavaScriptSerializer();
                Dictionary<string, object> manifest = serializer.Deserialize<Dictionary<string, object>>(
                    File.ReadAllText(manifestPath, Encoding.UTF8)
                );
                object rootValue;
                if (manifest != null && manifest.TryGetValue("project_root", out rootValue))
                {
                    string root = Convert.ToString(rootValue);
                    if (!String.IsNullOrWhiteSpace(root) && IsProjectRoot(root))
                    {
                        return Path.GetFullPath(root);
                    }
                }
            }
            catch
            {
                // Fall through to parent directory probing.
            }
            return "";
        }

        private static bool IsProjectRoot(string path)
        {
            return File.Exists(Path.Combine(path, "sensorbridge.py")) &&
                File.Exists(Path.Combine(path, "windows-app", "Start-SensorBridgeApp.ps1"));
        }

        public static AppOptions Parse(string[] args)
        {
            AppOptions options = new AppOptions();
            for (int index = 0; index < args.Length; index++)
            {
                string arg = args[index];
                string value = index + 1 < args.Length ? args[index + 1] : "";
                if (arg == "--project-root" && value.Length > 0)
                {
                    options.ProjectRoot = Path.GetFullPath(value);
                    index++;
                }
                else if (arg == "--port" && value.Length > 0)
                {
                    int parsed;
                    if (int.TryParse(value, out parsed))
                    {
                        options.Port = parsed;
                    }
                    index++;
                }
                else if (arg == "--host-name" && value.Length > 0)
                {
                    options.HostName = value;
                    index++;
                }
                else if (arg == "--upstream-url" && value.Length > 0)
                {
                    options.UpstreamUrl = value;
                    index++;
                }
            }
            return options;
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly AppOptions _options;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();
        private string _baseUrl;
        private string _language = "zh";
        private Label _titleLabel;
        private Label _subtitleLabel;
        private Label _upstreamLabel;
        private Label _backendLabel;
        private Label _cameraLabel;
        private Label _nextActionLabel;
        private Label _languageLabel;
        private ComboBox _languageSelect;
        private TextBox _upstreamText;
        private Label _serviceStatus;
        private Label _backendStatus;
        private Label _cameraStatus;
        private Label _nextAction;
        private Button _startButton;
        private Button _refreshButton;
        private Button _openButton;
        private Button _helpButton;
        private Button _photoButton;
        private Button _recordButton;
        private PictureBox _previewBox;
        private Label _previewLabel;
        private Label _mediaStatus;
        private System.Windows.Forms.Timer _previewTimer;
        private System.Windows.Forms.Timer _recordTimer;
        private AviRecorder _aviRecorder;
        private NotifyIcon _trayIcon;
        private ContextMenuStrip _trayMenu;
        private ToolStripMenuItem _trayOpenMain;
        private ToolStripMenuItem _trayOpenDashboard;
        private ToolStripMenuItem _trayExit;
        private bool _exitRequested;

        public MainForm(AppOptions options)
        {
            _options = options;
            _json.MaxJsonLength = Int32.MaxValue;
            _json.RecursionLimit = 256;
            _baseUrl = "http://127.0.0.1:" + _options.Port;
            Text = "SensorBridge";
            MinimumSize = new Size(760, 500);
            Size = new Size(860, 560);
            StartPosition = FormStartPosition.CenterScreen;
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            BackColor = Color.FromArgb(245, 247, 250);
            Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);

            BuildLayout();
            BuildTrayIcon();
            BuildPreviewTimer();
            Shown += delegate { StartProductMode(); };
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!_exitRequested && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                HideToTray();
                return;
            }
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            if (_trayIcon != null)
            {
                _trayIcon.Visible = false;
                _trayIcon.Dispose();
            }
            if (_trayMenu != null)
            {
                _trayMenu.Dispose();
            }
            if (_previewTimer != null)
            {
                _previewTimer.Stop();
                _previewTimer.Dispose();
            }
            StopRecording(false);
            if (_previewBox != null && _previewBox.Image != null)
            {
                _previewBox.Image.Dispose();
                _previewBox.Image = null;
            }
            base.OnFormClosed(e);
        }

        private void BuildLayout()
        {
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.RowCount = 4;
            root.ColumnCount = 1;
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 104));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Controls.Add(root);

            Panel header = new Panel();
            header.Dock = DockStyle.Fill;
            header.BackColor = Color.FromArgb(18, 94, 108);
            header.Padding = new Padding(18, 9, 18, 8);
            root.Controls.Add(header, 0, 0);

            _titleLabel = new Label();
            _titleLabel.Text = "SensorBridge";
            _titleLabel.ForeColor = Color.White;
            _titleLabel.Font = new Font("Segoe UI Semibold", 16F, FontStyle.Bold, GraphicsUnit.Point);
            _titleLabel.AutoSize = true;
            _titleLabel.Location = new Point(0, 4);
            header.Controls.Add(_titleLabel);

            _subtitleLabel = new Label();
            _subtitleLabel.ForeColor = Color.FromArgb(218, 242, 240);
            _subtitleLabel.Font = new Font("Segoe UI", 9.5F, FontStyle.Regular, GraphicsUnit.Point);
            _subtitleLabel.AutoSize = true;
            _subtitleLabel.Location = new Point(2, 33);
            header.Controls.Add(_subtitleLabel);

            _helpButton = new Button();
            _helpButton.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            _helpButton.Size = new Size(92, 28);
            _helpButton.Location = new Point(header.ClientSize.Width - _helpButton.Width - 4, 15);
            _helpButton.Click += delegate { ShowUsageHelp(); };
            header.Resize += delegate
            {
                _helpButton.Location = new Point(header.ClientSize.Width - _helpButton.Width - 4, 15);
            };
            header.Controls.Add(_helpButton);

            Panel toolbar = new Panel();
            toolbar.Dock = DockStyle.Fill;
            toolbar.BackColor = Color.White;
            toolbar.Padding = new Padding(14, 7, 14, 7);
            root.Controls.Add(toolbar, 0, 1);

            _upstreamLabel = new Label();
            _upstreamLabel.AutoSize = true;
            _upstreamLabel.ForeColor = Color.FromArgb(62, 73, 84);
            _upstreamLabel.Location = new Point(0, 9);
            toolbar.Controls.Add(_upstreamLabel);

            _upstreamText = new TextBox();
            _upstreamText.Text = _options.UpstreamUrl;
            _upstreamText.Width = 240;
            _upstreamText.Location = new Point(74, 6);
            toolbar.Controls.Add(_upstreamText);

            _startButton = new Button();
            _startButton.Width = 86;
            _startButton.Height = 28;
            _startButton.Location = new Point(326, 5);
            _startButton.Click += delegate { StartProductMode(); };
            toolbar.Controls.Add(_startButton);

            _refreshButton = new Button();
            _refreshButton.Width = 86;
            _refreshButton.Height = 28;
            _refreshButton.Location = new Point(420, 5);
            _refreshButton.Click += delegate { RefreshProductStatus(); };
            toolbar.Controls.Add(_refreshButton);

            _openButton = new Button();
            _openButton.Width = 128;
            _openButton.Height = 28;
            _openButton.Location = new Point(514, 5);
            _openButton.Click += delegate { OpenDashboardInBrowser(); };
            toolbar.Controls.Add(_openButton);

            _languageLabel = new Label();
            _languageLabel.AutoSize = true;
            _languageLabel.ForeColor = Color.FromArgb(62, 73, 84);
            _languageLabel.Location = new Point(652, 9);
            toolbar.Controls.Add(_languageLabel);

            _languageSelect = new ComboBox();
            _languageSelect.DropDownStyle = ComboBoxStyle.DropDownList;
            _languageSelect.Items.Add("English");
            _languageSelect.Items.Add("中文");
            _languageSelect.SelectedIndex = 1;
            _languageSelect.Width = 92;
            _languageSelect.Location = new Point(700, 5);
            _languageSelect.SelectedIndexChanged += delegate
            {
                _language = _languageSelect.SelectedIndex == 1 ? "zh" : "en";
                ApplyLanguage();
            };
            toolbar.Controls.Add(_languageSelect);

            _serviceStatus = new Label();
            _serviceStatus.AutoSize = true;
            _serviceStatus.ForeColor = Color.FromArgb(82, 94, 105);
            _serviceStatus.Location = new Point(804, 9);
            toolbar.Controls.Add(_serviceStatus);

            TableLayoutPanel statusGrid = new TableLayoutPanel();
            statusGrid.Dock = DockStyle.Fill;
            statusGrid.BackColor = Color.FromArgb(245, 247, 250);
            statusGrid.Padding = new Padding(14, 8, 14, 8);
            statusGrid.ColumnCount = 3;
            statusGrid.RowCount = 1;
            for (int i = 0; i < 3; i++)
            {
                statusGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.333F));
            }
            statusGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            root.Controls.Add(statusGrid, 0, 2);

            _backendStatus = AddStatusCard(statusGrid, 0, 0, out _backendLabel);
            _cameraStatus = AddStatusCard(statusGrid, 1, 0, out _cameraLabel);
            _nextAction = AddStatusCard(statusGrid, 2, 0, out _nextActionLabel);

            Panel previewPanel = new Panel();
            previewPanel.Dock = DockStyle.Fill;
            previewPanel.BackColor = Color.White;
            previewPanel.Padding = new Padding(10, 8, 10, 8);
            previewPanel.Margin = new Padding(14, 0, 14, 14);
            root.Controls.Add(previewPanel, 0, 3);

            TableLayoutPanel previewLayout = new TableLayoutPanel();
            previewLayout.Dock = DockStyle.Fill;
            previewLayout.ColumnCount = 1;
            previewLayout.RowCount = 3;
            previewLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
            previewLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            previewLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
            previewPanel.Controls.Add(previewLayout);

            Panel previewHeader = new Panel();
            previewHeader.Dock = DockStyle.Fill;
            previewLayout.Controls.Add(previewHeader, 0, 0);

            _previewLabel = new Label();
            _previewLabel.Dock = DockStyle.Left;
            _previewLabel.Width = 240;
            _previewLabel.ForeColor = Color.FromArgb(28, 39, 50);
            _previewLabel.Font = new Font("Segoe UI Semibold", 10F, FontStyle.Bold, GraphicsUnit.Point);
            _previewLabel.TextAlign = ContentAlignment.MiddleLeft;
            previewHeader.Controls.Add(_previewLabel);

            _recordButton = new Button();
            _recordButton.Dock = DockStyle.Right;
            _recordButton.Width = 104;
            _recordButton.Click += delegate { ToggleRecording(); };
            previewHeader.Controls.Add(_recordButton);

            _photoButton = new Button();
            _photoButton.Dock = DockStyle.Right;
            _photoButton.Width = 92;
            _photoButton.Margin = new Padding(0, 0, 8, 0);
            _photoButton.Click += delegate { SavePhotoFromApp(); };
            previewHeader.Controls.Add(_photoButton);

            AspectRatioPanel videoShell = new AspectRatioPanel();
            videoShell.Dock = DockStyle.Fill;
            videoShell.BackColor = Color.FromArgb(238, 242, 245);
            videoShell.Padding = new Padding(0);
            previewLayout.Controls.Add(videoShell, 0, 1);

            _previewBox = new CropPictureBox();
            _previewBox.BackColor = Color.FromArgb(20, 26, 32);
            videoShell.Controls.Add(_previewBox);

            _mediaStatus = new Label();
            _mediaStatus.Dock = DockStyle.Fill;
            _mediaStatus.ForeColor = Color.FromArgb(82, 94, 105);
            _mediaStatus.TextAlign = ContentAlignment.MiddleLeft;
            previewLayout.Controls.Add(_mediaStatus, 0, 2);

            ApplyLanguage();
        }

        private void BuildPreviewTimer()
        {
            _previewTimer = new System.Windows.Forms.Timer();
            _previewTimer.Interval = 250;
            _previewTimer.Tick += delegate { RefreshNativePreview(); };
            _previewTimer.Start();
        }

        private void RefreshNativePreview()
        {
            if (_previewBox == null || _previewLabel == null)
            {
                return;
            }
            string framePath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "SensorBridge",
                "camera",
                "latest.bmp");
            if (!File.Exists(framePath))
            {
                _previewLabel.Text = L("preview.waiting");
                return;
            }
            try
            {
                using (FileStream stream = new FileStream(framePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (Image loaded = Image.FromStream(stream))
                {
                    Image clone = new Bitmap(loaded);
                    Image old = _previewBox.Image;
                    _previewBox.Image = clone;
                    if (old != null)
                    {
                        old.Dispose();
                    }
                }
                _previewLabel.Text = L("preview.live");
            }
            catch
            {
                _previewLabel.Text = L("preview.waiting");
            }
        }

        private string LatestFramePath()
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "SensorBridge",
                "camera",
                "latest.bmp");
        }

        private void SavePhotoFromApp()
        {
            _photoButton.Enabled = false;
            _mediaStatus.Text = L("photo.saving");
            ThreadPool.QueueUserWorkItem(delegate
            {
                string message;
                try
                {
                    using (WebClient client = new WebClient())
                    {
                        client.Headers[HttpRequestHeader.ContentType] = "application/json";
                        string response = client.UploadString(_baseUrl + "/api/v1/camera/photo", "POST", "{}");
                        Dictionary<string, object> payload = _json.Deserialize<Dictionary<string, object>>(response);
                        message = L("photo.saved") + " " + Value(payload, "filename");
                    }
                }
                catch (Exception ex)
                {
                    message = L("photo.failed") + " " + ex.Message;
                }
                Ui(delegate
                {
                    _mediaStatus.Text = message;
                    _photoButton.Enabled = true;
                });
            });
        }

        private void ToggleRecording()
        {
            if (_aviRecorder != null)
            {
                StopRecording(true);
                return;
            }
            StartRecording();
        }

        private void StartRecording()
        {
            string framePath = LatestFramePath();
            if (!File.Exists(framePath))
            {
                _mediaStatus.Text = L("record.noFrame");
                return;
            }

            try
            {
                using (Image first = LoadFrame(framePath))
                {
                    string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyVideos), "SensorBridge");
                    Directory.CreateDirectory(dir);
                    string stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
                    string target = Path.Combine(dir, "SensorBridge-" + stamp + ".avi");
                    _aviRecorder = new AviRecorder();
                    _aviRecorder.Begin(target, first.Width, first.Height, 15);
                    _aviRecorder.AddFrame(first);
                }

                _recordTimer = new System.Windows.Forms.Timer();
                _recordTimer.Interval = 67;
                _recordTimer.Tick += delegate { RecordOneFrame(); };
                _recordTimer.Start();
                _recordButton.Text = L("record.stop");
                _mediaStatus.Text = L("record.recording");
            }
            catch (Exception ex)
            {
                StopRecording(false);
                _mediaStatus.Text = L("record.failed") + " " + ex.Message;
            }
        }

        private void RecordOneFrame()
        {
            if (_aviRecorder == null)
            {
                return;
            }
            try
            {
                using (Image frame = LoadFrame(LatestFramePath()))
                {
                    _aviRecorder.AddFrame(frame);
                }
                _mediaStatus.Text = L("record.recording") + " " + _aviRecorder.FrameCount + " " + L("record.frames");
            }
            catch
            {
                // Skip transient frame-write collisions; newest-frame recording continues on the next timer tick.
            }
        }

        private void StopRecording(bool openFolder)
        {
            if (_recordTimer != null)
            {
                _recordTimer.Stop();
                _recordTimer.Dispose();
                _recordTimer = null;
            }
            AviRecorder recorder = _aviRecorder;
            _aviRecorder = null;
            if (recorder == null)
            {
                return;
            }
            string path = recorder.Path;
            int frames = recorder.FrameCount;
            recorder.End();
            recorder.Dispose();
            if (_recordButton != null)
            {
                _recordButton.Text = L("record.start");
            }
            if (_mediaStatus != null)
            {
                _mediaStatus.Text = L("record.saved") + " " + Path.GetFileName(path) + " (" + frames + " " + L("record.frames") + ")";
            }
            if (openFolder)
            {
                Process.Start("explorer.exe", "/select,\"" + path + "\"");
            }
        }

        private static Image LoadFrame(string framePath)
        {
            using (FileStream stream = new FileStream(framePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (Image loaded = Image.FromStream(stream))
            {
                return new Bitmap(loaded);
            }
        }

        private void BuildTrayIcon()
        {
            _trayMenu = new ContextMenuStrip();
            _trayOpenMain = new ToolStripMenuItem("Open Main Window", null, delegate { ShowMainWindow(); });
            _trayOpenDashboard = new ToolStripMenuItem("Open Dashboard", null, delegate { OpenDashboardInBrowser(); });
            _trayExit = new ToolStripMenuItem("Exit", null, delegate { ExitApplication(); });
            _trayMenu.Items.Add(_trayOpenMain);
            _trayMenu.Items.Add(_trayOpenDashboard);
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add(_trayExit);

            _trayIcon = new NotifyIcon();
            _trayIcon.Icon = Icon;
            _trayIcon.Text = "SensorBridge Camera";
            _trayIcon.ContextMenuStrip = _trayMenu;
            _trayIcon.Visible = true;
            _trayIcon.DoubleClick += delegate { ShowMainWindow(); };
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

        private void ShowMainWindow()
        {
            ShowInTaskbar = true;
            Show();
            WindowState = FormWindowState.Normal;
            Activate();
        }

        private void ExitApplication()
        {
            if (_exitRequested)
            {
                return;
            }
            _exitRequested = true;
            if (_trayIcon != null)
            {
                _trayIcon.Visible = false;
            }
            ThreadPool.QueueUserWorkItem(delegate
            {
                ShutdownBackend();
                Ui(delegate { Application.Exit(); });
            });
        }

        private void ShutdownBackend()
        {
            try
            {
                using (WebClient client = new WebClient())
                {
                    client.Headers[HttpRequestHeader.ContentType] = "application/json";
                    client.UploadString(_baseUrl + "/api/v1/app/shutdown", "POST", "{}");
                }
            }
            catch
            {
                // Exit should still close the UI if the local backend is already gone.
            }
        }

        private static Label AddStatusCard(TableLayoutPanel panel, int column, int row, out Label key)
        {
            Panel card = new Panel();
            card.Dock = DockStyle.Fill;
            card.Margin = new Padding(5);
            card.Padding = new Padding(0);
            card.BackColor = Color.White;
            panel.Controls.Add(card, column, row);

            Panel accent = new Panel();
            accent.Dock = DockStyle.Left;
            accent.Width = 4;
            accent.BackColor = Color.FromArgb(44, 180, 155);
            card.Controls.Add(accent);

            Label keyLabel = new Label();
            keyLabel.Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right;
            keyLabel.Location = new Point(16, 8);
            keyLabel.Size = new Size(300, 16);
            keyLabel.TextAlign = ContentAlignment.MiddleLeft;
            keyLabel.ForeColor = Color.FromArgb(92, 104, 116);
            keyLabel.Font = new Font("Segoe UI Semibold", 8.5F, FontStyle.Bold, GraphicsUnit.Point);
            keyLabel.AutoEllipsis = true;
            card.Controls.Add(keyLabel);
            key = keyLabel;

            Label value = new Label();
            value.Text = "-";
            value.Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right;
            value.Location = new Point(16, 27);
            value.Size = new Size(300, 18);
            value.TextAlign = ContentAlignment.MiddleLeft;
            value.ForeColor = Color.FromArgb(28, 39, 50);
            value.Font = new Font("Segoe UI", 8.75F, FontStyle.Regular, GraphicsUnit.Point);
            value.AutoEllipsis = true;
            card.Controls.Add(value);
            card.Resize += delegate
            {
                int width = Math.Max(40, card.ClientSize.Width - 28);
                keyLabel.Width = width;
                value.Width = width;
            };
            return value;
        }

        private void StartProductMode()
        {
            if (_startButton.Enabled == false)
            {
                return;
            }
            _startButton.Enabled = false;
            _serviceStatus.Text = L("service.starting");
            _backendStatus.Text = L("backend.configuring") + " " + _upstreamText.Text;
            _nextAction.Text = L("next.waiting");
            ScheduleDashboardNavigation();

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<string, object> result = RunProductMode();
                    object baseUrlValue = GetPath(result, "base_url");
                    if (baseUrlValue != null)
                    {
                        _baseUrl = Convert.ToString(baseUrlValue);
                    }
                    Ui(delegate
                    {
                        _serviceStatus.Text = L("service.running") + " " + _baseUrl;
                    });
                    RefreshProductStatus();
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceStatus.Text = L("service.startFailed");
                        _nextAction.Text = exc.Message;
                    });
                }
                finally
                {
                    Ui(delegate { _startButton.Enabled = true; });
                }
            });
        }

        private Dictionary<string, object> RunProductMode()
        {
            string script = Path.Combine(_options.ProjectRoot, "windows-app", "Start-SensorBridgeApp.ps1");
            if (!File.Exists(script))
            {
                throw new FileNotFoundException("Missing launcher script", script);
            }

            StringBuilder arguments = new StringBuilder();
            arguments.Append("-NoProfile -ExecutionPolicy Bypass -File ");
            arguments.Append(Quote(script));
            arguments.Append(" -Port ").Append(_options.Port);
            arguments.Append(" -HostName ").Append(Quote(_options.HostName));
            arguments.Append(" -UpstreamUrl ").Append(Quote(_upstreamText.Text));
            arguments.Append(" -ProductMode -Json");

            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = "powershell.exe";
            startInfo.Arguments = arguments.ToString();
            startInfo.WorkingDirectory = _options.ProjectRoot;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            startInfo.RedirectStandardOutput = true;
            startInfo.RedirectStandardError = true;

            using (Process process = Process.Start(startInfo))
            {
                string output = process.StandardOutput.ReadToEnd();
                string error = process.StandardError.ReadToEnd();
                process.WaitForExit();
                if (process.ExitCode != 0)
                {
                    throw new InvalidOperationException(TrimForUi(error.Length > 0 ? error : output));
                }
                string json = ExtractJsonObject(output);
                return _json.Deserialize<Dictionary<string, object>>(json);
            }
        }

        private void ScheduleDashboardNavigation()
        {
            string baseUrl = _baseUrl;
            ThreadPool.QueueUserWorkItem(delegate
            {
                for (int attempt = 0; attempt < 30; attempt++)
                {
                    try
                    {
                        using (WebClient client = new WebClient())
                        {
                            client.DownloadString(baseUrl + "/health");
                        }
                        return;
                    }
                    catch
                    {
                        Thread.Sleep(1000);
                    }
                }
            });
        }

        private void RefreshProductStatus()
        {
            _refreshButton.Enabled = false;
            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    string raw;
                    using (WebClient client = new WebClient())
                    {
                        client.Encoding = Encoding.UTF8;
                        raw = client.DownloadString(_baseUrl + "/api/v1/product/status");
                    }
                    Dictionary<string, object> status = _json.Deserialize<Dictionary<string, object>>(raw);
                    Ui(delegate { RenderProductStatus(status); });
                }
                catch (Exception exc)
                {
                    Ui(delegate
                    {
                        _serviceStatus.Text = L("service.statusUnavailable");
                        _nextAction.Text = exc.Message;
                    });
                }
                finally
                {
                    Ui(delegate { _refreshButton.Enabled = true; });
                }
            });
        }

        private void RenderProductStatus(Dictionary<string, object> status)
        {
            _backendStatus.Text = TransportLine(status);

            _cameraStatus.Text = CameraTruthLine(status);

            string next = FirstNonEmpty(
                Value(status, "camera.reason"),
                Value(status, "webrtc.product_incomplete_reason"),
                Value(status, "webrtc.fallback_reason"),
                L("next.readyWhereSupported"));
            _nextAction.Text = next;
            _serviceStatus.Text = L("service.running") + " " + _baseUrl;
        }

        private string TransportLine(Dictionary<string, object> status)
        {
            string transport = Value(status, "activeCameraTransport");
            if (String.Equals(transport, "webrtc", StringComparison.OrdinalIgnoreCase))
            {
                return L("transport.webrtcActive");
            }
            if (String.IsNullOrWhiteSpace(transport))
            {
                return L("transport.waiting");
            }
            return transport;
        }

        private string CameraTruthLine(Dictionary<string, object> status)
        {
            string state = CameraStateText(Value(status, "camera.status"));
            string windowsCamera = BoolValue(status, "normalWindowsCameraVisible")
                ? L("camera.windowsUsable")
                : L("camera.windowsUnavailable");
            string fps = FpsValue(status, "virtualCameraFps");
            if (fps == "-")
            {
                fps = FpsValue(status, "receivedFps");
            }
            return JoinParts(state, windowsCamera, fps);
        }

        private string CameraStateText(string state)
        {
            if (String.Equals(state, "active", StringComparison.OrdinalIgnoreCase))
            {
                return L("camera.active");
            }
            if (String.Equals(state, "unavailable", StringComparison.OrdinalIgnoreCase))
            {
                return L("camera.unavailable");
            }
            return String.IsNullOrWhiteSpace(state) ? L("camera.waiting") : state;
        }

        private static string FpsValue(Dictionary<string, object> status, string key)
        {
            string raw = Value(status, key);
            double value;
            if (Double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out value) ||
                Double.TryParse(raw, out value))
            {
                return value.ToString("0.#", CultureInfo.InvariantCulture) + " fps";
            }
            return "-";
        }

        private static string JoinParts(params string[] parts)
        {
            List<string> clean = new List<string>();
            foreach (string part in parts)
            {
                if (!String.IsNullOrWhiteSpace(part))
                {
                    clean.Add(part);
                }
            }
            return clean.Count == 0 ? "-" : String.Join(" / ", clean.ToArray());
        }

        private static string FirstNonEmpty(params string[] values)
        {
            foreach (string value in values)
            {
                if (!String.IsNullOrWhiteSpace(value))
                {
                    return value;
                }
            }
            return "-";
        }

        private void OpenDashboardInBrowser()
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = DashboardUrl();
            startInfo.UseShellExecute = true;
            Process.Start(startInfo);
        }

        private string DashboardUrl()
        {
            return _baseUrl + "/?lang=" + (_language == "zh" ? "zh" : "en") + "&host=app&view=compact";
        }

        private void ShowUsageHelp()
        {
            MessageBox.Show(this, L("help.body"), L("help.title"), MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void ApplyLanguage()
        {
            _titleLabel.Text = "SensorBridge";
            _subtitleLabel.Text = L("app.subtitle");
            if (_helpButton != null)
            {
                _helpButton.Text = L("help.button");
            }
            _upstreamLabel.Text = L("backend.url");
            _startButton.Text = L("button.start");
            _refreshButton.Text = L("button.refresh");
            _openButton.Text = L("button.openDashboard");
            if (_photoButton != null)
            {
                _photoButton.Text = L("photo.button");
            }
            if (_recordButton != null)
            {
                _recordButton.Text = _aviRecorder == null ? L("record.start") : L("record.stop");
            }
            _languageLabel.Text = L("common.language");
            _backendLabel.Text = L("label.backend");
            _cameraLabel.Text = L("label.camera");
            _nextActionLabel.Text = L("label.nextAction");
            if (_previewLabel != null)
            {
                _previewLabel.Text = L("preview.waiting");
            }
            if (_mediaStatus != null && _mediaStatus.Text.Length == 0)
            {
                _mediaStatus.Text = L("media.ready");
            }
            if (_trayOpenMain != null)
            {
                _trayOpenMain.Text = L("tray.openMain");
                _trayOpenDashboard.Text = L("tray.openDashboard");
                _trayExit.Text = L("tray.exit");
            }
            if (_serviceStatus.Text.Length == 0 || _serviceStatus.Text == "Service: not started" || _serviceStatus.Text == "服务：未启动")
            {
                _serviceStatus.Text = L("service.notStarted");
            }
        }

        private string LZh(string key)
        {
            switch (key)
            {
                case "backend.url": return "iPad 地址";
                case "app.subtitle": return "iPad 摄像头到 Windows 虚拟摄像头";
                case "common.language": return "语言";
                case "button.start": return "启动";
                case "button.refresh": return "刷新";
                case "button.openDashboard": return "诊断网页";
                case "help.button": return "使用说明";
                case "help.title": return "使用说明";
                case "help.body": return "1. 确认 iPad 和电脑在同一局域网。\n2. iPad 地址保持为 http://192.168.0.24:27180，点“启动”。\n3. 看到“WebRTC 已连接”和实时预览后，在会议软件里选择 SensorBridge Camera。\n4. 点“拍照”保存当前画面到图片文件夹。\n5. 点“开始录像”，再次点击停止并保存到视频文件夹。\n6. 如果会议软件没有画面，先点“刷新”，再打开“诊断网页”查看状态。";
                case "label.backend": return "连接";
                case "label.camera": return "摄像头";
                case "label.nextAction": return "状态";
                case "transport.webrtcActive": return "WebRTC 已连接";
                case "transport.waiting": return "等待连接";
                case "service.notStarted": return "服务：未启动";
                case "service.starting": return "服务：正在启动摄像头...";
                case "service.running": return "服务：运行于";
                case "service.startFailed": return "服务：启动失败";
                case "service.statusUnavailable": return "服务：状态不可用";
                case "backend.configuring": return "正在连接";
                case "next.waiting": return "等待摄像头状态";
                case "next.readyWhereSupported": return "摄像头已就绪";
                case "truth.complete": return "完成";
                case "truth.notComplete": return "未完成";
                case "truth.visible": return "可见";
                case "truth.notVisible": return "不可见";
                case "camera.windowsUsable": return "Windows 可用";
                case "camera.windowsUnavailable": return "Windows 不可用";
                case "camera.directshowUsable": return "DirectShow 可用";
                case "camera.directshowNotReady": return "DirectShow 未就绪";
                case "camera.active": return "已连接";
                case "camera.unavailable": return "不可用";
                case "camera.waiting": return "等待视频";
                case "fps.received": return "接收";
                case "fps.decoded": return "解码";
                case "fps.virtualCamera": return "虚拟相机";
                case "preview.live": return "实时预览";
                case "preview.waiting": return "等待视频帧";
                case "media.ready": return "可拍照或录像";
                case "photo.button": return "拍照";
                case "photo.saving": return "正在保存照片...";
                case "photo.saved": return "照片已保存：";
                case "photo.failed": return "拍照失败：";
                case "record.start": return "开始录像";
                case "record.stop": return "停止录像";
                case "record.noFrame": return "还没有视频帧，不能录像";
                case "record.recording": return "正在录像";
                case "record.frames": return "帧";
                case "record.saved": return "录像已保存：";
                case "record.failed": return "录像失败：";
                case "tray.openMain": return "打开主界面";
                case "tray.openDashboard": return "打开网页控制台";
                case "tray.exit": return "退出";
            }
            return key;
        }

        private string L(string key)
        {
            if (_language == "zh")
            {
                return LZh(key);
            }
            switch (key)
            {
                case "backend.url": return "Backend URL";
                case "app.subtitle": return "Use your iPad as a Windows virtual camera";
                case "common.language": return "Language";
                case "button.start": return "Start";
                case "button.refresh": return "Refresh";
                case "button.openDashboard": return "Diagnostics";
                case "help.button": return "Help";
                case "help.title": return "How to use SensorBridge";
                case "help.body": return "1. Keep the iPad and this PC on the same LAN.\n2. Keep the iPad URL as http://192.168.0.24:27180, then click Start.\n3. When WebRTC is connected and preview is live, choose SensorBridge Camera in your meeting app.\n4. Click Photo to save the current frame to Pictures.\n5. Click Record, then Stop to save an AVI file to Videos.\n6. If a meeting app has no video, click Refresh first, then open Diagnostics.";
                case "label.backend": return "Backend";
                case "label.camera": return "Camera";
                case "label.nextAction": return "Next action";
                case "transport.webrtcActive": return "WebRTC connected";
                case "transport.waiting": return "Waiting for connection";
                case "service.notStarted": return "Service: not started";
                case "service.starting": return "Service: starting Product Mode...";
                case "service.running": return "Service: running at";
                case "service.startFailed": return "Service: start failed";
                case "service.statusUnavailable": return "Service: status unavailable";
                case "backend.configuring": return "Configuring";
                case "next.waiting": return "Waiting for Product Mode acceptance probes";
                case "next.readyWhereSupported": return "Ready where supported; see dashboard for full blocker list.";
                case "truth.complete": return "complete";
                case "truth.notComplete": return "not complete";
                case "truth.visible": return "visible";
                case "truth.notVisible": return "not visible";
                case "camera.windowsUsable": return "Windows Camera usable";
                case "camera.windowsUnavailable": return "Windows Camera unavailable";
                case "camera.directshowUsable": return "DirectShow usable";
                case "camera.directshowNotReady": return "DirectShow not ready";
                case "camera.active": return "Connected";
                case "camera.unavailable": return "Unavailable";
                case "camera.waiting": return "Waiting for video";
                case "fps.received": return "rx";
                case "fps.decoded": return "dec";
                case "fps.virtualCamera": return "camera";
                case "preview.live": return "Live preview";
                case "preview.waiting": return "Waiting for video";
                case "media.ready": return "Ready for photos or recording";
                case "photo.button": return "Photo";
                case "photo.saving": return "Saving photo...";
                case "photo.saved": return "Photo saved:";
                case "photo.failed": return "Photo failed:";
                case "record.start": return "Record";
                case "record.stop": return "Stop";
                case "record.noFrame": return "No video frame is available yet.";
                case "record.recording": return "Recording";
                case "record.frames": return "frames";
                case "record.saved": return "Recording saved:";
                case "record.failed": return "Recording failed:";
                case "tray.openMain": return "Open Main Window";
                case "tray.openDashboard": return "Open Dashboard";
                case "tray.exit": return "Exit";
            }
            return key;
        }

        private static string Value(Dictionary<string, object> root, string path)
        {
            object value = GetPath(root, path);
            return value == null ? "" : Convert.ToString(value);
        }

        private static bool BoolValue(Dictionary<string, object> root, string path)
        {
            object value = GetPath(root, path);
            if (value is bool)
            {
                return (bool)value;
            }
            bool parsed;
            return value != null && bool.TryParse(Convert.ToString(value), out parsed) && parsed;
        }

        private static object GetPath(Dictionary<string, object> root, string path)
        {
            object current = root;
            string[] parts = path.Split('.');
            foreach (string part in parts)
            {
                Dictionary<string, object> dict = current as Dictionary<string, object>;
                if (dict == null || !dict.ContainsKey(part))
                {
                    return null;
                }
                current = dict[part];
            }
            return current;
        }

        private static string Quote(string value)
        {
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }

        private static string ExtractJsonObject(string output)
        {
            int start = output.IndexOf('{');
            int end = output.LastIndexOf('}');
            if (start < 0 || end <= start)
            {
                throw new InvalidOperationException("Product Mode did not return JSON.");
            }
            return output.Substring(start, end - start + 1);
        }

        private static string TrimForUi(string value)
        {
            value = (value ?? "").Trim();
            if (value.Length <= 600)
            {
                return value;
            }
            return value.Substring(0, 600) + "...";
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
