param(
  [string]$SourceDir = ''
)

$ErrorActionPreference = 'Stop'
$audioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $audioRoot)
if (-not $SourceDir) {
  $SourceDir = Join-Path $root 'third_party\src\Windows-driver-samples\audio\sysvad'
}

$tabletDir = Join-Path $SourceDir 'TabletAudioSample'
$files = @(
  (Join-Path $tabletDir 'ComponentizedAudioSample.inx'),
  (Join-Path $tabletDir 'ComponentizedAudioSampleExtension.inx'),
  (Join-Path $tabletDir 'ComponentizedApoSample.inx')
)

foreach ($path in $files) {
  if (-not (Test-Path $path)) {
    throw "SysVAD source template not found: $path"
  }
}

function Update-TextFile {
  param(
    [string]$Path,
    [hashtable]$Replacements
  )

  $text = Get-Content -Raw -Path $Path
  $changed = $false
  foreach ($old in $Replacements.Keys) {
    $new = $Replacements[$old]
    if ($text.Contains($old)) {
      $text = $text.Replace($old, $new)
      $changed = $true
    }
  }

  $normalized = $text -replace '\.10\.0(\.\.\.\d+)+', '.10.0...16299'
  if ($normalized -ne $text) {
    $text = $normalized
    $changed = $true
  }

  if ($changed -or $text.Contains('SensorBridge')) {
    Set-Content -Path $Path -Value $text -Encoding Ascii -NoNewline
  }

  return $changed
}

function Update-CompatibilityPatch {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return $false
  }
  $replacements = @{
    'ExAllocateFromNPagedLookasideList(&m_BthHfpWorkTaskPool)' = 'ExAllocatePool2(POOL_FLAG_NON_PAGED, m_BthHfpWorkTaskPoolElementSize, MINADAPTER_POOLTAG)'
    'ExFreeToNPagedLookasideList(&m_BthHfpWorkTaskPool, bthWorkTask)' = 'ExFreePoolWithTag(bthWorkTask, MINADAPTER_POOLTAG)'
    'ExFreeToNPagedLookasideList(&This->m_BthHfpWorkTaskPool, task)' = 'ExFreePoolWithTag(task, MINADAPTER_POOLTAG)'
    'ExAllocateFromNPagedLookasideList(&m_UsbSidebandWorkTaskPool)' = 'ExAllocatePool2(POOL_FLAG_NON_PAGED, m_UsbSidebandWorkTaskPoolElementSize, MINADAPTER_POOLTAG)'
    'ExFreeToNPagedLookasideList(&m_UsbSidebandWorkTaskPool, usbHsWorkTask)' = 'ExFreePoolWithTag(usbHsWorkTask, MINADAPTER_POOLTAG)'
    'ExFreeToNPagedLookasideList(&This->m_UsbSidebandWorkTaskPool, task)' = 'ExFreePoolWithTag(task, MINADAPTER_POOLTAG)'
    'ExAllocateFromNPagedLookasideList(&m_A2dpSidebandWorkTaskPool)' = 'ExAllocatePool2(POOL_FLAG_NON_PAGED, m_A2dpSidebandWorkTaskPoolElementSize, MINADAPTER_POOLTAG)'
    'ExFreeToNPagedLookasideList(&m_A2dpSidebandWorkTaskPool, a2dpHpWorkTask)' = 'ExFreePoolWithTag(a2dpHpWorkTask, MINADAPTER_POOLTAG)'
    'ExFreeToNPagedLookasideList(&This->m_A2dpSidebandWorkTaskPool, task)' = 'ExFreePoolWithTag(task, MINADAPTER_POOLTAG)'
  }
  return Update-TextFile -Path $Path -Replacements $replacements
}

function Disable-RenderInterfaces {
  param([string]$Path)

  $text = Get-Content -Raw -Path $Path
  $updated = $text
  $renderInterfaceNames = @(
    '%KSNAME_WaveSpeaker%',
    '%KSNAME_TopologySpeaker%',
    '%KSNAME_WaveSpeakerHeadphone%',
    '%KSNAME_TopologySpeakerHeadphone%',
    '%KSNAME_WaveHdmi%',
    '%KSNAME_TopologyHdmi%',
    '%KSNAME_WaveSpdif%',
    '%KSNAME_TopologySpdif%',
    '%KSNAME_WaveBthHfpSpeaker%',
    '%KSNAME_TopologyBthHfpSpeaker%',
    '%KSNAME_WaveUsbHsSpeaker%',
    '%KSNAME_TopologyUsbHsSpeaker%'
  )

  foreach ($name in $renderInterfaceNames) {
    $updated = [regex]::Replace(
      $updated,
      "(?m)^AddInterface=.*$([regex]::Escape($name)).*(\r?\n)?",
      ''
    )
  }

  if ($updated -ne $text) {
    Set-Content -Path $Path -Value $updated -Encoding Ascii -NoNewline
    return $true
  }
  return $false
}

$baseInf = Join-Path $tabletDir 'ComponentizedAudioSample.inx'
$extensionInf = Join-Path $tabletDir 'ComponentizedAudioSampleExtension.inx'
$apoInf = Join-Path $tabletDir 'ComponentizedApoSample.inx'

$baseChanged = Update-TextFile -Path $baseInf -Replacements @{
  '%MfgName%=SYSVAD,NT$ARCH$.10.0...22621' = '%MfgName%=SYSVAD,NT$ARCH$.10.0...16299'
  '%MfgName%=SYSVAD,NT$ARCH$.10.0' = '%MfgName%=SYSVAD,NT$ARCH$.10.0...16299'
  '[SYSVAD.NT$ARCH$.10.0...22621]' = '[SYSVAD.NT$ARCH$.10.0...16299]'
  '[SYSVAD.NT$ARCH$.10.0]' = '[SYSVAD.NT$ARCH$.10.0...16299]'
  'Root\sysvad_ComponentizedAudioSample' = 'Root\SensorBridge_VirtualMicrophone'
  'ProviderName = "TODO-Set-Provider"' = 'ProviderName = "SensorBridge"'
  'MfgName      = "TODO-Set-Manufacturer"' = 'MfgName      = "SensorBridge"'
  'MsCopyRight  = "TODO-Set-Copyright"' = 'MsCopyRight  = "SensorBridge development package"'
  'SYSVAD_SA.DeviceDesc="Virtual Audio Device (WDM) - Tablet Sample"' = 'SYSVAD_SA.DeviceDesc="SensorBridge Virtual Microphone (Development)"'
  'SYSVAD_ComponentizedAudioSample.SvcDesc="Virtual Audio Device (WDM) - Tablet Sample Driver"' = 'SYSVAD_ComponentizedAudioSample.SvcDesc="SensorBridge Virtual Microphone Development Driver"'
  'SYSVAD.WaveMicIn.szPname="SYSVAD Wave Microphone Headphone"' = 'SYSVAD.WaveMicIn.szPname="SensorBridge Wave Microphone"'
  'SYSVAD.TopologyMicIn.szPname="SYSVAD Topology Microphone Headphone"' = 'SYSVAD.TopologyMicIn.szPname="SensorBridge Topology Microphone"'
  'SYSVAD.WaveMicArray1.szPname="SYSVAD Wave Microphone Array - Front"' = 'SYSVAD.WaveMicArray1.szPname="SensorBridge Wave Microphone Array"'
  'SYSVAD.TopologyMicArray1.szPname="SYSVAD Topology Microphone Array - Front"' = 'SYSVAD.TopologyMicArray1.szPname="SensorBridge Topology Microphone Array"'
  'SYSVAD.WaveMicArray2.szPname="SYSVAD Wave Microphone Array - Rear"' = 'SYSVAD.WaveMicArray2.szPname="SensorBridge Wave Microphone Array - Secondary"'
  'SYSVAD.TopologyMicArray2.szPname="SYSVAD Topology Microphone Array - Rear"' = 'SYSVAD.TopologyMicArray2.szPname="SensorBridge Topology Microphone Array - Secondary"'
  'SYSVAD.WaveMicArray3.szPname="SYSVAD Wave Microphone Array - Front/Rear"' = 'SYSVAD.WaveMicArray3.szPname="SensorBridge Wave Microphone Array - Wide"'
  'SYSVAD.TopologyMicArray3.szPname="SYSVAD Topology Microphone Array - Front/Rear"' = 'SYSVAD.TopologyMicArray3.szPname="SensorBridge Topology Microphone Array - Wide"'
  'SYSVAD.WaveBthHfpMic.szPname="SYSVAD Wave Bluetooth HFP Microphone"' = 'SYSVAD.WaveBthHfpMic.szPname="SensorBridge Wave Bluetooth HFP Microphone"'
  'SYSVAD.TopologyBthHfpMic.szPname="SYSVAD Topology Bluetooth HFP Microphone"' = 'SYSVAD.TopologyBthHfpMic.szPname="SensorBridge Topology Bluetooth HFP Microphone"'
  'SYSVAD.WaveUsbHsMic.szPname="SYSVAD Wave USB Headset Microphone"' = 'SYSVAD.WaveUsbHsMic.szPname="SensorBridge Wave USB Headset Microphone"'
  'SYSVAD.TopologyUsbHsMic.szPname="SYSVAD Topology USB Headset Microphone"' = 'SYSVAD.TopologyUsbHsMic.szPname="SensorBridge Topology USB Headset Microphone"'
  'MicArray1CustomName= "Internal Microphone Array - Front"' = 'MicArray1CustomName= "SensorBridge iPhone Microphone"'
  'MicArray2CustomName= "Internal Microphone Array - Rear"' = 'MicArray2CustomName= "SensorBridge iPhone Microphone - Secondary"'
  'MicArray3CustomName= "Internal Microphone Array - Front/Rear"' = 'MicArray3CustomName= "SensorBridge iPhone Microphone - Wide"'
  'MicInCustomName= "External Microphone Headphone"' = 'MicInCustomName= "SensorBridge External Microphone"'
}
$renderInterfacesRemoved = Disable-RenderInterfaces -Path $baseInf

$extensionChanged = Update-TextFile -Path $extensionInf -Replacements @{
  'Root\sysvad_ComponentizedAudioSample' = 'Root\SensorBridge_VirtualMicrophone'
  'MfgName              = "TODO-Set-Manufacturer"' = 'MfgName              = "SensorBridge"'
  'ProviderName         = "TODO-Set-Provider"' = 'ProviderName         = "SensorBridge"'
  'Device.ExtensionDesc = "Sample Device Extension"' = 'Device.ExtensionDesc = "SensorBridge Virtual Microphone Extension"'
  'ExtendedFriendlyName = "SYSVAD (with APO Extensions)"' = 'ExtendedFriendlyName = "SensorBridge Virtual Microphone (with APO Extensions)"'
  'Description = "Audio Proxy APO Sample"' = 'Description = "SensorBridge Audio Proxy APO"'
}

$apoChanged = Update-TextFile -Path $apoInf -Replacements @{
  'MfgName           = "TODO-Set-Manufacturer"' = 'MfgName           = "SensorBridge"'
  'ProviderName      = "TODO-Set-Provider"' = 'ProviderName      = "SensorBridge"'
  'Apo.ComponentDesc = "Audio Proxy APO Sample"' = 'Apo.ComponentDesc = "SensorBridge Audio Proxy APO"'
  'SFX_FriendlyName  = "Audio Proxy APO Sample (stream effect)"' = 'SFX_FriendlyName  = "SensorBridge APO (stream effect)"'
  'MFX_FriendlyName  = "Audio Proxy APO Sample (mode effect)"' = 'MFX_FriendlyName  = "SensorBridge APO (mode effect)"'
  'KWS_FriendlyName  = "Keyword Spotter APO Sample (endpoint effect)"' = 'KWS_FriendlyName  = "SensorBridge Keyword Spotter APO (endpoint effect)"'
  'AEC_FriendlyName  = "Acoustic Echo Cancellation APO Sample (mode effect)"' = 'AEC_FriendlyName  = "SensorBridge Acoustic Echo Cancellation APO (mode effect)"'
  'Copyright         = "Sample"' = 'Copyright         = "SensorBridge development package"'
}
$apoText = Get-Content -Raw -Path $apoInf
$apoTextUpdated = $apoText.
  Replace('ApoComponents,NT$ARCH$.10.0...16299', 'ApoComponents,NT$ARCH$.10.0...17763').
  Replace('[ApoComponents.NT$ARCH$.10.0...16299]', '[ApoComponents.NT$ARCH$.10.0...17763]')
if ($apoTextUpdated -ne $apoText) {
  Set-Content -Path $apoInf -Value $apoTextUpdated -Encoding Ascii -NoNewline
  $apoChanged = $true
}

$compatibilityChanged = Update-CompatibilityPatch -Path (Join-Path $SourceDir 'common.cpp')

[ordered]@{
  ok = $true
  component = 'Windows-driver-samples/audio/sysvad'
  mode = 'sensorbridge-virtual-microphone-patch'
  source_dir = $SourceDir
  root_hardware_id = 'Root\SensorBridge_VirtualMicrophone'
  base_changed = $baseChanged
  extension_changed = $extensionChanged
  apo_changed = $apoChanged
  render_interfaces_removed = $renderInterfacesRemoved
  win10_compatibility_changed = $compatibilityChanged
  applied = ($baseChanged -or $extensionChanged -or $apoChanged -or $renderInterfacesRemoved -or $compatibilityChanged)
  already_applied = (-not $baseChanged -and -not $extensionChanged -and -not $apoChanged -and -not $renderInterfacesRemoved -and -not $compatibilityChanged)
  files = $files
} | ConvertTo-Json -Depth 5
