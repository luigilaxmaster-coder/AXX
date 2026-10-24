using System;
using System.IO;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;

public class SlowBox : TextBox {
    protected override AutomationPeer OnCreateAutomationPeer() { return new SlowPeer(this); }
}
public class SlowPeer : TextBoxAutomationPeer, IValueProvider {
    static int writes;
    public SlowPeer(SlowBox owner) : base(owner) {}
    public override object GetPattern(PatternInterface pattern) {
        return pattern == PatternInterface.Value ? this : base.GetPattern(pattern);
    }
    bool IValueProvider.IsReadOnly { get { return false; } }
    string IValueProvider.Value { get { return ((SlowBox)Owner).Text; } }
    void IValueProvider.SetValue(string value) {
        Thread.Sleep(12000);
        ((SlowBox)Owner).Text = value;
        File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "slow-control-writes.txt"), (++writes).ToString());
    }
}
public class SlowControl {
    [STAThread] public static void Main() {
        var app = new Application();
        var box = new SlowBox { Margin = new Thickness(20), Text = "initial", AcceptsReturn = true };
        AutomationProperties.SetAutomationId(box, "axx-delayed-value");
        app.Run(new Window { Title = "Axx UIA delayed effect fixture", Width = 500, Height = 220, Content = box });
    }
}
