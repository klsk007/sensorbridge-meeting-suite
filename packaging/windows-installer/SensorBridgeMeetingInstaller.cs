using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Principal;
using System.Threading;
using System.Windows.Forms;

namespace SensorBridge.Meeting.Installer
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }
    }

    internal sealed class InstallerForm : Form
    {
        private const string PayloadResourceName = "SensorBridgeMeetingSuitePayload.zip";
        private const string VbCableUrl = "https://vb-audio.com/Cable/";
        private const string BundledPythonVersion = "3.12.3";

        private readonly TextBox _installDirText;
        private readonly Button _browseButton;
        private readonly CheckBox _installDepsCheck;
        private readonly CheckBox _registerCameraCheck;
        private readonly CheckBox _launchAfterInstallCheck;
        private readonly ProgressBar _progress;
        private readonly Label _statusLabel;
        private readonly TextBox _logText;
        private readonly ListView _preflightList;
        private readonly Button _preflightButton;
        private readonly Button _installButton;
        private readonly Button _closeButton;
        private readonly Label _vbCableHelpLabel;
        private readonly TextBox _vbCableUrlText;
        private readonly Button _copyVbCableUrlButton;
        private volatile bool _installing;
        private volatile bool _vbCableMissing;

        public InstallerForm()
        {
            Text = "SensorBridge Meeting Suite 安装器";
            StartPosition = FormStartPosition.CenterScreen;
            Size = new Size(980, 660);
            MinimumSize = new Size(860, 600);
            Font = new Font("Microsoft YaHei UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            BackColor = Color.FromArgb(246, 248, 250);

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 86;
            header.BackColor = Color.FromArgb(27, 92, 108);
            header.Padding = new Padding(22, 14, 22, 10);
            Controls.Add(header);

            Label title = new Label();
            title.Text = "SensorBridge Meeting Suite";
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 20F, FontStyle.Bold, GraphicsUnit.Point);
            title.AutoSize = true;
            title.Location = new Point(20, 12);
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "一键安装会议摄像头、麦克风、扬声器桥接工具";
            subtitle.ForeColor = Color.FromArgb(220, 243, 240);
            subtitle.AutoSize = true;
            subtitle.Location = new Point(23, 55);
            header.Controls.Add(subtitle);

            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.None;
            root.Location = new Point(0, header.Height);
            root.Size = new Size(ClientSize.Width, ClientSize.Height - header.Height);
            root.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            root.ColumnCount = 1;
            root.RowCount = 6;
            root.Padding = new Padding(22, 16, 22, 16);
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 72));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 98));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 54));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 76));
            Controls.Add(root);

            Panel pathPanel = new Panel();
            pathPanel.Dock = DockStyle.Fill;
            root.Controls.Add(pathPanel, 0, 0);

            Label pathLabel = new Label();
            pathLabel.Text = "安装位置";
            pathLabel.AutoSize = true;
            pathLabel.Location = new Point(0, 0);
            pathPanel.Controls.Add(pathLabel);

            _installDirText = new TextBox();
            _installDirText.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top;
            _installDirText.Location = new Point(0, 26);
            _installDirText.Width = 590;
            _installDirText.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SensorBridgeMeetingSuite");
            pathPanel.Controls.Add(_installDirText);

            _browseButton = new Button();
            _browseButton.Text = "浏览...";
            _browseButton.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            _browseButton.Location = new Point(606, 24);
            _browseButton.Size = new Size(96, 28);
            _browseButton.Click += delegate { BrowseInstallDir(); };
            pathPanel.Controls.Add(_browseButton);
            pathPanel.Resize += delegate
            {
                _browseButton.Left = Math.Max(0, pathPanel.ClientSize.Width - _browseButton.Width);
                _installDirText.Width = Math.Max(120, _browseButton.Left - 14);
            };

            Panel optionsPanel = new Panel();
            optionsPanel.Dock = DockStyle.Fill;
            root.Controls.Add(optionsPanel, 0, 1);

            _installDepsCheck = new CheckBox();
            _installDepsCheck.Text = "自动安装/修复 Python 3.12.3 和音视频依赖（随包离线资源优先）";
            _installDepsCheck.Checked = true;
            _installDepsCheck.AutoSize = true;
            _installDepsCheck.Location = new Point(0, 4);
            optionsPanel.Controls.Add(_installDepsCheck);

            _registerCameraCheck = new CheckBox();
            _registerCameraCheck.AutoSize = true;
            _registerCameraCheck.Location = new Point(0, 34);
            if (IsAdministrator())
            {
                _registerCameraCheck.Text = "注册 SensorBridge Camera 虚拟摄像头";
                _registerCameraCheck.Checked = true;
            }
            else
            {
                _registerCameraCheck.Text = "注册 SensorBridge Camera 虚拟摄像头（需要右键以管理员运行）";
                _registerCameraCheck.Checked = false;
                _registerCameraCheck.Enabled = false;
            }
            optionsPanel.Controls.Add(_registerCameraCheck);

            _launchAfterInstallCheck = new CheckBox();
            _launchAfterInstallCheck.Text = "安装完成后打开 SensorBridge Meeting Suite";
            _launchAfterInstallCheck.Checked = true;
            _launchAfterInstallCheck.AutoSize = true;
            _launchAfterInstallCheck.Location = new Point(0, 64);
            optionsPanel.Controls.Add(_launchAfterInstallCheck);

            Panel progressPanel = new Panel();
            progressPanel.Dock = DockStyle.Fill;
            root.Controls.Add(progressPanel, 0, 2);

            _statusLabel = new Label();
            _statusLabel.Text = "准备安装";
            _statusLabel.AutoSize = true;
            _statusLabel.Location = new Point(0, 0);
            progressPanel.Controls.Add(_statusLabel);

            _progress = new ProgressBar();
            _progress.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top;
            _progress.Location = new Point(0, 25);
            _progress.Width = 700;
            _progress.Height = 20;
            progressPanel.Controls.Add(_progress);
            progressPanel.Resize += delegate { _progress.Width = progressPanel.ClientSize.Width; };

            TableLayoutPanel checkAndLog = new TableLayoutPanel();
            checkAndLog.Dock = DockStyle.Fill;
            checkAndLog.ColumnCount = 2;
            checkAndLog.RowCount = 1;
            checkAndLog.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 55));
            checkAndLog.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 45));
            checkAndLog.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.Controls.Add(checkAndLog, 0, 3);

            Panel logPanel = new Panel();
            logPanel.Dock = DockStyle.Fill;
            logPanel.Margin = new Padding(0, 0, 8, 0);
            checkAndLog.Controls.Add(logPanel, 0, 0);

            Label logLabel = new Label();
            logLabel.Text = "安装日志";
            logLabel.Dock = DockStyle.Top;
            logLabel.Height = 24;

            _logText = new TextBox();
            _logText.Dock = DockStyle.Fill;
            _logText.Multiline = true;
            _logText.ReadOnly = true;
            _logText.ScrollBars = ScrollBars.Vertical;
            _logText.BackColor = Color.White;
            _logText.Font = new Font("Consolas", 9F, FontStyle.Regular, GraphicsUnit.Point);
            logPanel.Controls.Add(_logText);
            logPanel.Controls.Add(logLabel);

            Panel preflightPanel = new Panel();
            preflightPanel.Dock = DockStyle.Fill;
            preflightPanel.Margin = new Padding(8, 0, 0, 0);
            checkAndLog.Controls.Add(preflightPanel, 1, 0);

            Label preflightLabel = new Label();
            preflightLabel.Text = "安装前检查";
            preflightLabel.Dock = DockStyle.Top;
            preflightLabel.Height = 24;

            _preflightList = new ListView();
            _preflightList.Dock = DockStyle.Fill;
            _preflightList.View = View.Details;
            _preflightList.FullRowSelect = true;
            _preflightList.GridLines = true;
            _preflightList.HeaderStyle = ColumnHeaderStyle.Nonclickable;
            _preflightList.Columns.Add("项目", 92);
            _preflightList.Columns.Add("状态", 72);
            _preflightList.Columns.Add("推荐版本 / 说明", 230);
            preflightPanel.Controls.Add(_preflightList);
            preflightPanel.Controls.Add(preflightLabel);
            preflightPanel.Resize += delegate
            {
                int width = Math.Max(260, _preflightList.ClientSize.Width);
                _preflightList.Columns[0].Width = Math.Max(76, width / 4);
                _preflightList.Columns[1].Width = 72;
                _preflightList.Columns[2].Width = Math.Max(120, width - _preflightList.Columns[0].Width - _preflightList.Columns[1].Width - 8);
            };

            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.Dock = DockStyle.Fill;
            buttons.FlowDirection = FlowDirection.RightToLeft;
            buttons.WrapContents = false;
            root.Controls.Add(buttons, 0, 4);

            _closeButton = new Button();
            _closeButton.Text = "关闭";
            _closeButton.Size = new Size(96, 32);
            _closeButton.Margin = new Padding(10, 4, 0, 0);
            _closeButton.Click += delegate { Close(); };
            buttons.Controls.Add(_closeButton);

            _installButton = new Button();
            _installButton.Text = "开始一键安装";
            _installButton.Size = new Size(150, 32);
            _installButton.Margin = new Padding(10, 4, 0, 0);
            _installButton.Click += delegate { StartInstall(); };
            buttons.Controls.Add(_installButton);

            _preflightButton = new Button();
            _preflightButton.Text = "安装前检查";
            _preflightButton.Size = new Size(120, 32);
            _preflightButton.Margin = new Padding(10, 4, 0, 0);
            _preflightButton.Click += delegate { StartPreflightCheck(); };
            buttons.Controls.Add(_preflightButton);

            Panel vbCablePanel = new Panel();
            vbCablePanel.Dock = DockStyle.Fill;
            root.Controls.Add(vbCablePanel, 0, 5);

            _vbCableHelpLabel = new Label();
            _vbCableHelpLabel.Text = "提示：VB-CABLE 属于第三方系统音频驱动，安装器会检测它，但不会静默安装。";
            _vbCableHelpLabel.ForeColor = Color.FromArgb(86, 99, 112);
            _vbCableHelpLabel.AutoSize = true;
            _vbCableHelpLabel.Location = new Point(0, 2);
            vbCablePanel.Controls.Add(_vbCableHelpLabel);

            _vbCableUrlText = new TextBox();
            _vbCableUrlText.ReadOnly = true;
            _vbCableUrlText.Text = VbCableUrl;
            _vbCableUrlText.Visible = false;
            _vbCableUrlText.Location = new Point(0, 30);
            _vbCableUrlText.Width = 560;
            vbCablePanel.Controls.Add(_vbCableUrlText);

            _copyVbCableUrlButton = new Button();
            _copyVbCableUrlButton.Text = "复制网址";
            _copyVbCableUrlButton.Visible = false;
            _copyVbCableUrlButton.Size = new Size(96, 26);
            _copyVbCableUrlButton.Location = new Point(574, 28);
            _copyVbCableUrlButton.Click += delegate { CopyVbCableUrl(); };
            vbCablePanel.Controls.Add(_copyVbCableUrlButton);
            vbCablePanel.Resize += delegate
            {
                _copyVbCableUrlButton.Left = Math.Max(0, vbCablePanel.ClientSize.Width - _copyVbCableUrlButton.Width);
                _vbCableUrlText.Width = Math.Max(140, _copyVbCableUrlButton.Left - 14);
            };

            InitializePreflightList();
            AppendLog("安装器已准备好。");
            if (!IsAdministrator())
            {
                AppendLog("当前不是管理员模式；如需注册虚拟摄像头，请右键安装器并选择“以管理员身份运行”。");
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (_installing)
            {
                e.Cancel = true;
                MessageBox.Show("安装正在进行，请等待完成。", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            base.OnFormClosing(e);
        }

        private void BrowseInstallDir()
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择安装位置";
                dialog.SelectedPath = _installDirText.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    _installDirText.Text = dialog.SelectedPath;
                }
            }
        }

        private void InitializePreflightList()
        {
            _preflightList.Items.Clear();
            SetPreflightItem("python", "Python", "待检查", "推荐：Python 3.10+；如缺失，安装器会自动安装 Python " + BundledPythonVersion + "。", Color.FromArgb(86, 99, 112));
            SetPreflightItem("vbcable", "VB-CABLE", "待检查", "推荐：官方 VBCABLE_Driver_Pack45；因第三方驱动授权限制只提供下载链接，名字不同可在主程序手动选择。", Color.FromArgb(86, 99, 112));
        }

        private void StartPreflightCheck()
        {
            if (_installing)
            {
                return;
            }

            SetControlsEnabled(false);
            SetProgress(0, "安装前检查中");
            AppendLog("开始安装前检查。");
            InitializePreflightList();

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    RunPreflightCheck();
                    SetProgress(100, "安装前检查完成");
                    AppendLog("安装前检查完成。");
                }
                catch (Exception exc)
                {
                    AppendLog("安装前检查失败：" + exc.Message);
                    SetProgress(100, "安装前检查失败");
                }
                finally
                {
                    Ui(delegate { SetControlsEnabled(true); });
                }
            });
        }

        private void RunPreflightCheck()
        {
            CheckPythonRuntime();
            CheckVbCable();
        }

        private PythonInfo CheckPythonRuntime()
        {
            PythonInfo python = new PythonInfo { Found = false, Command = "", Prefix = "", Version = "" };
            foreach (string version in new string[] { "3.12", "3.11", "3.10" })
            {
                python = TryResolvePython("py.exe", "-" + version);
                if (python.Found) { break; }
            }
            if (!python.Found)
            {
                python = TryResolvePython("python.exe", "");
            }

            if (!python.Found)
            {
                SetPreflightItem("python", "Python", "将自动安装", "未检测到 Python 3.10+；一键安装时将随包安装 Python " + BundledPythonVersion + "。", Color.FromArgb(151, 75, 0));
                return python;
            }

            if (CompareVersion(python.Version, "3.10") >= 0)
            {
                SetPreflightItem("python", "Python", "通过", "当前 " + python.Version + "；推荐 Python 3.10+，满足后无需更新。", Color.SeaGreen);
            }
            else
            {
                SetPreflightItem("python", "Python", "将自动安装", "当前 " + python.Version + "；低于 3.10，一键安装时将随包安装 Python " + BundledPythonVersion + "。", Color.FromArgb(151, 75, 0));
            }
            return python;
        }

        private PythonInfo TryResolvePython(string command, string prefix)
        {
            string code = "import sys; print('%d.%d.%d' % sys.version_info[:3])";
            string args = (String.IsNullOrWhiteSpace(prefix) ? "" : prefix + " ") + "-c " + Quote(code);
            ProcessResult result = RunProcessCapture(command, args, 12000);
            if (result.ExitCode == 0 && !String.IsNullOrWhiteSpace(result.Output))
            {
                return new PythonInfo
                {
                    Found = true,
                    Command = command,
                    Prefix = prefix,
                    Version = FirstNonEmptyLine(result.Output)
                };
            }
            return new PythonInfo { Found = false, Command = command, Prefix = prefix, Version = "" };
        }

        private void CheckVbCable()
        {
            string command = "$names=@(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'CABLE Input|CABLE Output|VB-Audio|VB-CABLE' } | ForEach-Object { $_.Name }); $names -join [Environment]::NewLine";
            ProcessResult result = RunProcessCapture("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -Command " + Quote(command), 20000);
            string output = (result.Output ?? "") + Environment.NewLine + (result.Error ?? "");
            bool hasInput = output.IndexOf("CABLE Input", StringComparison.OrdinalIgnoreCase) >= 0;
            bool hasOutput = output.IndexOf("CABLE Output", StringComparison.OrdinalIgnoreCase) >= 0;
            bool hasAny = output.IndexOf("VB-Audio", StringComparison.OrdinalIgnoreCase) >= 0 || output.IndexOf("VB-CABLE", StringComparison.OrdinalIgnoreCase) >= 0;

            if (hasInput && hasOutput)
            {
                SetPreflightItem("vbcable", "VB-CABLE", "通过", "检测到默认播放端/录音端；无需重装或更新。", Color.SeaGreen);
            }
            else if (hasAny)
            {
                SetPreflightItem("vbcable", "VB-CABLE", "需手动选择", "检测到 VB-Audio 设备但不是默认名；安装后在主程序点“刷新音频设备”并手动选择。", Color.FromArgb(151, 75, 0));
            }
            else
            {
                SetPreflightItem("vbcable", "VB-CABLE", "需用户安装", "因第三方驱动授权限制不会静默安装；下载/安装/卸载：" + VbCableUrl, Color.Firebrick);
                ShowVbCableHelp(VbCableUrl);
            }
        }

        private void SetPreflightItem(string key, string name, string status, string detail, Color color)
        {
            Ui(delegate
            {
                ListViewItem item = null;
                foreach (ListViewItem candidate in _preflightList.Items)
                {
                    if (String.Equals(candidate.Name, key, StringComparison.Ordinal))
                    {
                        item = candidate;
                        break;
                    }
                }
                if (item == null)
                {
                    item = new ListViewItem(name);
                    item.Name = key;
                    item.SubItems.Add(status);
                    item.SubItems.Add(detail);
                    _preflightList.Items.Add(item);
                }
                else
                {
                    item.Text = name;
                    while (item.SubItems.Count < 3)
                    {
                        item.SubItems.Add("");
                    }
                    item.SubItems[1].Text = status;
                    item.SubItems[2].Text = detail;
                }
                item.ForeColor = color;
            });
        }

        private void StartInstall()
        {
            if (_installing)
            {
                return;
            }
            _installing = true;
            _vbCableMissing = false;
            SetControlsEnabled(false);
            _logText.Clear();
            SetProgress(0, "开始安装");

            string installDir = _installDirText.Text.Trim();
            bool installDeps = _installDepsCheck.Checked;
            bool registerCamera = _registerCameraCheck.Checked && _registerCameraCheck.Enabled;
            bool launchAfterInstall = _launchAfterInstallCheck.Checked;

            ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    RunInstall(installDir, installDeps, registerCamera, launchAfterInstall);
                    Ui(delegate
                    {
                        _installButton.Text = "重新安装";
                        SetControlsEnabled(true);
                    });
                }
                catch (Exception exc)
                {
                    AppendLog("安装失败：");
                    AppendLog(exc.ToString());
                    SetProgress(100, "安装失败");
                    Ui(delegate
                    {
                        MessageBox.Show(this, exc.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                        SetControlsEnabled(true);
                    });
                }
                finally
                {
                    _installing = false;
                }
            });
        }

        private void RunInstall(string installDir, bool installDeps, bool registerCamera, bool launchAfterInstall)
        {
            if (String.IsNullOrWhiteSpace(installDir))
            {
                throw new InvalidOperationException("安装位置不能为空。");
            }

            string tempRoot = Path.Combine(Path.GetTempPath(), "SensorBridgeMeetingInstaller-" + Guid.NewGuid().ToString("N"));
            string tempZip = Path.Combine(tempRoot, "payload.zip");
            string extractDir = Path.Combine(tempRoot, "payload");

            try
            {
                SetProgress(8, "读取内置安装包");
                Directory.CreateDirectory(tempRoot);
                ExtractPayloadZip(tempZip);

                SetProgress(18, "解压安装文件");
                Directory.CreateDirectory(extractDir);
                ZipFile.ExtractToDirectory(tempZip, extractDir);

                string installerScript = Path.Combine(extractDir, "Install-SensorBridgeMeeting.ps1");
                if (!File.Exists(installerScript))
                {
                    throw new FileNotFoundException("安装脚本不存在。", installerScript);
                }

                SetProgress(28, "执行安装脚本");
                int exitCode = RunPowerShellInstaller(installerScript, installDir, installDeps, registerCamera);
                if (exitCode != 0)
                {
                    throw new InvalidOperationException("安装脚本返回错误代码 " + exitCode + "。");
                }

                string appExe = Path.Combine(installDir, "meeting-suite\\windows-app\\SensorBridge.Meeting.App\\bin\\Release\\SensorBridge.Meeting.App.exe");
                if (!File.Exists(appExe))
                {
                    throw new FileNotFoundException("安装后没有找到主程序。", appExe);
                }

                SetProgress(94, "清理临时文件");
                TryDeleteDirectory(tempRoot);

                SetProgress(100, "安装完成");
                AppendLog("安装完成。");
                AppendLog("安装目录：" + installDir);
                AppendLog("桌面快捷方式：SensorBridge Meeting Suite");

                if (launchAfterInstall)
                {
                    SetProgress(100, "正在启动应用");
                    LaunchInstalledApp(appExe, installDir);
                }

                Ui(delegate
                {
                    string message = _vbCableMissing
                        ? "SensorBridge Meeting Suite 已安装，但未检测到 VB-CABLE。请复制窗口底部的网址，下载并安装/卸载 VB-CABLE。"
                        : "SensorBridge Meeting Suite 安装完成。";
                    MessageBox.Show(this, message, Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
                });
            }
            catch
            {
                TryDeleteDirectory(tempRoot);
                throw;
            }
        }

        private void ExtractPayloadZip(string destination)
        {
            Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadResourceName);
            if (resource == null)
            {
                throw new InvalidOperationException("安装器缺少内置安装包资源：" + PayloadResourceName);
            }
            using (resource)
            using (FileStream file = File.Open(destination, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                resource.CopyTo(file);
            }
            AppendLog("内置安装包已释放到临时目录。");
        }

        private int RunPowerShellInstaller(string scriptPath, string installDir, bool installDeps, bool registerCamera)
        {
            string args = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(scriptPath) +
                " -InstallDir " + Quote(installDir) +
                " -Progress";
            if (installDeps)
            {
                args += " -InstallPythonDeps";
            }
            if (registerCamera)
            {
                args += " -RegisterCamera";
            }

            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "powershell.exe";
            info.Arguments = args;
            info.WorkingDirectory = Path.GetDirectoryName(scriptPath);
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;

            using (Process process = new Process())
            {
                process.StartInfo = info;
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
                {
                    if (e.Data != null)
                    {
                        HandleInstallerOutput(e.Data);
                    }
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
                {
                    if (e.Data != null)
                    {
                        AppendLog("ERR " + e.Data);
                    }
                };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                return process.ExitCode;
            }
        }

        private void HandleInstallerOutput(string line)
        {
            const string prefix = "SENSORBRIDGE_PROGRESS|";
            const string vbCablePrefix = "SENSORBRIDGE_VBCABLE_MISSING|";
            if (line.StartsWith(vbCablePrefix, StringComparison.Ordinal))
            {
                string url = line.Substring(vbCablePrefix.Length).Trim();
                ShowVbCableHelp(String.IsNullOrWhiteSpace(url) ? VbCableUrl : url);
                AppendLog("未检测到 VB-CABLE。请从官方页面下载、安装或卸载：" + (String.IsNullOrWhiteSpace(url) ? VbCableUrl : url));
                return;
            }
            if (line.StartsWith(prefix, StringComparison.Ordinal))
            {
                string[] parts = line.Split(new char[] { '|' }, 3);
                int percent;
                if (parts.Length == 3 && Int32.TryParse(parts[1], out percent))
                {
                    SetProgress(percent, parts[2]);
                    AppendLog(parts[2]);
                    return;
                }
            }
            AppendLog(line);
        }

        private void ShowVbCableHelp(string url)
        {
            _vbCableMissing = true;
            Ui(delegate
            {
                _vbCableHelpLabel.Text = "未检测到 VB-CABLE。请从官方页面下载、安装或卸载；下面的网址可以直接复制：";
                _vbCableHelpLabel.ForeColor = Color.FromArgb(151, 75, 0);
                _vbCableUrlText.Text = url;
                _vbCableUrlText.Visible = true;
                _copyVbCableUrlButton.Visible = true;
                _vbCableUrlText.SelectAll();
            });
        }

        private void CopyVbCableUrl()
        {
            try
            {
                Clipboard.SetText(_vbCableUrlText.Text);
                AppendLog("VB-CABLE 官方网址已复制。");
            }
            catch (Exception exc)
            {
                AppendLog("复制网址失败：" + exc.Message);
            }
        }

        private void LaunchInstalledApp(string appExe, string installDir)
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = appExe;
            info.Arguments = "--project-root " + Quote(installDir);
            info.WorkingDirectory = installDir;
            info.UseShellExecute = true;
            Process.Start(info);
        }

        private void SetControlsEnabled(bool enabled)
        {
            Ui(delegate
            {
                _installDirText.Enabled = enabled;
                _browseButton.Enabled = enabled;
                _installDepsCheck.Enabled = enabled;
                _registerCameraCheck.Enabled = enabled && (IsAdministrator() || _registerCameraCheck.Checked);
                if (!IsAdministrator())
                {
                    _registerCameraCheck.Enabled = false;
                }
                _launchAfterInstallCheck.Enabled = enabled;
                _preflightButton.Enabled = enabled;
                _installButton.Enabled = enabled;
                _closeButton.Enabled = enabled;
            });
        }

        private void SetProgress(int percent, string status)
        {
            Ui(delegate
            {
                _progress.Value = Math.Max(_progress.Minimum, Math.Min(_progress.Maximum, percent));
                _statusLabel.Text = status;
            });
        }

        private void AppendLog(string text)
        {
            Ui(delegate
            {
                _logText.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + text + Environment.NewLine);
            });
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

        private static bool IsAdministrator()
        {
            WindowsIdentity identity = WindowsIdentity.GetCurrent();
            WindowsPrincipal principal = new WindowsPrincipal(identity);
            return principal.IsInRole(WindowsBuiltInRole.Administrator);
        }

        private static ProcessResult RunProcessCapture(string fileName, string arguments, int timeoutMilliseconds)
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = fileName;
            info.Arguments = arguments;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;

            try
            {
                using (Process process = Process.Start(info))
                {
                    if (process == null)
                    {
                        return new ProcessResult { ExitCode = -1, Output = "", Error = "Process did not start." };
                    }
                    if (!process.WaitForExit(timeoutMilliseconds))
                    {
                        try { process.Kill(); }
                        catch { }
                        return new ProcessResult { ExitCode = -1, Output = "", Error = "Timed out." };
                    }
                    return new ProcessResult
                    {
                        ExitCode = process.ExitCode,
                        Output = process.StandardOutput.ReadToEnd(),
                        Error = process.StandardError.ReadToEnd()
                    };
                }
            }
            catch (Exception exc)
            {
                return new ProcessResult { ExitCode = -1, Output = "", Error = exc.Message };
            }
        }

        private static string FirstNonEmptyLine(string text)
        {
            foreach (string line in SplitLines(text))
            {
                if (!String.IsNullOrWhiteSpace(line))
                {
                    return line.Trim();
                }
            }
            return "";
        }

        private static string[] SplitLines(string text)
        {
            return (text ?? "").Split(new string[] { "\r\n", "\n", "\r" }, StringSplitOptions.RemoveEmptyEntries);
        }

        private static int CompareVersion(string current, string minimum)
        {
            int[] left = ParseVersionParts(current);
            int[] right = ParseVersionParts(minimum);
            int length = Math.Max(left.Length, right.Length);
            for (int i = 0; i < length; i++)
            {
                int a = i < left.Length ? left[i] : 0;
                int b = i < right.Length ? right[i] : 0;
                if (a != b)
                {
                    return a.CompareTo(b);
                }
            }
            return 0;
        }

        private static int[] ParseVersionParts(string value)
        {
            string[] rawParts = (value ?? "").Split('.');
            List<int> parts = new List<int>();
            foreach (string raw in rawParts)
            {
                string digits = "";
                foreach (char ch in raw)
                {
                    if (Char.IsDigit(ch))
                    {
                        digits += ch;
                    }
                    else
                    {
                        break;
                    }
                }
                int parsed;
                if (Int32.TryParse(digits, out parsed))
                {
                    parts.Add(parsed);
                }
                else
                {
                    parts.Add(0);
                }
            }
            while (parts.Count < 3)
            {
                parts.Add(0);
            }
            return parts.ToArray();
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? "").Replace("\"", "\\\"") + "\"";
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                if (Directory.Exists(path))
                {
                    Directory.Delete(path, true);
                }
            }
            catch
            {
            }
        }

        private sealed class PythonInfo
        {
            public bool Found;
            public string Command;
            public string Prefix;
            public string Version;
        }

        private sealed class ProcessResult
        {
            public int ExitCode;
            public string Output;
            public string Error;
        }
    }
}
