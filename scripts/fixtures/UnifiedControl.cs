using System;
using System.Windows;
using System.Windows.Controls;

// Disposable native UIA target; never opens user files or sends external effects.
class UnifiedControl {
    [STAThread]
    static void Main() {
        var application = new Application();
        var form = new Window { Title = "Axx unified execution fixture", Width = 500, Height = 280 };
        var panel = new StackPanel { Margin = new Thickness(20) };
        var status = new TextBlock { Name = "status", Text = "Pendiente" };
        var confirm = new Button { Name = "confirm", Content = "Confirmar", Height = 35 };
        confirm.Click += (sender, args) => status.Text = "Confirmado";
        panel.Children.Add(confirm);
        panel.Children.Add(status);
        panel.Children.Add(new Button { Content = "Duplicado", Height = 35 });
        panel.Children.Add(new Button { Content = "Duplicado", Height = 35 });
        panel.Children.Add(new TextBox { Name = "editor", Text = "Texto de ensayo", Height = 35 });
        form.Content = panel;
        application.Run(form);
    }
}
