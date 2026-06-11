param(
  [string]$DataRoot = "E:\Project\ADVTEST\data\nuscenes",
  [string]$QuestionPath = "E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_test_questions.json",
  [string]$ApiBase = "http://218.197.140.7:3001/v1",
  [string]$ModelName = "Qwen3.5-35B-A3B"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/5] Setting environment variables..."
$env:NUSCENES_DATAROOT = $DataRoot
$env:NUSCENES_VERSION = "v1.0-test"
$env:VQA_API_BASE_URL = $ApiBase
$env:VQA_MODEL_NAME = $ModelName
$env:VQA_QA_PATH = $QuestionPath

Write-Host "[2/5] Checking required directories..."
$requiredDirs = @(
  (Join-Path $DataRoot "v1.0-test"),
  (Join-Path $DataRoot "samples"),
  (Join-Path $DataRoot "sweeps"),
  (Join-Path $DataRoot "maps")
)
foreach ($d in $requiredDirs) {
  if (-not (Test-Path $d)) {
    throw "Missing required directory: $d"
  }
}

Write-Host "[3/5] Verifying scene count (must be 6019)..."
$sceneJson = Join-Path $DataRoot "v1.0-test\scene.json"
if (-not (Test-Path $sceneJson)) {
  throw "Missing scene metadata: $sceneJson"
}
$sceneCount = python -c "import json,sys; p=sys.argv[1]; print(len(json.load(open(p,'r',encoding='utf-8'))))" $sceneJson
if ([int]$sceneCount -ne 6019) {
  throw "Scene count check failed: expected 6019, got $sceneCount. Current metadata is not full test split."
}

Write-Host "[4/5] Verifying test question set..."
if (-not (Test-Path $QuestionPath)) {
  throw "Missing test question file: $QuestionPath"
}

$questionCount = python -c "import json,sys; p=sys.argv[1]; d=json.load(open(p,'r',encoding='utf-8')); print(len(d.get('questions',d if isinstance(d,list) else [])))" $QuestionPath
if ([int]$questionCount -le 0) {
  throw "Question set is empty or invalid: $QuestionPath"
}

Write-Host "[5/5] Done."
Write-Host "NUSCENES_DATAROOT=$env:NUSCENES_DATAROOT"
Write-Host "NUSCENES_VERSION=$env:NUSCENES_VERSION"
Write-Host "VQA_QA_PATH=$env:VQA_QA_PATH"
Write-Host "SCENE_COUNT=$sceneCount"
Write-Host "QUESTION_COUNT=$questionCount"
