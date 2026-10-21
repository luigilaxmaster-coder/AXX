Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile("C:\Users\luigi\.gemini\antigravity-ide\brain\c61d2cb8-2930-4017-ba42-771c28675612\current_screen.png")
$cropRect = New-Object System.Drawing.Rectangle(520, 280, 400, 400)
$bmp = New-Object System.Drawing.Bitmap($cropRect.Width, $cropRect.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.DrawImage($img, (New-Object System.Drawing.Rectangle(0, 0, $cropRect.Width, $cropRect.Height)), $cropRect, [System.Drawing.GraphicsUnit]::Pixel)
$g.Dispose()
$img.Dispose()
$outPath = "C:\Users\luigi\.gemini\antigravity-ide\brain\c61d2cb8-2930-4017-ba42-771c28675612\crop_axx_center.png"
$bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "Center crop saved to $outPath"
