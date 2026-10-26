using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Automation;
using System.Windows.Input;
using System.Windows.Threading;

// Disposable test window. No global input hooks, external files, or hidden
// automation endpoint: mutations must arrive through Axx's real UIA/input path.
class ComputerUse {
    [STAThread]
    static void Main() {
        var app = new Application();
        var window = new Window {
            Title = "Axx Computer Use Acceptance", Width = 470, Height = 300,
            Left = 100, Top = 100, ResizeMode = ResizeMode.CanResize
        };
        AutomationProperties.SetAutomationId(window, "axx-computer-use-fixture");
        var panel = new StackPanel { Margin = new Thickness(20) };
        panel.Children.Add(new TextBlock {
            Text = "Disposable acceptance fixture", FontSize = 18,
            Margin = new Thickness(0, 0, 0, 14)
        });
        var enabled = new CheckBox { Content = "Enabled", Margin = new Thickness(0, 0, 0, 14) };
        AutomationProperties.SetAutomationId(enabled, "enabled");
        panel.Children.Add(enabled);
        var editor = new TextBox { Text = "Original", Height = 40, FontSize = 16 };
        AutomationProperties.SetAutomationId(editor, "editor");
        AutomationProperties.SetName(editor, "Editor");
        panel.Children.Add(editor);
        var status = new TextBlock { Text = "Ready", Margin = new Thickness(0, 14, 0, 0) };
        AutomationProperties.SetAutomationId(status, "status");
        enabled.Checked += (sender, args) => status.Text = "Enabled checked";
        enabled.Unchecked += (sender, args) => status.Text = "Enabled unchecked";
        panel.Children.Add(status);
        window.Content = panel;
        // Local widget focus on activation is normal app behavior, not SendInput.
        window.Activated += (sender, args) => window.Dispatcher.BeginInvoke(
            DispatcherPriority.Input, new Action(() => { editor.Focus(); Keyboard.Focus(editor); }));
        app.Run(window);
    }
}
