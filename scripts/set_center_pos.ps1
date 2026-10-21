$configPath = "C:\Users\luigi\AppData\Local\Axx\native-window.json"
$config = @{
    version = 2
    anchor_screen_x = 768.0
    anchor_screen_y = 432.0
    always_on_top = $true
    monitor = "\\.\DISPLAY1"
} | ConvertTo-Json

[System.IO.File]::WriteAllText($configPath, $config)
Write-Host "native-window.json updated:"
Get-Content $configPath
