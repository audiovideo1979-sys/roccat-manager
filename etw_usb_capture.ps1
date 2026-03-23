# Windows built-in USB ETW trace - no extra drivers needed
# Run as Administrator

$outDir = "C:\Projects Folder\ROCCAT_Manager_Full"
$etlFile = Join-Path $outDir "usb_trace.etl"

# USB ETW provider GUIDs
$usbHub3 = "{AC52AD17-CC01-4F85-8DF5-43AA2080B5A4}"  # USB Hub3
$usbPort = "{C88A4EF5-D048-4013-9408-E04B7DB2814A}"  # USB Port
$usbHid  = "{368D2E04-3765-4098-AC63-79EC12E7B4FA}"  # HID class

Write-Host "Starting USB ETW trace..." -ForegroundColor Green
Write-Host "  Output: $etlFile"

# Stop any existing session
logman stop usb_roccat -ets 2>$null

# Start ETW session
logman start usb_roccat -p $usbHub3 0xFFFFFFFF 0xFF -o $etlFile -ets
logman update usb_roccat -p $usbPort 0xFFFFFFFF 0xFF -ets
logman update usb_roccat -p $usbHid 0xFFFFFFFF 0xFF -ets

Write-Host ""
Write-Host "TRACING for 30 seconds..." -ForegroundColor Yellow
Write-Host "NOW: Change DPI in SWARM II and save!" -ForegroundColor Red
Write-Host ""

Start-Sleep -Seconds 30

Write-Host "Stopping trace..." -ForegroundColor Green
logman stop usb_roccat -ets

$size = if (Test-Path $etlFile) { (Get-Item $etlFile).Length } else { 0 }
Write-Host ""
Write-Host "Trace file: $etlFile ($size bytes)" -ForegroundColor Cyan

if ($size -gt 0) {
    Write-Host "Converting to text..." -ForegroundColor Green
    $txtFile = Join-Path $outDir "usb_trace.txt"
    tracerpt $etlFile -o $txtFile -of CSV -y 2>$null
    if (Test-Path $txtFile) {
        $lines = (Get-Content $txtFile | Measure-Object).Count
        Write-Host "Converted: $txtFile ($lines lines)" -ForegroundColor Cyan
    }
}
