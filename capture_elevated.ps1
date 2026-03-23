# Capture USB traffic on all USBPcap interfaces simultaneously for 30 seconds
# Run as Administrator

$usbpcap = "C:\Program Files\USBPcap\USBPcapCMD.exe"
$outDir = "C:\Projects Folder\ROCCAT_Manager_Full"
$procs = @()

Write-Host "Starting USB capture on all 5 interfaces..." -ForegroundColor Green

for ($i = 1; $i -le 5; $i++) {
    $iface = "\\.\USBPcap$i"
    $outFile = Join-Path $outDir "cap_iface$i.pcap"
    if (Test-Path $outFile) { Remove-Item $outFile -Force }

    $proc = Start-Process -FilePath $usbpcap `
        -ArgumentList "-d", $iface, "-o", $outFile, "-A", "--snaplen", "65535" `
        -NoNewWindow -PassThru
    $procs += $proc
    Write-Host "  Started capture on USBPcap$i (PID $($proc.Id))"
}

Write-Host ""
Write-Host "CAPTURING for 30 seconds..." -ForegroundColor Yellow
Write-Host "NOW: Change DPI in SWARM II and save!" -ForegroundColor Red
Write-Host ""

Start-Sleep -Seconds 30

Write-Host "Stopping captures..." -ForegroundColor Green
foreach ($proc in $procs) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1

Write-Host ""
Write-Host "Results:" -ForegroundColor Cyan
for ($i = 1; $i -le 5; $i++) {
    $outFile = Join-Path $outDir "cap_iface$i.pcap"
    if (Test-Path $outFile) {
        $size = (Get-Item $outFile).Length
        $marker = if ($size -gt 100) { " <<<< HAS TRAFFIC" } else { "" }
        Write-Host "  USBPcap$i : $size bytes$marker"
    } else {
        Write-Host "  USBPcap$i : NO FILE"
    }
}
