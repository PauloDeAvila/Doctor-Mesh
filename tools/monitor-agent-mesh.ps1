$logPath = 'C:\Users\phsra\OneDrive\Documents\Doctor Mesh\agent-mesh-chat.jsonl'
$ErrorActionPreference = 'Stop'
Write-Host 'DOCTOR MESH AGENT MESH - MONITOR' -ForegroundColor Cyan
Write-Host "Arquivo: $logPath" -ForegroundColor DarkGray
Write-Host 'Aguardando novas mensagens...' -ForegroundColor Yellow

function Show-Message([string]$line) {
    if ([string]::IsNullOrWhiteSpace($line)) { return }
    try { $m = $line | ConvertFrom-Json } catch { return }
    $colors = @{
        'delegado' = 'Red'
        'geometria' = 'Blue'
        'qualidade' = 'Green'
        'testes' = 'Yellow'
        'sistema' = 'Cyan'
    }
    $color = if ($colors.ContainsKey($m.sender)) { $colors[$m.sender] } else { 'Gray' }
    $stamp = ([datetime]$m.time).ToLocalTime().ToString('HH:mm:ss')
    Write-Host "[$stamp] $($m.sender) -> $($m.recipient) [$($m.kind)]" -ForegroundColor $color
    Write-Host $m.text -ForegroundColor White
    Write-Host ('-' * 80) -ForegroundColor DarkGray
}

try {
    if (Test-Path -LiteralPath $logPath) {
        Get-Content -LiteralPath $logPath -Encoding UTF8 -Wait | ForEach-Object { Show-Message $_ }
    } else {
        Write-Host 'O arquivo ainda não existe; aguardando criação...' -ForegroundColor Yellow
        while (-not (Test-Path -LiteralPath $logPath)) { Start-Sleep -Milliseconds 500 }
        Get-Content -LiteralPath $logPath -Encoding UTF8 -Wait | ForEach-Object { Show-Message $_ }
    }
} catch {
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Pressione Enter para fechar'
}
