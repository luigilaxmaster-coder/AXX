# Pure worker contract: synthetic elements, no desktop inspection or input.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../backend/actions/uia_worker.ps1') -Raw
$tokens=$null; $parseErrors=$null
[System.Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$parseErrors) | Out-Null
if ($parseErrors.Count) { throw 'UIA worker syntax failed' }
$start=$source.IndexOf('        $metadata = ')
$end=$source.IndexOf('        $answer = [ordered]', $start)
if ($start -lt 0 -or $end -le $start) { throw 'Metadata loop not found' }
$script:cachedReads=0
$script:fixtures=@()
foreach ($secret in @($false,$true)) {
    $element=[pscustomobject]@{Cached=[pscustomobject]@{
        IsPassword=$secret; ControlType=[System.Windows.Automation.ControlType]::Button
        IsOffscreen=$false; Name=$(if($secret){'PRIVATE'}else{'Apply'}); AutomationId='fixture'; ClassName='fixture'; IsEnabled=$true
        BoundingRectangle=[pscustomobject]@{X=20;Y=30;Width=90;Height=40}
    }}
    $element | Add-Member ScriptProperty Current { throw 'Unbatched metadata read' }
    $element | Add-Member ScriptMethod GetUpdatedCache {
        param($cache)
        if ($cache.TreeScope -ne [System.Windows.Automation.TreeScope]::Element) { throw 'Unexpected metadata scope' }
        $script:cachedReads++; return $this
    }
    $element | Add-Member ScriptMethod TryGetCurrentPattern { param($pattern,[ref]$result); return $false }
    $script:fixtures+=,$element
}
$all=[pscustomobject]@{}
$all | Add-Member ScriptMethod Item { param($index); return $script:fixtures[$index] }
function Get-ControlToken { return 'fixture-control' }
function Get-SupportedPatterns { return @() }
function Get-PatternState { return @{} }
function Convert-BoundedCoordinate($value) { return [int]$value }
$request=[pscustomobject]@{window_id=1;pid=2}
$reading=$true; $scraping=$false; $remaining=24000; $contentLimited=$false; $protected=$null; $count=2
$items=[System.Collections.Generic.List[object]]::new()
& ([scriptblock]::Create($source.Substring($start,$end-$start)))
if ($script:cachedReads -ne 2 -or $items.Count -ne 1 -or $items[0].name -ne 'Apply' -or
    $items[0].bounds.x -ne 20 -or $items[0].read_only -ne $true -or ($items | ConvertTo-Json -Depth 8) -match 'PRIVATE') {
    throw 'Metadata batching or protected-control exclusion failed'
}
'UIA_BATCHED_METADATA_PASSWORD_EXCLUSION_PASS'
