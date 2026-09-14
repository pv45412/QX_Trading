# Create QX Platform Desktop Shortcuts
$desktopPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop")
$projectDir = "C:\Project\2026"
$scriptsDir = Join-Path $projectDir "scripts"

$wshShell = New-Object -ComObject WScript.Shell

# Shortcut 1: Start QX Platform
$shortcut1Path = Join-Path $desktopPath "QX Start Platform.lnk"
$shortcut1 = $wshShell.CreateShortcut($shortcut1Path)
$shortcut1.TargetPath = Join-Path $scriptsDir "start_qx.bat"
$shortcut1.WorkingDirectory = $projectDir
$shortcut1.Description = "Start QX Quantitative Platform Backend & Frontend Servers"
$shortcut1.IconLocation = "shell32.dll, 24"
$shortcut1.Save()
Write-Host "[OK] Created Desktop Shortcut: $shortcut1Path"

# Shortcut 2: Stop QX Platform
$shortcut2Path = Join-Path $desktopPath "QX Stop Platform.lnk"
$shortcut2 = $wshShell.CreateShortcut($shortcut2Path)
$shortcut2.TargetPath = Join-Path $scriptsDir "stop_qx.bat"
$shortcut2.WorkingDirectory = $projectDir
$shortcut2.Description = "Stop QX Quantitative Platform Backend & Frontend Servers"
$shortcut2.IconLocation = "shell32.dll, 27"
$shortcut2.Save()
Write-Host "[OK] Created Desktop Shortcut: $shortcut2Path"

# Shortcut 3: Trigger Data Ingestion
$shortcut3Path = Join-Path $desktopPath "QX Trigger Data Ingestion.lnk"
$shortcut3 = $wshShell.CreateShortcut($shortcut3Path)
$shortcut3.TargetPath = Join-Path $scriptsDir "trigger_data_ingestion.bat"
$shortcut3.WorkingDirectory = $projectDir
$shortcut3.Description = "Trigger QX Platform Automated Data Ingestion & Cache Warmup"
$shortcut3.IconLocation = "shell32.dll, 14"
$shortcut3.Save()
Write-Host "[OK] Created Desktop Shortcut: $shortcut3Path"

Write-Host "`nAll Desktop shortcuts created successfully!"
