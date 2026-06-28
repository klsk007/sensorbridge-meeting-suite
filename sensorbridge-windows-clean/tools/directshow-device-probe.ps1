param()

$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public sealed class DirectShowDeviceInfo
{
    public string name;
    public string devicePath;
    public string kind;
}

public sealed class DirectShowProbeResult
{
    public int hresult;
    public DirectShowDeviceInfo[] devices;
}

public static class DirectShowVideoInputProbe
{
    static readonly Guid VideoInputDeviceCategory = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");

    public static DirectShowProbeResult Enumerate()
    {
        var result = new List<DirectShowDeviceInfo>();
        ICreateDevEnum devEnum = (ICreateDevEnum)new CreateDevEnum();
        Guid category = VideoInputDeviceCategory;
        IEnumMoniker enumMoniker;
        int hr = devEnum.CreateClassEnumerator(ref category, out enumMoniker, 0);
        if (hr != 0 || enumMoniker == null)
        {
            Marshal.ReleaseComObject(devEnum);
            return new DirectShowProbeResult { hresult = hr, devices = result.ToArray() };
        }

        var monikers = new IMoniker[1];
        while (enumMoniker.Next(1, monikers, IntPtr.Zero) == 0)
        {
            IBindCtx bindCtx = null;
            try
            {
                NativeMethods.CreateBindCtx(0, out bindCtx);
                Guid bagId = typeof(IPropertyBag).GUID;
                object bagObject;
                monikers[0].BindToStorage(bindCtx, null, ref bagId, out bagObject);
                var bag = (IPropertyBag)bagObject;
                result.Add(new DirectShowDeviceInfo {
                    name = ReadProperty(bag, "FriendlyName"),
                    devicePath = ReadProperty(bag, "DevicePath"),
                    kind = "DirectShow.VideoInputDevice"
                });
            }
            finally
            {
                if (bindCtx != null) Marshal.ReleaseComObject(bindCtx);
                if (monikers[0] != null) Marshal.ReleaseComObject(monikers[0]);
            }
        }
        Marshal.ReleaseComObject(enumMoniker);
        Marshal.ReleaseComObject(devEnum);
        return new DirectShowProbeResult { hresult = hr, devices = result.ToArray() };
    }

    static string ReadProperty(IPropertyBag bag, string name)
    {
        try
        {
            object value;
            bag.Read(name, out value, IntPtr.Zero);
            return value == null ? null : value.ToString();
        }
        catch
        {
            return null;
        }
    }
}

[ComImport]
[Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")]
public class CreateDevEnum
{
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("29840822-5B84-11D0-BD3B-00A0C911CE86")]
public interface ICreateDevEnum
{
    [PreserveSig]
    int CreateClassEnumerator([In] ref Guid clsidDeviceClass, [MarshalAs(UnmanagedType.Interface)] out IEnumMoniker enumMoniker, int flags);
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("55272A00-42CB-11CE-8135-00AA004BB851")]
public interface IPropertyBag
{
    void Read([MarshalAs(UnmanagedType.LPWStr)] string propertyName, [MarshalAs(UnmanagedType.Struct)] out object value, IntPtr errorLog);
    void Write([MarshalAs(UnmanagedType.LPWStr)] string propertyName, [MarshalAs(UnmanagedType.Struct)] ref object value);
}

public static class NativeMethods
{
    [DllImport("ole32.dll")]
    public static extern int CreateBindCtx(int reserved, out IBindCtx bindCtx);
}
'@

Add-Type -TypeDefinition $source

$comResult = [DirectShowVideoInputProbe]::Enumerate()
$devices = $comResult.devices | ForEach-Object {
  [ordered]@{
    name = $_.name
    devicePath = $_.devicePath
    kind = $_.kind
  }
}

$registryDevices = @()
$categoryPaths = @(
  'HKLM:\SOFTWARE\Classes\CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance',
  'HKCR:\CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance'
)
foreach ($categoryPath in $categoryPaths) {
  if (-not (Test-Path $categoryPath)) {
    continue
  }
  $registryDevices += Get-ChildItem $categoryPath -ErrorAction SilentlyContinue | ForEach-Object {
    $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    [ordered]@{
      name = [string]($props.FriendlyName)
      clsid = [string]($props.CLSID)
      kind = 'DirectShow.VideoInputDevice.Registry'
      registryPath = $_.Name
    }
  }
}

[ordered]@{
  ok = $true
  command = 'directshow_device_probe'
  changes_system = $false
  method = 'DirectShow.ICreateDevEnum.CLSID_VideoInputDeviceCategory'
  hresult = ('0x{0:X8}' -f ([uint32]$comResult.hresult))
  videoInput = @($devices)
  registryVideoInput = @($registryDevices | Sort-Object registryPath -Unique)
} | ConvertTo-Json -Depth 5
