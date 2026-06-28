param(
  [string]$SourceDir = ''
)

$ErrorActionPreference = 'Stop'
$cameraRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $cameraRoot)
if (-not $SourceDir) {
  $SourceDir = Join-Path $root 'third_party\src\VCamSample'
}

$header = Join-Path $SourceDir 'VCamSampleSource\FrameGenerator.h'
$source = Join-Path $SourceDir 'VCamSampleSource\FrameGenerator.cpp'
foreach ($path in @($header, $source)) {
  if (-not (Test-Path $path)) {
    throw "VCamSample source file not found: $path"
  }
}

function Update-TextFile {
  param(
    [string]$Path,
    [string]$Old,
    [string]$New
  )
  $text = Get-Content -Raw -Path $Path
  if ($text.Contains($New.Trim()) -or $text.Contains(($New.Trim() -replace "`n", "`r`n"))) {
    return $false
  }
  $oldText = $Old
  $newText = $New
  if (-not $text.Contains($oldText)) {
    $oldText = $Old -replace "`n", "`r`n"
    $newText = $New -replace "`n", "`r`n"
  }
  if (-not $text.Contains($oldText)) {
    throw "Expected source snippet not found in $Path"
  }
  Set-Content -Path $Path -Value $text.Replace($oldText, $newText) -Encoding UTF8 -NoNewline
  return $true
}

$headerChanged = $false
$headerChanged = (Update-TextFile -Path $header -Old @'
	wil::com_ptr_nothrow<IMFTransform> _converter;
	wil::com_ptr_nothrow<IWICBitmap> _bitmap;
	wil::com_ptr_nothrow<IMFDXGIDeviceManager> _dxgiManager;

	HRESULT CreateRenderTargetResources(UINT width, UINT height);
'@ -New @'
	wil::com_ptr_nothrow<IMFTransform> _converter;
	wil::com_ptr_nothrow<IWICBitmap> _bitmap;
	wil::com_ptr_nothrow<IWICImagingFactory> _wicFactory;
	wil::com_ptr_nothrow<IMFDXGIDeviceManager> _dxgiManager;

	HRESULT CreateRenderTargetResources(UINT width, UINT height);
	HRESULT TryDrawSensorBridgeFrameFile(bool* drewFrame);
'@) -or $headerChanged

$sourceChanged = $false
$sourceChanged = (Update-TextFile -Path $source -Old @'
		wil::com_ptr_nothrow<IWICImagingFactory> wicFactory;
		RETURN_IF_FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_ALL, IID_PPV_ARGS(&wicFactory)));

		RETURN_IF_FAILED(wicFactory->CreateBitmap(width, height, GUID_WICPixelFormat32bppPBGRA, WICBitmapCacheOnDemand, &_bitmap));
'@ -New @'
		RETURN_IF_FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_ALL, IID_PPV_ARGS(&_wicFactory)));

		RETURN_IF_FAILED(_wicFactory->CreateBitmap(width, height, GUID_WICPixelFormat32bppPBGRA, WICBitmapCacheOnDemand, &_bitmap));
'@) -or $sourceChanged

$sourceChanged = (Update-TextFile -Path $source -Old @'
	assert(_renderTarget);
	RETURN_IF_FAILED(_renderTarget->CreateSolidColorBrush(D2D1::ColorF(1, 1, 1, 1), &_whiteBrush));
'@ -New @'
	assert(_renderTarget);
	if (!_wicFactory)
	{
		RETURN_IF_FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_ALL, IID_PPV_ARGS(&_wicFactory)));
	}
	RETURN_IF_FAILED(_renderTarget->CreateSolidColorBrush(D2D1::ColorF(1, 1, 1, 1), &_whiteBrush));
'@) -or $sourceChanged

$sourceChanged = (Update-TextFile -Path $source -Old @'
HRESULT FrameGenerator::Generate(IMFSample* sample, REFGUID format, IMFSample** outSample)
'@ -New @'
HRESULT FrameGenerator::TryDrawSensorBridgeFrameFile(bool* drewFrame)
{
	RETURN_HR_IF_NULL(E_POINTER, drewFrame);
	*drewFrame = false;
	if (!_renderTarget || !_wicFactory)
	{
		return S_FALSE;
	}

	wchar_t programData[MAX_PATH]{};
	auto len = GetEnvironmentVariableW(L"ProgramData", programData, ARRAYSIZE(programData));
	if (!len || len >= ARRAYSIZE(programData))
	{
		return S_FALSE;
	}

	std::wstring basePath(programData);
	basePath += L"\\SensorBridge\\camera\\";
	auto path = basePath + L"latest.bmp";
	if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES)
	{

		wil::com_ptr_nothrow<IWICBitmapDecoder> decoder;
		auto hr = _wicFactory->CreateDecoderFromFilename(path.c_str(), nullptr, GENERIC_READ, WICDecodeMetadataCacheOnLoad, &decoder);
		if (FAILED(hr))
		{
			return S_FALSE;
		}

		wil::com_ptr_nothrow<IWICBitmapFrameDecode> frame;
		hr = decoder->GetFrame(0, &frame);
		if (FAILED(hr))
		{
			return S_FALSE;
		}

		wil::com_ptr_nothrow<IWICFormatConverter> converter;
		RETURN_IF_FAILED(_wicFactory->CreateFormatConverter(&converter));
		RETURN_IF_FAILED(converter->Initialize(
			frame.get(),
			GUID_WICPixelFormat32bppPBGRA,
			WICBitmapDitherTypeNone,
			nullptr,
			0.0,
			WICBitmapPaletteTypeCustom));

		wil::com_ptr_nothrow<ID2D1Bitmap> bitmap;
		RETURN_IF_FAILED(_renderTarget->CreateBitmapFromWicBitmap(converter.get(), nullptr, &bitmap));
		_renderTarget->DrawBitmap(bitmap.get(), D2D1::RectF(0, 0, (FLOAT)_width, (FLOAT)_height));
		*drewFrame = true;
		return S_OK;
	}

	return S_FALSE;
}

HRESULT FrameGenerator::Generate(IMFSample* sample, REFGUID format, IMFSample** outSample)
'@) -or $sourceChanged

$sourceChanged = (Update-TextFile -Path $source -Old @'
		_renderTarget->BeginDraw();
		_renderTarget->Clear(D2D1::ColorF(0, 0, 1, 1));

		// draw some HSL blocks
		const float divisor = 20;
		for (UINT i = 0; i < _width / divisor; i++)
		{
			for (UINT j = 0; j < _height / divisor; j++)
			{
				wil::com_ptr_nothrow<ID2D1SolidColorBrush> brush;
				auto color = HSL2RGB((float)i / (_height / divisor), 1, ((float)j / (_width / divisor)));
				RETURN_IF_FAILED(_renderTarget->CreateSolidColorBrush(color, &brush));
				_renderTarget->FillRectangle(D2D1::Rect(i * divisor, j * divisor, (i + 1) * divisor, (j + 1) * divisor), brush.get());
			}
		}

		auto radius = divisor * 2;
		const float padding = 1;
		_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(radius + padding, radius + padding), radius, radius), _whiteBrush.get());
		_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(radius + padding, _height - radius - padding), radius, radius), _whiteBrush.get());
		_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(_width - radius - padding, radius + padding), radius, radius), _whiteBrush.get());
		_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(_width - radius - padding, _height - radius - padding), radius, radius), _whiteBrush.get());
		_renderTarget->DrawRectangle(D2D1::Rect(radius, radius, _width - radius, _height - radius), _whiteBrush.get());
'@ -New @'
		_renderTarget->BeginDraw();
		_renderTarget->Clear(D2D1::ColorF(0, 0, 1, 1));
		bool drewSensorBridgeFrame = false;
		auto drawFrameHr = TryDrawSensorBridgeFrameFile(&drewSensorBridgeFrame);
		if (FAILED(drawFrameHr))
		{
			WINTRACE(L"FrameGenerator::TryDrawSensorBridgeFrameFile failed: 0x%08X", drawFrameHr);
		}

		// draw some HSL blocks
		if (!drewSensorBridgeFrame)
		{
			const float divisor = 20;
			for (UINT i = 0; i < _width / divisor; i++)
			{
				for (UINT j = 0; j < _height / divisor; j++)
				{
					wil::com_ptr_nothrow<ID2D1SolidColorBrush> brush;
					auto color = HSL2RGB((float)i / (_height / divisor), 1, ((float)j / (_width / divisor)));
					RETURN_IF_FAILED(_renderTarget->CreateSolidColorBrush(color, &brush));
					_renderTarget->FillRectangle(D2D1::Rect(i * divisor, j * divisor, (i + 1) * divisor, (j + 1) * divisor), brush.get());
				}
			}

			auto radius = divisor * 2;
			const float padding = 1;
			_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(radius + padding, radius + padding), radius, radius), _whiteBrush.get());
			_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(radius + padding, _height - radius - padding), radius, radius), _whiteBrush.get());
			_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(_width - radius - padding, radius + padding), radius, radius), _whiteBrush.get());
			_renderTarget->DrawEllipse(D2D1::Ellipse(D2D1::Point2F(_width - radius - padding, _height - radius - padding), radius, radius), _whiteBrush.get());
			_renderTarget->DrawRectangle(D2D1::Rect(radius, radius, _width - radius, _height - radius), _whiteBrush.get());
		}
'@) -or $sourceChanged

[ordered]@{
  ok = $true
  component = 'VCamSample'
  mode = 'sensorbridge-frame-file-patch'
  source_dir = $SourceDir
  header_changed = $headerChanged
  source_changed = $sourceChanged
  applied = ($headerChanged -or $sourceChanged)
  already_applied = (-not $headerChanged -and -not $sourceChanged)
  frame_file_dir = Join-Path $env:ProgramData 'SensorBridge\camera'
} | ConvertTo-Json -Depth 5
