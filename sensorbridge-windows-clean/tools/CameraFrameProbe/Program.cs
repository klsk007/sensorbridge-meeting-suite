using System.Text.Json;
using Windows.Devices.Enumeration;
using Windows.Graphics.Imaging;
using Windows.Media.Capture;
using Windows.Media.MediaProperties;
using Windows.Storage.Streams;

static string? ReadOption(string[] args, string name)
{
    for (var i = 0; i < args.Length - 1; i++)
    {
        if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
        {
            return args[i + 1];
        }
    }

    return null;
}

static bool HasFlag(string[] args, string name)
{
    return args.Any(arg => string.Equals(arg, name, StringComparison.OrdinalIgnoreCase));
}

static async Task<int> MainAsync(string[] args)
{
    var nameContains = ReadOption(args, "--name-contains") ?? "SensorBridge,VCamSample";
    var output = ReadOption(args, "--output");
    var listOnly = HasFlag(args, "--list");

    var devices = await DeviceInformation.FindAllAsync(DeviceClass.VideoCapture);
    var deviceSummaries = devices
        .Select(device => new
        {
            id = device.Id,
            name = device.Name,
            isEnabled = device.IsEnabled,
            kind = device.Kind.ToString()
        })
        .ToArray();

    var nameNeedles = nameContains
        .Split(new[] { ',', ';', '|' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    var selected = devices.FirstOrDefault(device =>
        nameNeedles.Any(needle => device.Name.Contains(needle, StringComparison.OrdinalIgnoreCase)));

    if (listOnly || selected is null)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = selected is not null,
            command = "camera-frame-probe",
            mode = "list",
            name_contains = nameContains,
            selected = selected is null ? null : new { id = selected.Id, name = selected.Name },
            video_capture = deviceSummaries,
            error = selected is null ? "No matching video capture device was found." : null
        }, new JsonSerializerOptions { WriteIndented = true }));
        return selected is null ? 2 : 0;
    }

    try
    {
        using var capture = new MediaCapture();
        await capture.InitializeAsync(new MediaCaptureInitializationSettings
        {
            VideoDeviceId = selected.Id,
            StreamingCaptureMode = StreamingCaptureMode.Video,
            SharingMode = MediaCaptureSharingMode.SharedReadOnly,
            MemoryPreference = MediaCaptureMemoryPreference.Cpu
        });

        using var stream = new InMemoryRandomAccessStream();
        await capture.CapturePhotoToStreamAsync(ImageEncodingProperties.CreateBmp(), stream);

        stream.Seek(0);
        var decoder = await BitmapDecoder.CreateAsync(stream);

        stream.Seek(0);
        var reader = new DataReader(stream.GetInputStreamAt(0));
        await reader.LoadAsync((uint)stream.Size);
        var bytes = new byte[stream.Size];
        reader.ReadBytes(bytes);

        if (!string.IsNullOrWhiteSpace(output))
        {
            var outputPath = Path.GetFullPath(output);
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
            await File.WriteAllBytesAsync(outputPath, bytes);
            output = outputPath;
        }

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = "camera-frame-probe",
            mode = "capture",
            name_contains = nameContains,
            selected = new { id = selected.Id, name = selected.Name },
            frame = new
            {
                width = decoder.PixelWidth,
                height = decoder.PixelHeight,
                bytes = bytes.Length,
                format = decoder.DecoderInformation.FriendlyName
            },
            output
        }, new JsonSerializerOptions { WriteIndented = true }));
        return 0;
    }
    catch (Exception ex)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = false,
            command = "camera-frame-probe",
            mode = "capture",
            name_contains = nameContains,
            selected = new { id = selected.Id, name = selected.Name },
            error = ex.Message,
            exception_type = ex.GetType().FullName
        }, new JsonSerializerOptions { WriteIndented = true }));
        return 1;
    }
}

return await MainAsync(args);
