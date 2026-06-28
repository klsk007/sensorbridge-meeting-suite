using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text.Json;

static IReadOnlyList<object> EnumerateVideoInputDevices()
{
    var category = DirectShowGuids.VideoInputDeviceCategory;
    var devEnum = (ICreateDevEnum)new CreateDevEnum();
    var hr = devEnum.CreateClassEnumerator(ref category, out var enumMoniker, 0);
    if (hr != 0 || enumMoniker is null)
    {
        return Array.Empty<object>();
    }

    var devices = new List<object>();
    var monikers = new IMoniker[1];
    while (enumMoniker.Next(1, monikers, IntPtr.Zero) == 0)
    {
        var moniker = monikers[0];
        var bindCtx = (IBindCtx?)null;
        try
        {
            CreateBindCtx(0, out bindCtx);
            var bagId = typeof(IPropertyBag).GUID;
            moniker.BindToStorage(bindCtx, null, ref bagId, out var bagObject);
            var bag = (IPropertyBag)bagObject;

            var friendlyName = ReadProperty(bag, "FriendlyName");
            var devicePath = ReadProperty(bag, "DevicePath");
            devices.Add(new
            {
                name = friendlyName,
                devicePath,
                kind = "DirectShow.VideoInputDevice"
            });
        }
        finally
        {
            if (bindCtx is not null)
            {
                Marshal.ReleaseComObject(bindCtx);
            }
            Marshal.ReleaseComObject(moniker);
        }
    }
    Marshal.ReleaseComObject(enumMoniker);
    Marshal.ReleaseComObject(devEnum);
    return devices;
}

static string? ReadProperty(IPropertyBag bag, string name)
{
    try
    {
        bag.Read(name, out var value, IntPtr.Zero);
        return value?.ToString();
    }
    catch (COMException)
    {
        return null;
    }
}

var videoInput = EnumerateVideoInputDevices();
var payload = new
{
    ok = true,
    command = "directshow_device_probe",
    method = "DirectShow.ICreateDevEnum.CLSID_VideoInputDeviceCategory",
    videoInput
};

Console.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));

internal static class DirectShowGuids
{
    public static Guid VideoInputDeviceCategory = new("860BB310-5D01-11D0-BD3B-00A0C911CE86");
}

[ComImport]
[Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")]
internal sealed class CreateDevEnum
{
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("29840822-5B84-11D0-BD3B-00A0C911CE86")]
internal interface ICreateDevEnum
{
    [PreserveSig]
    int CreateClassEnumerator(ref Guid clsidDeviceClass, out IEnumMoniker? enumMoniker, int flags);
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("55272A00-42CB-11CE-8135-00AA004BB851")]
internal interface IPropertyBag
{
    void Read([MarshalAs(UnmanagedType.LPWStr)] string propertyName, [MarshalAs(UnmanagedType.Struct)] out object value, IntPtr errorLog);
    void Write([MarshalAs(UnmanagedType.LPWStr)] string propertyName, [MarshalAs(UnmanagedType.Struct)] ref object value);
}

internal static partial class NativeMethods
{
    [DllImport("ole32.dll")]
    public static extern int CreateBindCtx(int reserved, out IBindCtx bindCtx);
}
