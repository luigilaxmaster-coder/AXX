$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$effectStarted = $false

try {
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class AxxUiNative { [DllImport("kernel32.dll")] public static extern ulong GetTickCount64(); [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context); [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect); [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; } }'
    if ([AxxUiNative]::SetThreadDpiAwarenessContext([IntPtr]::new(-4)) -eq [IntPtr]::Zero) { throw 'No se pudo establecer geometría física en el worker UIA.' }
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $request -or $request.operation -notin @('capture', 'inspect', 'inspect_browser', 'read_content', 'locate_edit', 'set_value', 'invoke', 'check_value', 'locate_folder', 'scrape_app', 'set_state', 'read_grid', 'read_value')) {
        throw 'Operación UI Automation desconocida.'
    }
    if ($request.operation -eq 'locate_folder') {
        $shell = New-Object -ComObject Shell.Application
        $found = @()
        foreach ($window in $shell.Windows()) {
            try {
                if ([IO.Path]::GetFileName($window.FullName) -ine 'explorer.exe') { continue }
                $actual = [string]$window.Document.Folder.Self.Path
                if ([IO.Path]::GetFullPath($actual).TrimEnd('\') -ine [IO.Path]::GetFullPath([string]$request.path).TrimEnd('\')) { continue }
                $element = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]::new([long]$window.HWND))
                $found += @{window_id=[long]$window.HWND;pid=$element.Current.ProcessId;path=$actual}
            } catch { continue }
        }
        [Console]::Out.Write((@{success=$true;windows=@($found);verification='shell_folder_observed'} | ConvertTo-Json -Depth 4 -Compress))
        exit 0
    }
    if ($request.window_id -le 0 -or $request.pid -le 0) { throw 'Identidad de ventana inválida.' }

    $hwnd = [IntPtr]::new([long]$request.window_id)
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
    if ($null -eq $root -or $root.Current.ProcessId -ne [int]$request.pid) {
        throw 'La ventana observada ya no existe o pertenece a otro proceso.'
    }
    $processStarted = [Diagnostics.Process]::GetProcessById([int]$request.pid).StartTime.ToFileTimeUtc().ToString()
    if ($request.expected_process_started -and $request.expected_process_started -cne $processStarted) { throw 'Cambió la instancia del proceso observado.' }

    if ($request.operation -eq 'capture') {
        Add-Type -AssemblyName System.Drawing
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class AxxWindowCapture { [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr dc, uint flags); [DllImport("user32.dll")] public static extern IntPtr GetWindowDpiAwarenessContext(IntPtr hwnd); }'
        $rect=[AxxUiNative+Rect]::new()
        if (-not [AxxUiNative]::GetWindowRect($hwnd,[ref]$rect)) { throw 'Geometría de captura no disponible.' }
        $physical=@{x=$rect.Left;y=$rect.Top;width=$rect.Right-$rect.Left;height=$rect.Bottom-$rect.Top}
        if ([AxxUiNative]::SetThreadDpiAwarenessContext([AxxWindowCapture]::GetWindowDpiAwarenessContext($hwnd)) -eq [IntPtr]::Zero) { throw 'Contexto DPI de captura no disponible.' }
        if (-not [AxxUiNative]::GetWindowRect($hwnd,[ref]$rect)) { throw 'Geometría de aplicación no disponible.' }
        $width=$rect.Right-$rect.Left; $height=$rect.Bottom-$rect.Top
        if ($width -le 0 -or $height -le 0 -or [long]$width*$height -gt 34000000) { throw 'Tamaño de captura no permitido.' }
        $bitmap=[Drawing.Bitmap]::new($width,$height);$graphics=[Drawing.Graphics]::FromImage($bitmap)
        $small=$null;$memory=[IO.MemoryStream]::new()
        try {
            $dc=$graphics.GetHdc()
            try { if (-not [AxxWindowCapture]::PrintWindow($hwnd,$dc,2)) { throw 'La aplicación no admite captura de ventana.' } }
            finally { $graphics.ReleaseHdc($dc) }
            $scale=[Math]::Min(1,[Math]::Min(1280.0/$width,1280.0/$height))
            $small=[Drawing.Bitmap]::new($bitmap,[int][Math]::Round($width*$scale),[int][Math]::Round($height*$scale))
            $small.Save($memory,[Drawing.Imaging.ImageFormat]::Jpeg)
            if ($memory.Length -gt 350000) { throw 'La imagen excede el límite de envío.' }
            [Console]::Out.Write((@{success=$true;process_started=$processStarted;window_bounds=$physical;jpeg=[Convert]::ToBase64String($memory.ToArray())} | ConvertTo-Json -Compress))
        } finally { if ($small) {$small.Dispose()};$memory.Dispose();$graphics.Dispose();$bitmap.Dispose() }
        exit 0
    }

    function Get-ControlToken($element, [long]$windowId, [int]$processId) {
        $runtimeId = $element.GetRuntimeId()
        $identity = "$windowId`:$processId`:$processStarted`:$($runtimeId -join ',')"
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($identity)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    }

    function Convert-BoundedCoordinate([double]$value) {
        if ([double]::IsNaN($value) -or [double]::IsInfinity($value)) { return 0 }
        return [int][Math]::Round([Math]::Max(-1000000, [Math]::Min(1000000, $value)))
    }

    function Get-SupportedPatterns($element) {
        $patterns = [System.Collections.Generic.List[string]]::new()
        foreach ($pattern in $element.GetSupportedPatterns()) {
            $name = $pattern.ProgrammaticName -replace 'PatternIdentifiers\.Pattern$',''
            if ($name -in @('Invoke','Value','Toggle','SelectionItem','ExpandCollapse','Scroll','Text','RangeValue','Grid','Table','Selection')) { $patterns.Add($name) }
        }
        return @($patterns)
    }

    function Get-PatternState($element, $supported=$null) {
        if ($null -eq $supported) { $supported=Get-SupportedPatterns $element }
        $state = @{}; $p = $null
        if ($supported -contains 'Toggle' -and $element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$p)) { $state.Toggle = $p.Current.ToggleState.ToString() }
        if ($supported -contains 'ExpandCollapse' -and $element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$p)) { $state.ExpandCollapse = $p.Current.ExpandCollapseState.ToString() }
        if ($supported -contains 'SelectionItem' -and $element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$p)) { $state.SelectionItem = [bool]$p.Current.IsSelected }
        if ($supported -contains 'RangeValue' -and $element.TryGetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern, [ref]$p)) {
            $state.RangeValue = @{value=$p.Current.Value; minimum=$p.Current.Minimum; maximum=$p.Current.Maximum; read_only=$p.Current.IsReadOnly}
        }
        if ($supported -contains 'Scroll' -and $element.TryGetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern, [ref]$p)) {
            $state.Scroll = @{horizontal=$p.Current.HorizontalScrollPercent; vertical=$p.Current.VerticalScrollPercent}
        }
        if ($supported -contains 'Grid' -and $element.TryGetCurrentPattern([System.Windows.Automation.GridPattern]::Pattern, [ref]$p)) {
            $state.Grid = @{rows=$p.Current.RowCount; columns=$p.Current.ColumnCount}
        }
        return $state
    }

    function Assert-StateTarget($element, [bool]$requireFocus=$true) {
        if (-not $request.expected_tick_deadline -or [AxxUiNative]::GetTickCount64() -ge [UInt64]$request.expected_tick_deadline) { throw 'STALE_OBSERVATION: la observación caducó antes de verificar el estado.' }
        if ($root.Current.Name -cne $request.expected_title -or $element.Current.Name -cne $request.expected_name -or
            $root.Current.ProcessId -ne [int]$request.pid -or
            [Diagnostics.Process]::GetProcessById([int]$request.pid).StartTime.ToFileTimeUtc().ToString() -cne $request.expected_process_started) { throw 'Cambió el objetivo de la observación.' }
        if ($requireFocus -and [AxxUiNative]::GetForegroundWindow() -ne $hwnd) { throw 'La aplicación perdió el foco antes del efecto.' }
        $rect = [AxxUiNative+Rect]::new()
        if (-not [AxxUiNative]::GetWindowRect($hwnd, [ref]$rect) -or $rect.Left -ne $request.expected_bounds.x -or $rect.Top -ne $request.expected_bounds.y -or
            ($rect.Right-$rect.Left) -ne $request.expected_bounds.width -or ($rect.Bottom-$rect.Top) -ne $request.expected_bounds.height) { throw 'La geometría observada cambió.' }
        if (-not $element.Current.IsEnabled -or $element.Current.IsOffscreen -or $element.Current.IsPassword) { throw 'El control no está disponible para esta acción.' }
    }

    if ($request.operation -eq 'locate_edit') {
        $edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit))
        $found = [System.Collections.Generic.List[object]]::new()
        for ($i = 0; $i -lt [Math]::Min($edits.Count, 64); $i++) {
            $item = $edits.Item($i)
            if (-not $item.Current.IsEnabled -or $item.Current.IsOffscreen -or $item.Current.IsPassword) { continue }
            $pattern = $null
            if (-not $item.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern) -or $pattern.Current.IsReadOnly) { continue }
            $bounds = $item.Current.BoundingRectangle
            if ($bounds.Width -lt 1 -or $bounds.Height -lt 1) { continue }
            $found.Add(@{ control_id = Get-ControlToken $item ([long]$request.window_id) ([int]$request.pid);
                name = [string]$item.Current.Name })
        }
        [Console]::Out.Write((@{success=$true;window_title=[string]$root.Current.Name;controls=@($found);
            process_started=$processStarted;truncated=($edits.Count -gt 64);verification='visible_edit_controls_observed'} | ConvertTo-Json -Depth 4 -Compress))
        exit 0
    }

    if ($request.operation -in @('inspect', 'inspect_browser', 'read_content', 'scrape_app')) {
        $reading = $request.operation -eq 'read_content'
        $scraping = $request.operation -eq 'scrape_app'
        $remaining = 24000
        $contentLimited = $false
        $windowTitle = $root.Current.Name
        if ($reading -and $windowTitle -cne $request.expected_title) { throw 'Cambió la ventana o página desde la preparación. Vuelve a seleccionarla y aprobar la lectura.' }
        $scope = $root
        $browserProcess = [Diagnostics.Process]::GetProcessById([int]$request.pid).ProcessName -in @('chrome','msedge','brave','firefox','opera','vivaldi')
        if ($reading -and $browserProcess -and -not $request.include_browser_chrome) {
            $documents = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document))
            $matching = @($documents | Where-Object { -not $_.Current.IsOffscreen -and $_.Current.Name -and
                ($windowTitle -ceq $_.Current.Name -or $windowTitle.StartsWith($_.Current.Name + ' - ', [StringComparison]::Ordinal) -or
                 $windowTitle.StartsWith($_.Current.Name + ' — ', [StringComparison]::Ordinal)) })
            if ($matching.Count -ne 1) { throw 'No se pudo identificar una única página activa. Activa la pestaña que quieres leer y vuelve a intentarlo.' }
            $scope = $matching[0]
        }
        $items = [System.Collections.Generic.List[object]]::new()
        if ($request.operation -eq 'inspect_browser') {
            $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.OrCondition]::new(
                    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit),
                    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ComboBox)))
        } else {
            $all = $scope.FindAll([System.Windows.Automation.TreeScope]::Subtree,
                [System.Windows.Automation.Condition]::TrueCondition)
        }
        $protected = $scope.FindFirst([System.Windows.Automation.TreeScope]::Subtree,
            [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::IsPasswordProperty, $true))
        $maxAllowed = if ($scraping) { 1000 } elseif ($reading) { 1000 } else { 250 }
        $count = [Math]::Min($all.Count, $maxAllowed)
        # Batch metadata across the provider boundary instead of fetching each property repeatedly.
        $metadata = [System.Windows.Automation.CacheRequest]::new()
        $metadata.TreeScope = [System.Windows.Automation.TreeScope]::Element
        foreach ($property in @('IsPassword','ControlType','IsOffscreen','Name','BoundingRectangle','AutomationId','ClassName','IsEnabled')) {
            $metadata.Add([System.Windows.Automation.AutomationElement]::("${property}Property"))
        }
        for ($i = 0; $i -lt $count; $i++) {
            $item = $all.Item($i)
            $info = $item.GetUpdatedCache($metadata).Cached
            if ($info.IsPassword) { continue }
            $controlType = $info.ControlType.ProgrammaticName
            $name = ''
            if (($reading -and -not $info.IsOffscreen) -or $controlType -in @('ControlType.Button', 'ControlType.CheckBox', 'ControlType.RadioButton',
                'ControlType.MenuItem', 'ControlType.ComboBox', 'ControlType.TabItem', 'ControlType.ToolBar',
                'ControlType.ListItem', 'ControlType.TreeItem', 'ControlType.Slider', 'ControlType.Spinner')) {
                $name = [string]$info.Name
                if ($name.Length -gt 200) { $name = $name.Substring(0, 200) }
            }
            $valuePattern = $null
            $invokePattern = $null
            $hasInvokePattern = $item.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokePattern)
            $hasValuePattern = $item.TryGetCurrentPattern(
                [System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern)
            $supportedPatterns = Get-SupportedPatterns $item
            if (@($supportedPatterns | Where-Object { $_ -in @('Toggle','ExpandCollapse','SelectionItem','RangeValue','Scroll','Value','Grid','Table') }).Count) {
                $name = [string]$info.Name
                if ($name.Length -gt 200) { $name = $name.Substring(0, 200) }
            }
            $text = ''; $value = ''
            if ($reading -and -not $info.IsOffscreen -and $remaining -gt 0) {
                if ($hasValuePattern) {
                    $value = [string]$valuePattern.Current.Value
                    if ($value.Length -gt [Math]::Min(8192, $remaining)) { $contentLimited = $true }
                    $value = $value.Substring(0, [Math]::Min($value.Length, [Math]::Min(8192, $remaining)))
                    $remaining -= $value.Length
                }
                if ($controlType -in @('ControlType.Text', 'ControlType.Hyperlink') -and $remaining -gt 0) {
                    $text = [string]$info.Name
                    if ($text.Length -gt [Math]::Min(2000, $remaining)) { $contentLimited = $true }
                    $text = $text.Substring(0, [Math]::Min($text.Length, [Math]::Min(2000, $remaining)))
                    $remaining -= $text.Length
                }
                if ($null -eq $protected -and $controlType -in @('ControlType.Edit', 'ControlType.Document') -and $remaining -gt 0) {
                    $textPattern = $null
                    if ($item.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$textPattern)) {
                        $text = $textPattern.DocumentRange.GetText([Math]::Min(8192, $remaining))
                        if ($text.Length -ge [Math]::Min(8192, $remaining)) { $contentLimited = $true }
                        $remaining -= $text.Length
                    }
                }
            }
            $rect = $info.BoundingRectangle
            $controlEntry = [ordered]@{
                control_id = (Get-ControlToken $item ([long]$request.window_id) ([int]$request.pid))
                automation_id = [string]$info.AutomationId
                control_type = $controlType
                name = $name
                class_name = [string]$info.ClassName
                enabled = [bool]$info.IsEnabled
                offscreen = [bool]$info.IsOffscreen
                supports_value_pattern = [bool]$hasValuePattern
                supports_invoke_pattern = [bool]$hasInvokePattern
                patterns = $supportedPatterns
                state = (Get-PatternState $item $supportedPatterns)
                read_only = $(
                    if ($hasValuePattern) { [bool]$valuePattern.Current.IsReadOnly }
                    elseif ($controlType -in @('ControlType.Edit','ControlType.Document') -and $supportedPatterns -contains 'Text') {
                        try {
                            $editableText=$null
                            if ($item.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$editableText)) {
                                $readOnly=$editableText.DocumentRange.GetAttributeValue([System.Windows.Automation.TextPattern]::IsReadOnlyAttribute)
                                if ($readOnly -is [bool]) { $readOnly } else { $true }
                            } else { $true }
                        } catch { $true }
                    } else { $true }
                )
                text = $text
                value = $value
                bounds = [ordered]@{ x = (Convert-BoundedCoordinate $rect.X); y = (Convert-BoundedCoordinate $rect.Y);
                    width = (Convert-BoundedCoordinate $rect.Width); height = (Convert-BoundedCoordinate $rect.Height) }
            }
            if ($scraping) {
                $controlEntry['accelerator_key'] = [string]$item.Current.AcceleratorKey
                $controlEntry['access_key'] = [string]$item.Current.AccessKey
                # HelpText can contain document content; discovery exports metadata only.
                if ($controlType -in @('ControlType.Button', 'ControlType.MenuItem', 'ControlType.SplitButton',
                    'ControlType.CheckBox', 'ControlType.RadioButton', 'ControlType.ComboBox', 'ControlType.TabItem',
                    'ControlType.Edit', 'ControlType.Document')) {
                    $controlEntry['patterns'] = (Get-SupportedPatterns $item)
                } else {
                    $controlEntry['patterns'] = @()
                }
            }
            $items.Add($controlEntry)
        }
        $answer = [ordered]@{ success = $true; window_id = [long]$request.window_id; pid = [int]$request.pid;
            window_title = $windowTitle; controls = @($items); truncated = ($all.Count -gt $count); count = $count;
            verification = $(if ($scraping) { 'uia_app_tree_scraped' } else { 'uia_control_tree_observed' }) }
        if ($reading) {
            if ($root.Current.Name -ne $windowTitle) { throw 'La ventana cambió durante la lectura. Vuelve a leerla.' }
            $answer.verification = 'uia_window_content_observed'
            $answer.truncated = $answer.truncated -or $remaining -le 0 -or $contentLimited
            $answer['source'] = 'windows_accessibility'
            $answer['content_status'] = $(if (@($items | Where-Object { $_.text -or $_.value }).Count) { 'observed' } else { 'unavailable' })
            $answer['limitation'] = 'Solo contenido expuesto por la aplicación; puede faltar texto, enlaces o elementos fuera de pantalla. No es acceso al DOM.'
        }
    } else {
        if ($request.operation -in @('set_value','invoke','set_state') -and [AxxUiNative]::GetForegroundWindow().ToInt64() -ne [long]$request.window_id) {
            throw 'La aplicación perdió el foco antes de escribir.'
        }
        if ($request.control_id -notmatch '^[a-f0-9]{64}$') { throw 'control_id observado inválido.' }
        $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition)
        $matches = @()
        for ($i = 0; $i -lt $all.Count; $i++) {
            $candidate = $all.Item($i)
            if ((Get-ControlToken $candidate ([long]$request.window_id) ([int]$request.pid)) -eq $request.control_id) {
                $matches += $candidate
            }
        }
        if ($matches.Count -ne 1) { throw 'El selector observado expiró o dejó de ser único; vuelve a inspeccionar.' }
        $element = $matches[0]
        if (-not $element.Current.IsEnabled -or $element.Current.IsOffscreen) { throw 'El control no está habilitado o visible.' }
        if ($request.operation -eq 'read_value') {
            Assert-StateTarget $element $false
            $pattern = $null
            if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                throw 'El control observado no ofrece ValuePattern.'
            }
            $actual = [string]$pattern.Current.Value
            if ($actual.Length -gt 2048) { throw 'El valor del control excede el límite de lectura.' }
            Assert-StateTarget $element $false
            $answer = @{success=$true;window_id=[long]$request.window_id;pid=[int]$request.pid;
                process_started=$processStarted;control_id=[string]$request.control_id;value=$actual;
                verification='uia_control_value_observed';effect_executed=$false}
            [Console]::Out.Write(($answer | ConvertTo-Json -Depth 4 -Compress)); exit 0
        }
        if ($request.operation -eq 'read_grid') {
            Assert-StateTarget $element $false
            $grid=$null
            if (-not $element.TryGetCurrentPattern([System.Windows.Automation.GridPattern]::Pattern,[ref]$grid)) { throw 'GridPattern no disponible.' }
            if ($request.row -gt $grid.Current.RowCount -or $request.column -gt $grid.Current.ColumnCount) { throw 'Inicio fuera de la tabla.' }
            $rowEnd=[Math]::Min($grid.Current.RowCount,$request.row+$request.rows)
            $columnEnd=[Math]::Min($grid.Current.ColumnCount,$request.column+$request.columns)
            $cells=[System.Collections.Generic.List[object]]::new(); $remaining=24000; $contentLimited=$false
            for ($r=[int]$request.row; $r -lt $rowEnd -and $remaining -gt 0; $r++) {
                for ($c=[int]$request.column; $c -lt $columnEnd -and $remaining -gt 0; $c++) {
                    $cell=$grid.GetItem($r,$c); $text=''; $value=$null
                    if (-not $cell.Current.IsPassword) {
                        $text=[string]$cell.Current.Name
                        if ($cell.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$value)) { $text=[string]$value.Current.Value }
                    }
                    if ($text.Length -gt [Math]::Min($remaining,8192)) { $contentLimited=$true }
                    $text=$text.Substring(0,[Math]::Min($text.Length,[Math]::Min($remaining,8192))); $remaining-=$text.Length
                    $cells.Add(@{row=$r;column=$c;text=$text;redacted=[bool]$cell.Current.IsPassword;control_id=(Get-ControlToken $cell ([long]$request.window_id) ([int]$request.pid))})
                }
            }
            Assert-StateTarget $element $false
            $answer=@{success=$true;window_id=[long]$request.window_id;pid=[int]$request.pid;process_started=$processStarted;
                rows=$grid.Current.RowCount;columns=$grid.Current.ColumnCount;cells=@($cells);truncated=($rowEnd -lt $grid.Current.RowCount -or $columnEnd -lt $grid.Current.ColumnCount -or $remaining -le 0 -or $contentLimited);
                verification='uia_grid_readback';effect_executed=$false}
            [Console]::Out.Write(($answer | ConvertTo-Json -Depth 6 -Compress)); exit 0
        }
        if ($request.operation -eq 'set_state') {
            Assert-StateTarget $element
            $before = Get-PatternState $element
            $pattern = $null
            switch -CaseSensitive ($request.pattern) {
                'Value' {
                    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern) -or $pattern.Current.IsReadOnly) { throw 'ValuePattern no permite escritura.' }
                    if (-not [String]::Equals($pattern.Current.Value,[string]$request.state,[StringComparison]::Ordinal)) { Assert-StateTarget $element; $effectStarted=$true; $pattern.SetValue([string]$request.state) }
                    $actual=[string]$pattern.Current.Value
                    $matchesState=[String]::Equals($actual,[string]$request.state,[StringComparison]::Ordinal)
                    $sha=[Security.Cryptography.SHA256]::Create()
                    try { $valueHash=[BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($actual))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
                }
                'Toggle' {
                    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) { throw 'TogglePattern no disponible.' }
                    $desired = if ($request.state) { 'On' } else { 'Off' }
                    # TogglePattern has no SetState; bound tri-state cycling and read each transition.
                    for ($attempt=0; $pattern.Current.ToggleState.ToString() -cne $desired -and $attempt -lt 3; $attempt++) {
                        Assert-StateTarget $element; $effectStarted=$true; $pattern.Toggle()
                    }
                    $matchesState = $pattern.Current.ToggleState.ToString() -ceq $desired
                }
                'ExpandCollapse' {
                    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) { throw 'ExpandCollapsePattern no disponible.' }
                    $desired = if ($request.state -eq 'expanded') { 'Expanded' } else { 'Collapsed' }
                    if ($pattern.Current.ExpandCollapseState.ToString() -cne $desired) {
                        Assert-StateTarget $element; $effectStarted=$true
                        if ($request.state -eq 'expanded') { $pattern.Expand() } else { $pattern.Collapse() }
                    }
                    $matchesState = $pattern.Current.ExpandCollapseState.ToString() -ceq $desired
                }
                'SelectionItem' {
                    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { throw 'SelectionItemPattern no disponible.' }
                    if ($pattern.Current.IsSelected -ne [bool]$request.state) {
                        Assert-StateTarget $element; $effectStarted=$true
                        if ($request.state) { $pattern.Select() } else { $pattern.RemoveFromSelection() }
                    }
                    $matchesState = $pattern.Current.IsSelected -eq [bool]$request.state
                }
                'RangeValue' {
                    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern, [ref]$pattern) -or $pattern.Current.IsReadOnly) { throw 'RangeValuePattern no permite escritura.' }
                    $desired=[double]$request.state
                    if ($desired -lt $pattern.Current.Minimum -or $desired -gt $pattern.Current.Maximum) { throw 'Valor fuera del rango observado.' }
                    if ($pattern.Current.Value -ne $desired) { Assert-StateTarget $element; $effectStarted=$true; $pattern.SetValue($desired) }
                    $matchesState = $pattern.Current.Value -eq $desired
                }
                'Scroll' {
                    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern, [ref]$pattern)) { throw 'ScrollPattern no disponible.' }
                    Assert-StateTarget $element; $effectStarted=$true
                    $pattern.SetScrollPercent([double]$request.state.horizontal,[double]$request.state.vertical)
                    $matchesState = ($request.state.horizontal -eq -1 -or [Math]::Abs($pattern.Current.HorizontalScrollPercent-$request.state.horizontal) -le 0.01) -and
                                    ($request.state.vertical -eq -1 -or [Math]::Abs($pattern.Current.VerticalScrollPercent-$request.state.vertical) -le 0.01)
                }
                default { throw 'Patrón UIA no permitido.' }
            }
            Assert-StateTarget $element
            if (-not $matchesState) { throw 'El estado leído no coincide con el objetivo solicitado.' }
            $answer = @{success=$true;window_id=[long]$request.window_id;pid=[int]$request.pid;control_id=$request.control_id;
                process_started=$processStarted;pattern=$request.pattern;before=$before;after=(Get-PatternState $element);
                effect_executed=$effectStarted;verification='uia_state_readback';postconditions_passed=$true}
            if ($request.pattern -eq 'Value') { $answer.value_sha256=$valueHash; $answer.value_length=$actual.Length; $answer.verification='uia_value_readback' }
            [Console]::Out.Write(($answer | ConvertTo-Json -Depth 8 -Compress)); exit 0
        }
        if ($request.operation -eq 'invoke') {
            if ($root.Current.Name -cne $request.expected_title -or $element.Current.Name -cne $request.expected_name) { throw 'La ventana o el control cambió antes de la acción.' }
            if ($element.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button) { throw 'El control observado ya no es un botón.' }
            if ([AxxUiNative]::GetForegroundWindow().ToInt64() -ne [long]$request.window_id) { throw 'La aplicación perdió el foco antes de pulsar.' }
            $pattern = $null
            if (-not $element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { throw 'El botón no ofrece InvokePattern.' }
            $effectStarted = $true
            $pattern.Invoke()
            $answer = [ordered]@{ success = $true; window_id = [long]$request.window_id; pid = [int]$request.pid;
                control_id = [string]$request.control_id; verification = 'uia_invoke_acknowledged' }
            [Console]::Out.Write(($answer | ConvertTo-Json -Depth 4 -Compress))
            exit 0
        }
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
            throw 'El control no ofrece ValuePattern; la acción no se ejecutó.'
        }
        if ($pattern.Current.IsReadOnly) { throw 'El control es de solo lectura.' }
        if ($element.Current.IsPassword) { throw 'No se escriben controles protegidos.' }
        if ($request.expected_title -and $root.Current.Name -cne $request.expected_title) { throw 'Cambió la pestaña o el título aprobado.' }
        if (($request.operation -eq 'set_value' -and [AxxUiNative]::GetForegroundWindow().ToInt64() -ne [long]$request.window_id) -or
            $root.Current.ProcessId -ne [int]$request.pid) { throw 'La ventana perdió el foco o cambió antes del efecto.' }
        if ($request.operation -eq 'set_value') { $effectStarted = $true; $pattern.SetValue([string]$request.value) }
        $actual = [string]$pattern.Current.Value
        $expectedBytes = [System.Text.UTF8Encoding]::new($false).GetBytes([string]$request.value)
        $actualBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($actual)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $expectedHash = [BitConverter]::ToString($sha.ComputeHash($expectedBytes)).Replace('-', '').ToLowerInvariant()
            $actualHash = [BitConverter]::ToString($sha.ComputeHash($actualBytes)).Replace('-', '').ToLowerInvariant()
        } finally { $sha.Dispose() }
        $answer = [ordered]@{ success = ($expectedHash -eq $actualHash); window_id = [long]$request.window_id;
            pid = [int]$request.pid; control_id = [string]$request.control_id;
            value_sha256 = $actualHash; value_length = $actual.Length; verification = 'uia_value_readback' }
        if (-not $answer.success) { throw 'La lectura posterior no coincide con el texto solicitado.' }
    }
    $answer['process_started'] = $processStarted
    $focusedElement = [System.Windows.Automation.AutomationElement]::FocusedElement
    $answer['focused_control_id'] = if ($focusedElement -and $focusedElement.Current.ProcessId -eq [int]$request.pid) { Get-ControlToken $focusedElement ([long]$request.window_id) ([int]$request.pid) } else { $null }
    [Console]::Out.Write(($answer | ConvertTo-Json -Depth 8 -Compress))
} catch {
    [Console]::Out.Write((@{success=$false;error=$_.Exception.Message;effect_started=$effectStarted} | ConvertTo-Json -Compress))
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
