# 校园网 VPN 预连（Windows rasdial）。凭据由调用方通过环境变量传入，勿把密码写入仓库。
# 前置：在「设置 → 网络和 Internet → VPN」中已添加与 SCHOOL_VPN_CONN_NAME 同名的连接（服务器地址等按学校说明填写）。
$ErrorActionPreference = "Stop"
$name = $env:SCHOOL_VPN_CONN_NAME
$user = $env:SCHOOL_VPN_USER
$pass = $env:SCHOOL_VPN_PASS
$expectIp = $env:SCHOOL_VPN_EXPECTED_IPV4

if (-not $name -or -not $user -or -not $pass) {
    Write-Host "[VPN] 缺少环境变量 SCHOOL_VPN_CONN_NAME / SCHOOL_VPN_USER / SCHOOL_VPN_PASS"
    exit 2
}

if ($expectIp) {
    try {
        $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress })
        if ($ips -contains $expectIp) {
            Write-Host "[VPN] 本机已存在 IPv4 $expectIp，视为已挂 VPN，跳过拨号。"
            exit 0
        }
    } catch {
        Write-Host "[VPN] Get-NetIPAddress 检查失败，继续尝试拨号: $_"
    }
}

try {
    $vc = Get-VpnConnection -Name $name -ErrorAction SilentlyContinue
    if ($vc -and $vc.ConnectionStatus -eq "Connected") {
        Write-Host "[VPN] Windows 报告「$name」已连接，跳过拨号。"
        exit 0
    }
} catch {
    Write-Host "[VPN] Get-VpnConnection 检查失败，继续尝试拨号: $_"
}

Write-Host "[VPN] 正在 rasdial「$name」…"
$p = Start-Process -FilePath "rasdial.exe" -ArgumentList @($name, $user, $pass) -Wait -PassThru -NoNewWindow
exit $p.ExitCode
