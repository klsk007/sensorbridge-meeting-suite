#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>
#include <wincodec.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cwchar>
#include <filesystem>
#include <string>
#include <thread>
#include <vector>

#include <softcam/softcam.h>

namespace fs = std::filesystem;

struct Options {
    fs::path frame_dir;
    int width = 640;
    int height = 480;
    float fps = 30.0f;
    bool wait_for_connection = false;
};

static std::atomic_bool g_running{true};

BOOL WINAPI CtrlHandler(DWORD control_type)
{
    switch (control_type) {
    case CTRL_C_EVENT:
    case CTRL_BREAK_EVENT:
    case CTRL_CLOSE_EVENT:
    case CTRL_SHUTDOWN_EVENT:
        g_running = false;
        return TRUE;
    default:
        return FALSE;
    }
}

std::wstring NextArg(int& i, int argc, wchar_t** argv)
{
    if (i + 1 >= argc) {
        return L"";
    }
    i += 1;
    return argv[i];
}

Options ParseOptions(int argc, wchar_t** argv)
{
    Options options;
    wchar_t program_data[MAX_PATH] = {};
    DWORD length = GetEnvironmentVariableW(L"ProgramData", program_data, MAX_PATH);
    if (length > 0 && length < MAX_PATH) {
        options.frame_dir = fs::path(program_data) / L"SensorBridge" / L"camera";
    } else {
        options.frame_dir = L"C:\\ProgramData\\SensorBridge\\camera";
    }

    for (int i = 1; i < argc; ++i) {
        std::wstring arg = argv[i];
        if (arg == L"--frame-dir") {
            options.frame_dir = NextArg(i, argc, argv);
        } else if (arg == L"--width") {
            options.width = std::max(4, _wtoi(NextArg(i, argc, argv).c_str()));
        } else if (arg == L"--height") {
            options.height = std::max(4, _wtoi(NextArg(i, argc, argv).c_str()));
        } else if (arg == L"--fps") {
            options.fps = std::max(1.0f, static_cast<float>(_wtof(NextArg(i, argc, argv).c_str())));
        } else if (arg == L"--wait-for-connection") {
            options.wait_for_connection = true;
        }
    }

    options.width = (options.width + 3) & ~3;
    return options;
}

fs::path LatestImagePath(const fs::path& frame_dir)
{
    fs::path bmp = frame_dir / L"latest.bmp";
    if (fs::exists(bmp)) {
        return bmp;
    }
    return {};
}

void DrawPlaceholder(std::vector<unsigned char>& image, int width, int height, unsigned frame_counter)
{
    image.assign(static_cast<size_t>(width) * static_cast<size_t>(height) * 3, 0);
    int bar = static_cast<int>(frame_counter % static_cast<unsigned>(std::max(width, 1)));
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            size_t offset = (static_cast<size_t>(y) * width + x) * 3;
            bool line = std::abs(x - bar) < 8 || y < 36;
            image[offset + 0] = line ? 80 : static_cast<unsigned char>((x * 80) / std::max(width, 1));
            image[offset + 1] = line ? 220 : static_cast<unsigned char>((y * 80) / std::max(height, 1));
            image[offset + 2] = line ? 255 : 30;
        }
    }
}

bool LoadImageBgr24(IWICImagingFactory* factory, const fs::path& path, int width, int height, std::vector<unsigned char>& image)
{
    IWICBitmapDecoder* decoder = nullptr;
    IWICBitmapFrameDecode* frame = nullptr;
    IWICBitmapScaler* scaler = nullptr;
    IWICFormatConverter* converter = nullptr;
    bool ok = false;

    HRESULT hr = factory->CreateDecoderFromFilename(
        path.c_str(),
        nullptr,
        GENERIC_READ,
        WICDecodeMetadataCacheOnDemand,
        &decoder);
    if (FAILED(hr)) {
        goto cleanup;
    }
    hr = decoder->GetFrame(0, &frame);
    if (FAILED(hr)) {
        goto cleanup;
    }
    hr = factory->CreateBitmapScaler(&scaler);
    if (FAILED(hr)) {
        goto cleanup;
    }
    hr = scaler->Initialize(frame, static_cast<UINT>(width), static_cast<UINT>(height), WICBitmapInterpolationModeFant);
    if (FAILED(hr)) {
        goto cleanup;
    }
    hr = factory->CreateFormatConverter(&converter);
    if (FAILED(hr)) {
        goto cleanup;
    }
    hr = converter->Initialize(
        scaler,
        GUID_WICPixelFormat24bppBGR,
        WICBitmapDitherTypeNone,
        nullptr,
        0.0,
        WICBitmapPaletteTypeCustom);
    if (FAILED(hr)) {
        goto cleanup;
    }

    image.resize(static_cast<size_t>(width) * static_cast<size_t>(height) * 3);
    hr = converter->CopyPixels(
        nullptr,
        static_cast<UINT>(width * 3),
        static_cast<UINT>(image.size()),
        image.data());
    ok = SUCCEEDED(hr);

cleanup:
    if (converter) converter->Release();
    if (scaler) scaler->Release();
    if (frame) frame->Release();
    if (decoder) decoder->Release();
    return ok;
}

int wmain(int argc, wchar_t** argv)
{
    SetConsoleCtrlHandler(CtrlHandler, TRUE);
    Options options = ParseOptions(argc, argv);
    fs::create_directories(options.frame_dir);

    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr)) {
        std::fprintf(stderr, "{\"ok\":false,\"error\":\"CoInitializeEx failed\",\"hresult\":\"0x%08lx\"}\n", hr);
        return 1;
    }

    IWICImagingFactory* factory = nullptr;
    hr = CoCreateInstance(
        CLSID_WICImagingFactory,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_PPV_ARGS(&factory));
    if (FAILED(hr)) {
        CoUninitialize();
        std::fprintf(stderr, "{\"ok\":false,\"error\":\"WIC factory creation failed\",\"hresult\":\"0x%08lx\"}\n", hr);
        return 1;
    }

    scCamera camera = scCreateCamera(options.width, options.height, options.fps);
    if (!camera) {
        factory->Release();
        CoUninitialize();
        std::fprintf(stderr, "{\"ok\":false,\"error\":\"scCreateCamera failed\"}\n");
        return 1;
    }

    std::fwprintf(
        stdout,
        L"{\"ok\":true,\"command\":\"directshow_camera_sender\",\"frame_dir\":\"%ls\",\"width\":%d,\"height\":%d,\"fps\":%.3f}\n",
        options.frame_dir.c_str(),
        options.width,
        options.height,
        options.fps);
    std::fflush(stdout);

    if (options.wait_for_connection) {
        scWaitForConnection(camera);
    }

    std::vector<unsigned char> image;
    fs::path loaded_path;
    fs::file_time_type loaded_write_time{};
    bool have_loaded_frame = false;
    unsigned frame_counter = 0;
    auto delay = std::chrono::milliseconds(static_cast<int>(1000.0f / std::max(1.0f, options.fps)));

    while (g_running) {
        fs::path path = LatestImagePath(options.frame_dir);
        bool should_load = false;
        fs::file_time_type write_time{};
        if (!path.empty()) {
            write_time = fs::last_write_time(path);
            should_load = !have_loaded_frame || path != loaded_path || write_time != loaded_write_time;
        }

        if (should_load && LoadImageBgr24(factory, path, options.width, options.height, image)) {
            loaded_path = path;
            loaded_write_time = write_time;
            have_loaded_frame = true;
        }
        if (!have_loaded_frame) {
            DrawPlaceholder(image, options.width, options.height, frame_counter);
        }

        scSendFrame(camera, image.data());
        frame_counter += 1;
        std::this_thread::sleep_for(delay);
    }

    scDeleteCamera(camera);
    factory->Release();
    CoUninitialize();
    return 0;
}
