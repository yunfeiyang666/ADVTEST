param(
  [string]$ApiKey,
  [string]$ApiBase = "http://218.197.140.7:3001/v1",
  [string]$ModelName = "Qwen3.5-35B-A3B"
)

$ErrorActionPreference = "Stop"

$dataRoot = "E:\Project\ADVTEST\data\nuscenes"
$testMeta = Join-Path $dataRoot "v1.0-test"
$qaDir = Join-Path $dataRoot "qa"
$qaPath = Join-Path $qaDir "NuScenes_val_questions.json"

if (-not (Test-Path $testMeta)) { throw "Missing test metadata dir: $testMeta" }
if (-not (Test-Path (Join-Path $dataRoot "samples"))) { throw "Missing dir: $dataRoot\samples" }
if (-not (Test-Path (Join-Path $dataRoot "sweeps"))) { throw "Missing dir: $dataRoot\sweeps" }
if (-not (Test-Path (Join-Path $dataRoot "maps"))) { throw "Missing dir: $dataRoot\maps" }
if (-not (Test-Path $qaPath)) { throw "Missing QA file: $qaPath" }

$sceneCount = python -c "import json,sys; print(len(json.load(open(sys.argv[1],'r',encoding='utf-8'))))" (Join-Path $testMeta "scene.json")
$frameCount = python -c "import json,sys; print(len(json.load(open(sys.argv[1],'r',encoding='utf-8'))))" (Join-Path $testMeta "sample.json")
$qaCount = python -c "import json,sys; d=json.load(open(sys.argv[1],'r',encoding='utf-8')); print(len(d.get('questions',[])))" $qaPath

$env:NUSCENES_DATAROOT = $dataRoot
$env:NUSCENES_VERSION = "v1.0-test"
$env:VQA_API_BASE_URL = $ApiBase
$env:VQA_MODEL_NAME = $ModelName
$env:VQA_QA_PATH = $qaPath
if ($ApiKey) { $env:VQA_API_KEY = $ApiKey }

Write-Host "Configured for test split."
Write-Host "NUSCENES_DATAROOT=$env:NUSCENES_DATAROOT"
Write-Host "NUSCENES_VERSION=$env:NUSCENES_VERSION"
Write-Host "VQA_QA_PATH=$env:VQA_QA_PATH"
Write-Host "TEST_SCENE_COUNT=$sceneCount"
Write-Host "TEST_FRAME_COUNT=$frameCount"
Write-Host "QA_COUNT=$qaCount"
Write-Host "NOTE: Current local QA is val questions file; if you have official test questions file, replace VQA_QA_PATH."
