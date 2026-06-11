param(
    [string]$ApiBase = "http://218.197.140.7:3001/v1",
    [string]$Model = "Qwen3.5-122B-A10B",
    [ValidateSet("direct", "env")]
    [string]$ProxyMode = "direct"
)

Write-Host ""
Write-Host "School API env setup (current session)" -ForegroundColor Cyan
Write-Host "base_url = $ApiBase" -ForegroundColor DarkGray
Write-Host "model    = $Model" -ForegroundColor DarkGray
Write-Host "proxy    = $ProxyMode" -ForegroundColor DarkGray
Write-Host ""

$secure = Read-Host "Input API key (sk-...)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
$plain = ($plain -replace '[\x00-\x1F\x7F]', '').Trim()

if ([string]::IsNullOrWhiteSpace($plain)) {
    Write-Host "API key is empty; nothing was set." -ForegroundColor Red
    exit 1
}

$env:VQA_API_KEY = $plain
$env:VQA_API_BASE_URL = $ApiBase
$env:VQA_MODEL_NAME = $Model
$env:VQA_TRUST_ENV_PROXY = if ($ProxyMode -eq "env") { "true" } else { "false" }
$env:VQA_DISABLE_THINKING = "true"

$masked = if ($plain.Length -le 10) { "********" } else { $plain.Substring(0, 6) + "..." + $plain.Substring($plain.Length - 4) }
Write-Host ""
Write-Host "VQA_API_KEY set: $masked" -ForegroundColor Green
Write-Host "VQA_API_BASE_URL set: $env:VQA_API_BASE_URL" -ForegroundColor Green
Write-Host "VQA_MODEL_NAME set: $env:VQA_MODEL_NAME" -ForegroundColor Green
Write-Host "VQA_TRUST_ENV_PROXY set: $env:VQA_TRUST_ENV_PROXY" -ForegroundColor Green
Write-Host "VQA_DISABLE_THINKING set: $env:VQA_DISABLE_THINKING" -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor White
Write-Host "  python bench_models.py --n-calls 3" -ForegroundColor Gray
Write-Host ""
