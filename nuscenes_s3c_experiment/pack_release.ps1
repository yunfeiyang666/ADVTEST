# ADVTEST 发布包：代码 + 过滤场景图 + deploy +（可选）dataset\Trainval 子集
#   默认与量产一致：仅打包 <ADVTEST>\dataset\Trainval 下内容（maps、samples、test6019_bundle、
#   v1.0-trainval、.v1.0-trainval_meta.txt 等），约数 GB 级，非 data\nuscenes 全树。
#
# 仅代码与小数据（默认，几十 MB 级）:
#   powershell -ExecutionPolicy Bypass -File nuscenes_s3c_experiment\pack_release.ps1
#
# 连同 dataset\Trainval 打进同一个 tar.gz:
#   powershell -ExecutionPolicy Bypass -File nuscenes_s3c_experiment\pack_release.ps1 -IncludeNuScenesData
#
# 拆成 CODE 包 + DATA 包（推荐大文件断点续传）:
#   powershell -ExecutionPolicy Bypass -File nuscenes_s3c_experiment\pack_release.ps1 -IncludeNuScenesData -SplitArchive
#
# 自定义数据源目录:
#   ... -IncludeNuScenesData -NuScenesDataPath "D:\my_Trainval"
#
# 旧版：整树打包 data\nuscenes（体积极大，一般不用）:
#   ... -IncludeNuScenesData -DataBundleKind DataNuscenes
#
# Trainval 目录下若还有 *_blobs.tgz、can_bus.zip 等，默认不会打进包；需要整文件夹时加:
#   -TrainvalFullFolder
#
param(
    [string]$OutDir = "",
    [string]$AdvtestRoot = "",
    [switch]$IncludeNuScenesData,
    [string]$NuScenesDataPath = "",
    [switch]$SplitArchive,
    [ValidateSet("Trainval", "DataNuscenes")]
    [string]$DataBundleKind = "Trainval",
    [switch]$TrainvalFullFolder
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
if (-not $AdvtestRoot) { $AdvtestRoot = $RepoRoot }
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot ("advtest_release_" + $stamp)
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$PkgCode = Join-Path $OutDir "official_pipeline"
$PkgSg   = Join-Path $OutDir "filtered_scene_graphs"
$PkgDep  = Join-Path $OutDir "deploy"

Write-Host "OUT: $OutDir"

function Invoke-RobocopyNuScenes {
    param([string]$Src, [string]$Dest)
    if (-not (Test-Path $Src)) {
        throw "nuScenes 数据目录不存在: $Src"
    }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Write-Host "robocopy (MT) $Src to $Dest"
    # /XJ：排除 junction/符号链接（本仓库 data/nuscenes 下常有自指 nuscenes 联接，tar 会报 Invalid argument）
    & robocopy $Src $Dest /E /COPY:DAT /XJ /R:2 /W:2 /MT:8 /NFL /NDL /NJH /NJS
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy 失败，退出码=$rc （见 robocopy 文档）"
    }
}

# 与资源管理器所列一致：maps / samples / test6019_bundle / v1.0-trainval / .v1.0-trainval_meta.txt（不含 blobs 压缩包等）
function Invoke-CopyTrainvalDisplayedSubset {
    param([string]$SrcRoot, [string]$DestRoot)
    if (-not (Test-Path $SrcRoot)) {
        throw "Trainval 源目录不存在: $SrcRoot"
    }
    New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null
    Write-Host "Trainval 子集（不含 blobs 等）: $SrcRoot -> $DestRoot"
    foreach ($d in @("maps", "samples", "test6019_bundle", "v1.0-trainval")) {
        $s = Join-Path $SrcRoot $d
        if (Test-Path $s) {
            Invoke-RobocopyNuScenes -Src $s -Dest (Join-Path $DestRoot $d)
        } else {
            Write-Warning "缺少子目录（跳过）: $s"
        }
    }
    $meta = Join-Path $SrcRoot ".v1.0-trainval_meta.txt"
    if (Test-Path $meta) {
        Copy-Item -Force $meta (Join-Path $DestRoot ".v1.0-trainval_meta.txt")
    } else {
        Write-Warning "缺少元信息文件: $meta"
    }
}

function Invoke-CopyBundleData {
    param(
        [string]$SrcRoot,
        [string]$DestRoot,
        [string]$Kind,
        [bool]$TrainvalFull
    )
    if ($Kind -eq "DataNuscenes" -or $TrainvalFull) {
        Invoke-RobocopyNuScenes -Src $SrcRoot -Dest $DestRoot
    } else {
        Invoke-CopyTrainvalDisplayedSubset -SrcRoot $SrcRoot -DestRoot $DestRoot
    }
}

function Invoke-TarGz {
    param([string]$FolderPath, [string]$ArchivePath)
    $parent = Split-Path $FolderPath -Parent
    $leaf   = Split-Path $FolderPath -Leaf
    Push-Location $parent
    try {
        Write-Host "tar.gz: $ArchivePath"
        tar -cvzf $ArchivePath $leaf
    } finally {
        Pop-Location
    }
}

# ── 代码 ─────────────────────────────────────────────────────────────
Copy-Item -Recurse -Force (Join-Path $PSScriptRoot "official_pipeline") $PkgCode
@(".venv", "__pycache__", ".pytest_cache") | ForEach-Object {
    Get-ChildItem -Path $PkgCode -Recurse -Directory -Filter $_ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Remove-Item -Force (Join-Path $PkgCode "advtest_runtime.env") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $PkgCode "output") -ErrorAction SilentlyContinue
Get-ChildItem -Path $PkgCode -Recurse -Filter "*.zip" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# ── 场景图 ───────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $PkgSg | Out-Null
$sgSrc = Join-Path $AdvtestRoot "filtered_scene_graphs"
if (Test-Path $sgSrc) {
    Copy-Item -Force (Join-Path $sgSrc "*.json") $PkgSg
} else {
    Write-Warning "未找到 $sgSrc ，请手动拷贝 filtered_scene_graphs/*.json"
}

# ── deploy ────────────────────────────────────────────────────────────
Copy-Item -Recurse -Force (Join-Path $PSScriptRoot "deploy") $PkgDep
Copy-Item -Force (Join-Path $PkgCode "requirements_server.txt") (Join-Path $OutDir "requirements_server.txt")

# 打包说明（含 dataset/Trainval 时的 env 示例）
$bundleReadme = @"
ADVTEST 解压根目录 = 本目录的上一级在 tar 解压后形成的文件夹（建议改名为 ADVTEST）

【若本包内含 dataset/Trainval】（默认仅含 maps、samples、test6019_bundle、v1.0-trainval、.v1.0-trainval_meta.txt；不含 *_blobs.tgz 等）
  NUSCENES_DATAROOT=<解压根>/dataset/Trainval
  NUSCENES_VERSION=v1.0-trainval
  VQA_QA_JSON=<解压根>/data/nuscenes/qa/NuScenes_val_questions.json
  （题集若不在包内，请单独放置并改 VQA_QA_JSON）

【旧版整包 data/nuscenes】若你使用 -DataBundleKind DataNuscenes 打出的大库：
  NUSCENES_DATAROOT=<解压根>/data/nuscenes
  NUSCENES_VERSION 按实际 v1.0-test 或 v1.0-trainval 填写

三机分工仍见 deploy/README_DEPLOY.txt
"@
$bundleReadme | Set-Content -Encoding UTF8 (Join-Path $OutDir "README_BUNDLE.txt")

$dataRelInBundle = if ($DataBundleKind -eq "DataNuscenes") { "data\nuscenes" } else { "dataset\Trainval" }
$defaultDataSrc = if ($DataBundleKind -eq "DataNuscenes") {
    Join-Path $AdvtestRoot "data\nuscenes"
} else {
    Join-Path $AdvtestRoot "dataset\Trainval"
}
$dataSrc = ""
if ($NuScenesDataPath) {
    $dataSrc = $NuScenesDataPath
} elseif ($IncludeNuScenesData) {
    $dataSrc = $defaultDataSrc
}

$ParentAll = Split-Path $OutDir -Parent
$LeafAll   = Split-Path $OutDir -Leaf

if ($IncludeNuScenesData -and $SplitArchive) {
    # 小包：仅代码+SG+deploy（tar 工作目录固定为 RepoRoot，避免 -OutDir 在外盘时路径错位）
    $OutCode = Join-Path $RepoRoot ("advtest_release_CODE_" + $stamp)
    $TarRootSplit = Split-Path $OutCode -Parent
    New-Item -ItemType Directory -Force -Path $OutCode | Out-Null
    Copy-Item -Recurse -Force $PkgCode (Join-Path $OutCode "official_pipeline")
    Copy-Item -Recurse -Force $PkgSg   (Join-Path $OutCode "filtered_scene_graphs")
    Copy-Item -Recurse -Force $PkgDep  (Join-Path $OutCode "deploy")
    Copy-Item -Force (Join-Path $OutDir "requirements_server.txt") (Join-Path $OutCode "requirements_server.txt")
    Copy-Item -Force (Join-Path $OutDir "README_BUNDLE.txt") (Join-Path $OutCode "README_BUNDLE.txt")
    $LeafCode = Split-Path $OutCode -Leaf
    Push-Location $TarRootSplit
    try {
        tar -cvzf "$LeafCode.tar.gz" $LeafCode
        if ($LASTEXITCODE -ne 0) { throw "tar CODE 失败，退出码=$LASTEXITCODE" }
        Write-Host "OK: $(Join-Path $TarRootSplit "$LeafCode.tar.gz")"
    } finally { Pop-Location }

    # 大包：dataset/Trainval 或 data/nuscenes（由 DataBundleKind 决定）
    $OutData = Join-Path $RepoRoot ("advtest_release_NUSCENES_DATA_" + $stamp)
    $PkgData = Join-Path $OutData $dataRelInBundle
    New-Item -ItemType Directory -Force -Path (Split-Path $PkgData -Parent) | Out-Null
    Invoke-CopyBundleData -SrcRoot $dataSrc -DestRoot $PkgData -Kind $DataBundleKind -TrainvalFull ([bool]$TrainvalFullFolder)
    $dataReadme = if ($DataBundleKind -eq "DataNuscenes") {
        "nuScenes 全树，NUSCENES_DATAROOT=<解压根>/data/nuscenes（VERSION 按实际）"
    } else {
        "6019 子集 Trainval 树，NUSCENES_DATAROOT=<解压根>/dataset/Trainval , NUSCENES_VERSION=v1.0-trainval"
    }
    $dataReadme | Set-Content -Encoding UTF8 (Join-Path $OutData "README_DATA.txt")
    $LeafData = Split-Path $OutData -Leaf
    Push-Location $TarRootSplit
    try {
        tar -cvzf "$LeafData.tar.gz" $LeafData
        if ($LASTEXITCODE -ne 0) { throw "tar DATA 失败，退出码=$LASTEXITCODE" }
        Write-Host "OK: $(Join-Path $TarRootSplit "$LeafData.tar.gz")"
    } finally { Pop-Location }

    Remove-Item -Recurse -Force $OutDir -ErrorAction SilentlyContinue
    Write-Host @"

Split 模式已生成两个压缩包（建议先传 CODE，再传 DATA）:
  $(Join-Path $TarRootSplit "$LeafCode.tar.gz")
  $(Join-Path $TarRootSplit "$LeafData.tar.gz")
解压到同一父目录后，将 $LeafData 下的 dataset（或 data）与 $LeafCode 合并到同一 ADVTEST 根下（与 official_pipeline 并列）。
"@
    exit 0
}

if ($IncludeNuScenesData -and $dataSrc) {
    $PkgData = Join-Path $OutDir $dataRelInBundle
    New-Item -ItemType Directory -Force -Path (Split-Path $PkgData -Parent) | Out-Null
    Invoke-CopyBundleData -SrcRoot $dataSrc -DestRoot $PkgData -Kind $DataBundleKind -TrainvalFull ([bool]$TrainvalFullFolder)
}

Push-Location $ParentAll
try {
    tar -cvzf "$LeafAll.tar.gz" $LeafAll
    if ($LASTEXITCODE -ne 0) { throw "tar 失败，退出码=$LASTEXITCODE" }
    Write-Host "OK: $(Join-Path $ParentAll "$LeafAll.tar.gz")"
} finally {
    Pop-Location
}

Write-Host @"

下一步：
1) 将 $LeafAll.tar.gz 传到服务器解压
2) 若包内含 dataset/Trainval：按 README_BUNDLE.txt 设置 NUSCENES_DATAROOT / v1.0-trainval
3) VQA_QA_JSON（val 题集）若未随包，请单独放置（见 README_BUNDLE.txt）
4) deploy/README_DEPLOY.txt：ADVTEST_EXCEL_PATH、ADVTEST_FRAME_PLAN_JSON（三机不同）
5) cd official_pipeline; pip install -r requirements_server.txt; python run_v17_production.py
"@
