$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

try {
    $request = [Console]::In.ReadLine() | ConvertFrom-Json -ErrorAction Stop
    if ($request.window_id -le 0 -or $request.pid -le 0 -or $request.max_seconds -lt 1 -or
        $request.max_seconds -gt 300 -or $request.max_events -lt 1 -or $request.max_events -gt 500) {
        throw 'Invalid observation bounds.'
    }
    $parentProcess = [Diagnostics.Process]::GetProcessById([int]$request.parent_pid)
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    # UIA callbacks run on native threads without a PowerShell runspace.
    Add-Type -ReferencedAssemblies UIAutomationClient,UIAutomationTypes,WindowsBase -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Windows.Automation;
public sealed class AxxObserver : IDisposable {
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    readonly AutomationElement root;
    readonly IntPtr hwnd;
    readonly int pid, maximum;
    readonly int[] rootId;
    readonly object gate = new object();
    readonly AutomationEventHandler eventHandler;
    readonly AutomationPropertyChangedEventHandler propertyHandler;
    readonly List<AutomationEvent> registered = new List<AutomationEvent>();
    bool propertiesRegistered, disposed;
    int count;
    public readonly ConcurrentQueue<Dictionary<string, object>> Queue = new ConcurrentQueue<Dictionary<string, object>>();
    public bool Full { get { lock(gate) { return count >= maximum; } } }
    static string Bound(string s) { return s == null ? "" : s.Substring(0, Math.Min(s.Length, 200)); }
    static bool Same(int[] a, int[] b) {
        if (a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; ++i) if (a[i] != b[i]) return false;
        return true;
    }
    public bool Alive() {
        try {
            uint owner;
            GetWindowThreadProcessId(hwnd, out owner);
            return IsWindow(hwnd) && owner == pid && Same(rootId, AutomationElement.FromHandle(hwnd).GetRuntimeId());
        } catch { return false; }
    }
    bool InScope(AutomationElement element) {
        var current = element;
        for (int i = 0; i < 64 && current != null; ++i) {
            if (Same(rootId, current.GetRuntimeId())) return true;
            current = TreeWalker.RawViewWalker.GetParent(current);
        }
        return false;
    }
    void Capture(object sender, string kind, object state) {
        lock(gate) {
            if (disposed || count >= maximum) return;
            try {
                var element = sender as AutomationElement;
                if (element == null || element.Current.ProcessId != pid || element.Current.IsPassword || !InScope(element)) return;
                var info = element.Current;
                var type = info.ControlType;
                string name = "";
                if (type == ControlType.Button || type == ControlType.CheckBox || type == ControlType.RadioButton || type == ControlType.MenuItem)
                    name = Bound(info.Name);
                var runtimeId = element.GetRuntimeId();
                if (runtimeId.Length == 0 || runtimeId.Length > 32) return;
                var selector = new Dictionary<string, object> {
                    {"runtime_id", runtimeId}, {"automation_id", Bound(info.AutomationId)},
                    {"control_type", type.ProgrammaticName}, {"name", name}, {"is_password", false}
                };
                Queue.Enqueue(new Dictionary<string, object> {
                    {"type", "event"}, {"kind", kind}, {"window_id", hwnd.ToInt64()}, {"pid", pid},
                    {"selector", selector}, {"state", state}
                });
                count++;
            } catch { /* Provider disappeared; never broaden observation scope. */ }
        }
    }
    void OnEvent(object sender, AutomationEventArgs e) {
        string kind = e.EventId == InvokePattern.InvokedEvent ? "invoke" :
            e.EventId == SelectionItemPattern.ElementSelectedEvent ? "selection" :
            e.EventId == SelectionItemPattern.ElementAddedToSelectionEvent ? "selection_added" : "selection_removed";
        Capture(sender, kind, null);
    }
    void OnProperty(object sender, AutomationPropertyChangedEventArgs e) {
        try {
            if (e.Property == TogglePattern.ToggleStateProperty) Capture(sender, "toggle", Convert.ToInt32(e.NewValue));
            else if (e.Property == ExpandCollapsePattern.ExpandCollapseStateProperty) Capture(sender, "expand_collapse", Convert.ToInt32(e.NewValue));
            else if (e.Property == AutomationElement.IsEnabledProperty) Capture(sender, "enabled", e.NewValue is bool ? e.NewValue : null);
            else if (e.Property == AutomationElement.IsOffscreenProperty) Capture(sender, "offscreen", e.NewValue is bool ? e.NewValue : null);
        } catch { /* Ignore unsupported property values from a provider. */ }
    }
    public AxxObserver(long windowId, int processId, int maxEvents) {
        hwnd = new IntPtr(windowId); pid = processId; maximum = maxEvents;
        root = AutomationElement.FromHandle(hwnd);
        if (root == null || root.Current.ProcessId != pid) throw new InvalidOperationException("Window identity lost.");
        rootId = root.GetRuntimeId();
        eventHandler = OnEvent; propertyHandler = OnProperty;
        try {
            foreach (var ev in new [] {InvokePattern.InvokedEvent, SelectionItemPattern.ElementSelectedEvent,
                SelectionItemPattern.ElementAddedToSelectionEvent, SelectionItemPattern.ElementRemovedFromSelectionEvent}) {
                Automation.AddAutomationEventHandler(ev, root, TreeScope.Subtree, eventHandler);
                registered.Add(ev);
            }
            Automation.AddAutomationPropertyChangedEventHandler(root, TreeScope.Subtree, propertyHandler,
                TogglePattern.ToggleStateProperty, ExpandCollapsePattern.ExpandCollapseStateProperty,
                AutomationElement.IsEnabledProperty, AutomationElement.IsOffscreenProperty);
            propertiesRegistered = true;
        } catch { Dispose(); throw; }
    }
    public Dictionary<string, object> Next() {
        Dictionary<string, object> item;
        return Queue.TryDequeue(out item) ? item : null;
    }
    public void Dispose() {
        lock(gate) { disposed = true; }
        foreach (var ev in registered) {
            try { Automation.RemoveAutomationEventHandler(ev, root, eventHandler); } catch { }
        }
        if (propertiesRegistered) {
            try { Automation.RemoveAutomationPropertyChangedEventHandler(root, propertyHandler); } catch { }
        }
    }
}
'@
    $observer = [AxxObserver]::new([long]$request.window_id, [int]$request.pid, [int]$request.max_events)
    [Console]::Out.WriteLine('{"type":"ready"}')
    [Console]::Out.Flush()
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $reason = 'time_limit'
    try {
        while ($watch.Elapsed.TotalSeconds -lt $request.max_seconds) {
            if ($parentProcess.HasExited) { $reason = 'parent_exit'; break }
            if (-not $observer.Alive()) { $reason = 'window_lost'; break }
            while ($null -ne ($item = $observer.Next())) {
                [Console]::Out.WriteLine(($item | ConvertTo-Json -Depth 6 -Compress))
            }
            [Console]::Out.Flush()
            if ($observer.Full) { $reason = 'event_limit'; break }
            Start-Sleep -Milliseconds 100
        }
    } finally { $observer.Dispose() }
    [Console]::Out.WriteLine((@{type='end'; reason=$reason} | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
} catch {
    [Console]::Out.WriteLine('{"type":"end","reason":"observer_error"}')
    [Console]::Out.Flush()
    exit 2
}
