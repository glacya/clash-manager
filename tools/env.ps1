# 현재 PowerShell 세션에만 프로젝트 도구 경로를 설정합니다 (시스템/사용자 환경변수는 건드리지 않음).
# 사용: . .\tools\env.ps1
$tools = $PSScriptRoot
$env:ANDROID_HOME = "$tools\android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:APPIUM_HOME = "$tools\appium-home"
$env:Path = "$tools\node;$tools\appium\node_modules\.bin;$env:ANDROID_HOME\platform-tools;$env:Path"
