Get-Process | Where-Object { $_.ProcessName -match "Axx|msedgewebview2" } | Select-Object Id, ProcessName, MainWindowTitle, MainWindowHandle
