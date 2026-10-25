$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$effectStarted = $false

try {
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class AxxUiNative { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); }'
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $request -or $request.operation -notin @('inspect', 'read_content', 'locate_edit', 'set_value', 'invoke', 'check_value', 'locate_folder', 'scrape_app')) {
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

    function Get-ControlToken($element, [long]$windowId, [int]$processId) {
        $runtimeId = $element.GetRuntimeId()
        $identity = "$windowId`:$processId`:$($runtimeId -join ',')"
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
        $dummy = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$dummy)) { $patterns.Add('Invoke') }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$dummy)) { $patterns.Add('Value') }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$dummy)) { $patterns.Add('Toggle') }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$dummy)) { $patterns.Add('SelectionItem') }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$dummy)) { $patterns.Add('ExpandCollapse') }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern, [ref]$dummy)) { $patterns.Add('Scroll') }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$dummy)) { $patterns.Add('Text') }
        return @($patterns)
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
            truncated=($edits.Count -gt 64);verification='visible_edit_controls_observed'} | ConvertTo-Json -Depth 4 -Compress))
        exit 0
    }

    if ($request.operation -in @('inspect', 'read_content', 'scrape_app')) {
        $reading = $request.operation -eq 'read_content'
        $scraping = $request.operation -eq 'scrape_app'
        $remaining = 24000
        $contentLimited = $false
        $windowTitle = $root.Current.Name
        if ($reading -and $windowTitle -cne $request.expected_title) { throw 'Cambió la ventana o página desde la preparación. Vuelve a seleccionarla y aprobar la lectura.' }
        $scope = $root
        $browserProcess = [Diagnostics.Process]::GetProcessById([int]$request.pid).ProcessName -in @('chrome','msedge','brave','firefox','opera','vivaldi')
        if ($reading -and $browserProcess) {
            $documents = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document))
            $matching = @($documents | Where-Object { -not $_.Current.IsOffscreen -and $_.Current.Name -and
                ($windowTitle -ceq $_.Current.Name -or $windowTitle.StartsWith($_.Current.Name + ' - ', [StringComparison]::Ordinal) -or
                 $windowTitle.StartsWith($_.Current.Name + ' — ', [StringComparison]::Ordinal)) })
            if ($matching.Count -ne 1) { throw 'No se pudo identificar una única página activa. Activa la pestaña que quieres leer y vuelve a intentarlo.' }
            $scope = $matching[0]
        }
        $items = [System.Collections.Generic.List[object]]::new()
        $all = $scope.FindAll([System.Windows.Automation.TreeScope]::Subtree,
            [System.Windows.Automation.Condition]::TrueCondition)
        $protected = $scope.FindFirst([System.Windows.Automation.TreeScope]::Subtree,
            [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::IsPasswordProperty, $true))
        $maxAllowed = if ($scraping) { 1000 } elseif ($reading) { 1000 } else { 250 }
        $count = [Math]::Min($all.Count, $maxAllowed)
        for ($i = 0; $i -lt $count; $i++) {
            $item = $all.Item($i)
            if ($item.Current.IsPassword) { continue }
            $controlType = $item.Current.ControlType.ProgrammaticName
            $name = ''
            if (($reading -and -not $item.Current.IsOffscreen) -or $controlType -in @('ControlType.Button', 'ControlType.CheckBox', 'ControlType.RadioButton',
                'ControlType.MenuItem', 'ControlType.ComboBox', 'ControlType.TabItem', 'ControlType.ToolBar')) {
                $name = [string]$item.Current.Name
                if ($name.Length -gt 200) { $name = $name.Substring(0, 200) }
            }
            $valuePattern = $null
            $hasValuePattern = $item.TryGetCurrentPattern(
                [System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern)
            $text = ''; $value = ''
            if ($reading -and -not $item.Current.IsOffscreen -and $remaining -gt 0) {
                if ($hasValuePattern) {
                    $value = [string]$valuePattern.Current.Value
                    if ($value.Length -gt [Math]::Min(8192, $remaining)) { $contentLimited = $true }
                    $value = $value.Substring(0, [Math]::Min($value.Length, [Math]::Min(8192, $remaining)))
                    $remaining -= $value.Length
                }
                if ($controlType -in @('ControlType.Text', 'ControlType.Hyperlink') -and $remaining -gt 0) {
                    $text = [string]$item.Current.Name
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
            $rect = $item.Current.BoundingRectangle
            $controlEntry = [ordered]@{
                control_id = (Get-ControlToken $item ([long]$request.window_id) ([int]$request.pid))
                automation_id = [string]$item.Current.AutomationId
                control_type = $controlType
                name = $name
                class_name = [string]$item.Current.ClassName
                enabled = [bool]$item.Current.IsEnabled
                offscreen = [bool]$item.Current.IsOffscreen
                supports_value_pattern = [bool]$hasValuePattern
                read_only = $(if ($hasValuePattern) { [bool]$valuePattern.Current.IsReadOnly } else { $true })
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
        if ($request.operation -in @('set_value','invoke') -and [AxxUiNative]::GetForegroundWindow().ToInt64() -ne [long]$request.window_id) {
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
    [Console]::Out.Write(($answer | ConvertTo-Json -Depth 8 -Compress))
} catch {
    [Console]::Out.Write((@{success=$false;error=$_.Exception.Message;effect_started=$effectStarted} | ConvertTo-Json -Compress))
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
