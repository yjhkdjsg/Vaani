$ErrorActionPreference = "Stop"

$BUILD_DIR = Join-Path $PSScriptRoot "..\build"
$CHAT_DIR = Join-Path $BUILD_DIR "chat_handler"
$SOURCE_ROOT = Join-Path $PSScriptRoot "..\.."

New-Item -ItemType Directory -Force -Path $CHAT_DIR | Out-Null

pip install boto3 -t $CHAT_DIR --platform manylinux2014_aarch64 --only-binary=:all: --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed"
    exit 1
}

Copy-Item -Path (Join-Path $SOURCE_ROOT "lambda\chat_handler\lambda_function.py") -Destination $CHAT_DIR -Force
Copy-Item -Path (Join-Path $SOURCE_ROOT "services") -Destination $CHAT_DIR -Recurse -Force
Copy-Item -Path (Join-Path $SOURCE_ROOT "utils") -Destination $CHAT_DIR -Recurse -Force
Copy-Item -Path (Join-Path $SOURCE_ROOT "config") -Destination $CHAT_DIR -Recurse -Force

$ZIP_PATH = Join-Path $BUILD_DIR "chat_handler.zip"
Push-Location $CHAT_DIR
Compress-Archive -Path * -DestinationPath $ZIP_PATH -Force
Pop-Location

Write-Host "Build complete: $ZIP_PATH"
