using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;

namespace SensorBridge.Tools
{
    internal static class Program
    {
        private const int DIF_REGISTERDEVICE = 0x00000019;
        private const int DICD_GENERATE_ID = 0x00000001;
        private const int SPDRP_HARDWAREID = 0x00000001;
        private const int INSTALLFLAG_FORCE = 0x00000001;

        [StructLayout(LayoutKind.Sequential)]
        private struct SP_DEVINFO_DATA
        {
            public int cbSize;
            public Guid ClassGuid;
            public int DevInst;
            public IntPtr Reserved;
        }

        [DllImport("setupapi.dll", SetLastError = true)]
        private static extern IntPtr SetupDiCreateDeviceInfoList(ref Guid ClassGuid, IntPtr hwndParent);

        [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool SetupDiCreateDeviceInfo(
            IntPtr DeviceInfoSet,
            string DeviceName,
            ref Guid ClassGuid,
            string DeviceDescription,
            IntPtr hwndParent,
            int CreationFlags,
            out SP_DEVINFO_DATA DeviceInfoData);

        [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool SetupDiSetDeviceRegistryProperty(
            IntPtr DeviceInfoSet,
            ref SP_DEVINFO_DATA DeviceInfoData,
            int Property,
            byte[] PropertyBuffer,
            int PropertyBufferSize);

        [DllImport("setupapi.dll", SetLastError = true)]
        private static extern bool SetupDiCallClassInstaller(
            int InstallFunction,
            IntPtr DeviceInfoSet,
            ref SP_DEVINFO_DATA DeviceInfoData);

        [DllImport("setupapi.dll", SetLastError = true)]
        private static extern bool SetupDiDestroyDeviceInfoList(IntPtr DeviceInfoSet);

        [DllImport("newdev.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool UpdateDriverForPlugAndPlayDevices(
            IntPtr hwndParent,
            string HardwareId,
            string FullInfPath,
            int InstallFlags,
            out bool bRebootRequired);

        private static int Main(string[] args)
        {
            try
            {
                if (args.Length == 0 || HasArg(args, "--help") || HasArg(args, "-h"))
                {
                    PrintUsage();
                    return 0;
                }

                string command = args[0].ToLowerInvariant();
                string infPath = RequiredValue(args, "--inf");
                string hardwareId = RequiredValue(args, "--hardware-id");
                string fullInfPath = Path.GetFullPath(infPath);
                if (!File.Exists(fullInfPath))
                {
                    throw new FileNotFoundException("INF file was not found.", fullInfPath);
                }

                InfMetadata metadata = InfMetadata.Load(fullInfPath);
                if (command == "inspect")
                {
                    WriteJson(true, "inspect", fullInfPath, hardwareId, metadata, false, null);
                    return 0;
                }
                if (command != "install")
                {
                    throw new ArgumentException("Unknown command: " + command);
                }

                InstallRootDevice(fullInfPath, hardwareId, metadata);
                bool rebootRequired;
                bool updated = UpdateDriverForPlugAndPlayDevices(
                    IntPtr.Zero,
                    hardwareId,
                    fullInfPath,
                    INSTALLFLAG_FORCE,
                    out rebootRequired);
                if (!updated)
                {
                    ThrowLastWin32("UpdateDriverForPlugAndPlayDevices failed");
                }

                WriteJson(true, "install", fullInfPath, hardwareId, metadata, rebootRequired, null);
                return 0;
            }
            catch (Exception ex)
            {
                WriteJson(false, args.Length > 0 ? args[0] : "unknown", null, null, null, false, ex);
                return 1;
            }
        }

        private static void InstallRootDevice(string infPath, string hardwareId, InfMetadata metadata)
        {
            Guid classGuid = metadata.ClassGuid;
            IntPtr deviceInfoSet = SetupDiCreateDeviceInfoList(ref classGuid, IntPtr.Zero);
            if (deviceInfoSet == IntPtr.Zero || deviceInfoSet.ToInt64() == -1)
            {
                ThrowLastWin32("SetupDiCreateDeviceInfoList failed");
            }

            try
            {
                SP_DEVINFO_DATA deviceInfoData = new SP_DEVINFO_DATA();
                deviceInfoData.cbSize = Marshal.SizeOf(typeof(SP_DEVINFO_DATA));
                bool created = SetupDiCreateDeviceInfo(
                    deviceInfoSet,
                    RootDeviceNameFromHardwareId(hardwareId),
                    ref classGuid,
                    metadata.DeviceDescription,
                    IntPtr.Zero,
                    DICD_GENERATE_ID,
                    out deviceInfoData);
                if (!created)
                {
                    ThrowLastWin32("SetupDiCreateDeviceInfo failed");
                }

                byte[] hardwareIds = Encoding.Unicode.GetBytes(hardwareId + "\0\0");
                bool propertySet = SetupDiSetDeviceRegistryProperty(
                    deviceInfoSet,
                    ref deviceInfoData,
                    SPDRP_HARDWAREID,
                    hardwareIds,
                    hardwareIds.Length);
                if (!propertySet)
                {
                    ThrowLastWin32("SetupDiSetDeviceRegistryProperty(SPDRP_HARDWAREID) failed");
                }

                bool registered = SetupDiCallClassInstaller(DIF_REGISTERDEVICE, deviceInfoSet, ref deviceInfoData);
                if (!registered)
                {
                    ThrowLastWin32("SetupDiCallClassInstaller(DIF_REGISTERDEVICE) failed");
                }
            }
            finally
            {
                SetupDiDestroyDeviceInfoList(deviceInfoSet);
            }
        }

        private static bool HasArg(string[] args, string name)
        {
            for (int i = 0; i < args.Length; i++)
            {
                if (String.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        private static string RequiredValue(string[] args, string name)
        {
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (String.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
                {
                    return args[i + 1];
                }
            }
            throw new ArgumentException("Missing required argument: " + name);
        }

        private static string RootDeviceNameFromHardwareId(string hardwareId)
        {
            const string rootPrefix = "Root\\";
            if (hardwareId.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase))
            {
                return hardwareId.Substring(rootPrefix.Length);
            }
            return hardwareId;
        }

        private static void ThrowLastWin32(string message)
        {
            int error = Marshal.GetLastWin32Error();
            throw new InvalidOperationException(message + " (Win32 error " + error + ")");
        }

        private static void PrintUsage()
        {
            Console.WriteLine("SensorBridge RootDeviceInstaller");
            Console.WriteLine("  inspect --inf <path.inf> --hardware-id <Root\\...>");
            Console.WriteLine("  install --inf <path.inf> --hardware-id <Root\\...>");
        }

        private static void WriteJson(
            bool ok,
            string command,
            string infPath,
            string hardwareId,
            InfMetadata metadata,
            bool rebootRequired,
            Exception error)
        {
            StringBuilder builder = new StringBuilder();
            builder.Append("{");
            AppendJson(builder, "ok", ok, false);
            AppendJson(builder, "command", command, true);
            if (infPath != null) AppendJson(builder, "inf", infPath, true);
            if (hardwareId != null) AppendJson(builder, "hardware_id", hardwareId, true);
            if (metadata != null)
            {
                AppendJson(builder, "class_name", metadata.ClassName, true);
                AppendJson(builder, "class_guid", metadata.ClassGuid.ToString("B"), true);
                AppendJson(builder, "device_description", metadata.DeviceDescription, true);
            }
            AppendJson(builder, "reboot_required", rebootRequired, true);
            if (error != null)
            {
                AppendJson(builder, "error", error.Message, true);
            }
            builder.Append("}");
            Console.WriteLine(builder.ToString());
        }

        private static void AppendJson(StringBuilder builder, string name, string value, bool comma)
        {
            if (comma) builder.Append(",");
            builder.Append("\"").Append(Escape(name)).Append("\":");
            builder.Append("\"").Append(Escape(value ?? "")).Append("\"");
        }

        private static void AppendJson(StringBuilder builder, string name, bool value, bool comma)
        {
            if (comma) builder.Append(",");
            builder.Append("\"").Append(Escape(name)).Append("\":");
            builder.Append(value ? "true" : "false");
        }

        private static string Escape(string value)
        {
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private sealed class InfMetadata
        {
            public string ClassName;
            public Guid ClassGuid;
            public string DeviceDescription;

            public static InfMetadata Load(string infPath)
            {
                string text = File.ReadAllText(infPath);
                string className = MatchValue(text, @"(?im)^\s*Class\s*=\s*([^\r\n;]+)");
                string classGuidValue = MatchValue(text, @"(?im)^\s*ClassGuid\s*=\s*([^\r\n;]+)");
                if (String.IsNullOrWhiteSpace(className))
                {
                    throw new InvalidDataException("INF Class value was not found.");
                }
                if (String.IsNullOrWhiteSpace(classGuidValue))
                {
                    throw new InvalidDataException("INF ClassGuid value was not found.");
                }

                string description = MatchValue(text, @"(?im)^\s*SYSVAD_SA\.DeviceDesc\s*=\s*""?([^""\r\n]+)");
                if (String.IsNullOrWhiteSpace(description))
                {
                    description = className.Trim();
                }

                return new InfMetadata
                {
                    ClassName = className.Trim().Trim('"'),
                    ClassGuid = new Guid(classGuidValue.Trim().Trim('"')),
                    DeviceDescription = description.Trim().Trim('"')
                };
            }

            private static string MatchValue(string text, string pattern)
            {
                Match match = Regex.Match(text, pattern);
                return match.Success ? match.Groups[1].Value.Trim() : "";
            }
        }
    }
}
