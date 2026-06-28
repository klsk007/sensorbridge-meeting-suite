using System.Text.Json;
using Windows.Devices.Enumeration;

static async Task<IReadOnlyList<object>> EnumerateAsync(DeviceClass deviceClass)
{
    var devices = await DeviceInformation.FindAllAsync(deviceClass);
    return devices
        .Select(device => new
        {
            id = device.Id,
            name = device.Name,
            isEnabled = device.IsEnabled,
            kind = device.Kind.ToString(),
            enclosureLocation = device.EnclosureLocation?.Panel.ToString()
        })
        .Cast<object>()
        .ToArray();
}

var payload = new
{
    ok = true,
    method = "Windows.Devices.Enumeration.DeviceInformation.FindAllAsync",
    audioCapture = await EnumerateAsync(DeviceClass.AudioCapture),
    audioRender = await EnumerateAsync(DeviceClass.AudioRender)
};

Console.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
