# Default Docker runner for input PDFs
param(
    [string]$PdfFile,
    [string]$Output = 'output.md'
)

# Check Docker
$dockerRunning = docker info 2>&1 | Select-String 'Server Version' -Quiet
if (-not $dockerRunning) {
    Write-Host 'Error: Docker Desktop not running' -ForegroundColor Red
    exit 1
}

# Ensure output dir
if (-not (Test-Path 'output')) {
    New-Item -ItemType Directory -Path 'output' | Out-Null
}

# Get PDF
if ($PdfFile) {
    $pdfPath = $PdfFile
} else {
    $pdfFiles = Get-ChildItem 'input' -Filter '*.pdf'
    if ($pdfFiles.Count -eq 0) {
        Write-Host 'Error: No PDF found in input folder' -ForegroundColor Red
        exit 1
    } elseif ($pdfFiles.Count -eq 1) {
        $pdfPath = $pdfFiles[0].Name
        Write-Host "Auto select: $($pdfFiles[0].Name)" -ForegroundColor Cyan
    } else {
        Write-Host 'PDFs found:' -ForegroundColor Cyan
        for ($i = 0; $i -lt $pdfFiles.Count; $i++) {
            Write-Host "  $($i + 1). $($pdfFiles[$i].Name)"
        }
        $choice = Read-Host 'Select (1-$($pdfFiles.Count))'
        $idx = [int]$choice - 1
        $pdfPath = $pdfFiles[$idx].Name
    }
}

$env:PDF_FILE = $pdfPath
$env:OUTPUT_FILE = $Output

Write-Host "
Converting: $pdfPath" -ForegroundColor Green
Write-Host "Output: $Output
" -ForegroundColor Green

docker compose run --rm lawtomd-gpu

if ($LASTEXITCODE -eq 0) {
    Write-Host "
Done!" -ForegroundColor Green
} else {
    Write-Host "
Failed." -ForegroundColor Red
}
