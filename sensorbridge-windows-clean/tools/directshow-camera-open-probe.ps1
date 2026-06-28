param(
  [string]$NameNeedle = 'SensorBridge',
  [int]$TimeoutMilliseconds = 5000
)

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
using System.Threading;

public sealed class DirectShowOpenProbeResult
{
    public bool ok;
    public string error;
    public string selectedName;
    public string hresult;
    public int width;
    public int height;
    public int bitCount;
    public int bufferBytes;
}

public static class DirectShowOpenProbe
{
    static readonly Guid VideoInputDeviceCategory = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
    static readonly Guid MediaTypeVideo = new Guid("73646976-0000-0010-8000-00AA00389B71");
    static readonly Guid MediaSubTypeRgb24 = new Guid("E436EB7D-524F-11CE-9F53-0020AF0BA770");
    static readonly Guid FormatVideoInfo = new Guid("05589F80-C356-11CE-BF01-00AA0055595A");

    public static DirectShowOpenProbeResult Run(string nameNeedle, int timeoutMilliseconds)
    {
        object graphObject = null;
        object captureBuilderObject = null;
        object sourceObject = null;
        object grabberObject = null;
        object nullRendererObject = null;
        string selectedName = null;
        try
        {
            sourceObject = FindVideoSource(nameNeedle, out selectedName);
            if (sourceObject == null)
            {
                return Fail("camera_not_found", "SensorBridge DirectShow camera was not found.");
            }

            graphObject = new FilterGraph();
            captureBuilderObject = new CaptureGraphBuilder2();
            grabberObject = new SampleGrabber();
            nullRendererObject = new NullRenderer();

            var graphBuilder = (IGraphBuilder)graphObject;
            var filterGraph = (IFilterGraph)graphObject;
            var captureBuilder = (ICaptureGraphBuilder2)captureBuilderObject;
            var sourceFilter = (IBaseFilter)sourceObject;
            var grabberFilter = (IBaseFilter)grabberObject;
            var nullRenderer = (IBaseFilter)nullRendererObject;
            var sampleGrabber = (ISampleGrabber)grabberObject;

            Check(filterGraph.AddFilter(sourceFilter, "SensorBridge Camera"), "AddFilter(source)");
            Check(filterGraph.AddFilter(grabberFilter, "SensorBridge Sample Grabber"), "AddFilter(grabber)");
            Check(filterGraph.AddFilter(nullRenderer, "SensorBridge Null Renderer"), "AddFilter(null)");

            var requested = new AMMediaType();
            requested.majorType = MediaTypeVideo;
            requested.subType = MediaSubTypeRgb24;
            requested.formatType = FormatVideoInfo;
            Check(sampleGrabber.SetMediaType(requested), "SetMediaType");
            Check(sampleGrabber.SetBufferSamples(true), "SetBufferSamples");
            Check(sampleGrabber.SetOneShot(false), "SetOneShot");

            Check(captureBuilder.SetFiltergraph(graphBuilder), "SetFiltergraph");
            Check(captureBuilder.RenderStream(IntPtr.Zero, IntPtr.Zero, sourceFilter, grabberFilter, nullRenderer), "RenderStream");

            var control = (IMediaControl)graphObject;
            Check(control.Run(), "Run");
            int hr = 0;
            int size = 0;
            var deadline = DateTime.UtcNow.AddMilliseconds(Math.Max(timeoutMilliseconds, 250));
            while (DateTime.UtcNow < deadline)
            {
                hr = sampleGrabber.GetCurrentBuffer(ref size, IntPtr.Zero);
                if (hr == 0 && size > 0)
                {
                    break;
                }
                Thread.Sleep(50);
            }
            control.Stop();
            if (size <= 0)
            {
                return Fail("no_frame", "DirectShow graph opened but no frame buffer arrived before timeout.", hr);
            }

            var connected = new AMMediaType();
            int mediaHr = sampleGrabber.GetConnectedMediaType(connected);
            int width = 0;
            int height = 0;
            int bitCount = 0;
            if (mediaHr == 0 && connected.formatPtr != IntPtr.Zero && connected.formatSize >= Marshal.SizeOf(typeof(VideoInfoHeader)))
            {
                var vih = (VideoInfoHeader)Marshal.PtrToStructure(connected.formatPtr, typeof(VideoInfoHeader));
                width = vih.bmiHeader.width;
                height = Math.Abs(vih.bmiHeader.height);
                bitCount = vih.bmiHeader.bitCount;
            }
            FreeMediaType(connected);

            return new DirectShowOpenProbeResult
            {
                ok = true,
                selectedName = selectedName,
                hresult = HResult(0),
                width = width,
                height = height,
                bitCount = bitCount,
                bufferBytes = size
            };
        }
        catch (COMException exc)
        {
            var result = Fail("directshow_com_error", exc.Message, exc.ErrorCode);
            result.selectedName = selectedName;
            return result;
        }
        catch (Exception exc)
        {
            var result = Fail("directshow_open_failed", exc.Message);
            result.selectedName = selectedName;
            return result;
        }
        finally
        {
            Release(nullRendererObject);
            Release(grabberObject);
            Release(sourceObject);
            Release(captureBuilderObject);
            Release(graphObject);
        }
    }

    static object FindVideoSource(string nameNeedle, out string selectedName)
    {
        selectedName = null;
        ICreateDevEnum devEnum = null;
        IEnumMoniker enumMoniker = null;
        try
        {
            devEnum = (ICreateDevEnum)new CreateDevEnum();
            Guid category = VideoInputDeviceCategory;
            int hr = devEnum.CreateClassEnumerator(ref category, out enumMoniker, 0);
            if (hr != 0 || enumMoniker == null)
            {
                return null;
            }
            var monikers = new IMoniker[1];
            while (enumMoniker.Next(1, monikers, IntPtr.Zero) == 0)
            {
                IBindCtx bindCtx = null;
                object bagObject = null;
                try
                {
                    NativeMethods.CreateBindCtx(0, out bindCtx);
                    Guid bagId = typeof(IPropertyBag).GUID;
                    monikers[0].BindToStorage(bindCtx, null, ref bagId, out bagObject);
                    var bag = (IPropertyBag)bagObject;
                    string name = ReadProperty(bag, "FriendlyName") ?? "";
                    if (name.IndexOf(nameNeedle ?? "", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        Guid filterId = typeof(IBaseFilter).GUID;
                        object filterObject;
                        monikers[0].BindToObject(bindCtx, null, ref filterId, out filterObject);
                        selectedName = name;
                        return filterObject;
                    }
                }
                finally
                {
                    Release(bagObject);
                    Release(bindCtx);
                    Release(monikers[0]);
                }
            }
            return null;
        }
        finally
        {
            Release(enumMoniker);
            Release(devEnum);
        }
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

    static void Check(int hr, string step)
    {
        if (hr < 0)
        {
            throw new COMException(step + " failed", hr);
        }
    }

    static DirectShowOpenProbeResult Fail(string code, string message, int hr)
    {
        return new DirectShowOpenProbeResult { ok = false, error = code + ": " + message, hresult = HResult(hr) };
    }

    static DirectShowOpenProbeResult Fail(string code, string message)
    {
        return new DirectShowOpenProbeResult { ok = false, error = code + ": " + message, hresult = HResult(0) };
    }

    static string HResult(int hr)
    {
        return "0x" + unchecked((uint)hr).ToString("X8");
    }

    static void FreeMediaType(AMMediaType mediaType)
    {
        if (mediaType.formatPtr != IntPtr.Zero)
        {
            Marshal.FreeCoTaskMem(mediaType.formatPtr);
            mediaType.formatPtr = IntPtr.Zero;
        }
        if (mediaType.unkPtr != IntPtr.Zero)
        {
            Marshal.Release(mediaType.unkPtr);
            mediaType.unkPtr = IntPtr.Zero;
        }
    }

    static void Release(object value)
    {
        if (value != null && Marshal.IsComObject(value))
        {
            Marshal.ReleaseComObject(value);
        }
    }
}

[ComImport]
[Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")]
public class CreateDevEnum
{
}

[ComImport]
[Guid("E436EBB3-524F-11CE-9F53-0020AF0BA770")]
public class FilterGraph
{
}

[ComImport]
[Guid("BF87B6E1-8C27-11D0-B3F0-00AA003761C5")]
public class CaptureGraphBuilder2
{
}

[ComImport]
[Guid("C1F400A0-3F08-11D3-9F0B-006008039E37")]
public class SampleGrabber
{
}

[ComImport]
[Guid("C1F400A4-3F08-11D3-9F0B-006008039E37")]
public class NullRenderer
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

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("56A86895-0AD4-11CE-B03A-0020AF0BA770")]
public interface IBaseFilter
{
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("56A8689F-0AD4-11CE-B03A-0020AF0BA770")]
public interface IFilterGraph
{
    [PreserveSig]
    int AddFilter([MarshalAs(UnmanagedType.Interface)] IBaseFilter filter, [MarshalAs(UnmanagedType.LPWStr)] string name);
    [PreserveSig]
    int RemoveFilter([MarshalAs(UnmanagedType.Interface)] IBaseFilter filter);
    [PreserveSig]
    int EnumFilters(out IntPtr enumFilters);
    [PreserveSig]
    int FindFilterByName([MarshalAs(UnmanagedType.LPWStr)] string name, out IBaseFilter filter);
    [PreserveSig]
    int ConnectDirect(IntPtr pinOut, IntPtr pinIn, IntPtr mediaType);
    [PreserveSig]
    int Reconnect(IntPtr pin);
    [PreserveSig]
    int Disconnect(IntPtr pin);
    [PreserveSig]
    int SetDefaultSyncSource();
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("56A868A9-0AD4-11CE-B03A-0020AF0BA770")]
public interface IGraphBuilder
{
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("93E5A4E0-2D50-11D2-ABFA-00A0C9C6E38D")]
public interface ICaptureGraphBuilder2
{
    [PreserveSig]
    int SetFiltergraph([MarshalAs(UnmanagedType.Interface)] IGraphBuilder graphBuilder);
    [PreserveSig]
    int GetFiltergraph(out IGraphBuilder graphBuilder);
    [PreserveSig]
    int SetOutputFileName(IntPtr type, [MarshalAs(UnmanagedType.LPWStr)] string fileName, out IBaseFilter mux, out IntPtr sink);
    [PreserveSig]
    int FindInterface(IntPtr category, IntPtr type, [MarshalAs(UnmanagedType.Interface)] IBaseFilter filter, ref Guid iid, out IntPtr result);
    [PreserveSig]
    int RenderStream(IntPtr category, IntPtr type, [MarshalAs(UnmanagedType.IUnknown)] object source, [MarshalAs(UnmanagedType.Interface)] IBaseFilter compressor, [MarshalAs(UnmanagedType.Interface)] IBaseFilter renderer);
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsDual)]
[Guid("56A868B1-0AD4-11CE-B03A-0020AF0BA770")]
public interface IMediaControl
{
    [PreserveSig]
    int Run();
    [PreserveSig]
    int Pause();
    [PreserveSig]
    int Stop();
    [PreserveSig]
    int GetState(int timeoutMs, out int filterState);
    [PreserveSig]
    int RenderFile([MarshalAs(UnmanagedType.BStr)] string fileName);
    [PreserveSig]
    int AddSourceFilter([MarshalAs(UnmanagedType.BStr)] string fileName, out object filterInfo);
    [PreserveSig]
    int get_FilterCollection(out object collection);
    [PreserveSig]
    int get_RegFilterCollection(out object collection);
    [PreserveSig]
    int StopWhenReady();
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("6B652FFF-11FE-4FCE-92AD-0266B5D7C78F")]
public interface ISampleGrabber
{
    [PreserveSig]
    int SetOneShot([MarshalAs(UnmanagedType.Bool)] bool oneShot);
    [PreserveSig]
    int SetMediaType([In] AMMediaType mediaType);
    [PreserveSig]
    int GetConnectedMediaType([Out] AMMediaType mediaType);
    [PreserveSig]
    int SetBufferSamples([MarshalAs(UnmanagedType.Bool)] bool bufferThem);
    [PreserveSig]
    int GetCurrentBuffer(ref int bufferSize, IntPtr buffer);
    [PreserveSig]
    int GetCurrentSample(out IntPtr sample);
    [PreserveSig]
    int SetCallback(IntPtr callback, int whichMethodToCallback);
}

[StructLayout(LayoutKind.Sequential)]
public class AMMediaType
{
    public Guid majorType;
    public Guid subType;
    [MarshalAs(UnmanagedType.Bool)]
    public bool fixedSizeSamples;
    [MarshalAs(UnmanagedType.Bool)]
    public bool temporalCompression;
    public int sampleSize;
    public Guid formatType;
    public IntPtr unkPtr;
    public int formatSize;
    public IntPtr formatPtr;
}

[StructLayout(LayoutKind.Sequential)]
public struct DsRect
{
    public int left;
    public int top;
    public int right;
    public int bottom;
}

[StructLayout(LayoutKind.Sequential)]
public struct BitmapInfoHeader
{
    public int size;
    public int width;
    public int height;
    public short planes;
    public short bitCount;
    public int compression;
    public int imageSize;
    public int xPelsPerMeter;
    public int yPelsPerMeter;
    public int clrUsed;
    public int clrImportant;
}

[StructLayout(LayoutKind.Sequential)]
public struct VideoInfoHeader
{
    public DsRect source;
    public DsRect target;
    public int bitRate;
    public int bitErrorRate;
    public long avgTimePerFrame;
    public BitmapInfoHeader bmiHeader;
}

public static class NativeMethods
{
    [DllImport("ole32.dll")]
    public static extern int CreateBindCtx(int reserved, out IBindCtx bindCtx);
}
'@

Add-Type -TypeDefinition $source

$probe = [DirectShowOpenProbe]::Run($NameNeedle, $TimeoutMilliseconds)
[ordered]@{
  ok = [bool]$probe.ok
  command = 'directshow_camera_open_probe'
  changes_system = $false
  method = 'DirectShow.FilterGraph.SampleGrabber'
  name_needle = $NameNeedle
  timeout_ms = $TimeoutMilliseconds
  selected = $probe.selectedName
  hresult = $probe.hresult
  width = $probe.width
  height = $probe.height
  bit_count = $probe.bitCount
  buffer_bytes = $probe.bufferBytes
  error = $probe.error
} | ConvertTo-Json -Depth 5
