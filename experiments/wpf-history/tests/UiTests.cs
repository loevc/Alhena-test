using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Alhena
{
    public static class UiTests
    {
        [STAThread]
        public static int Main(string[] args)
        {
            var app = new Application();
            var window = new MainWindow(File.ReadAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "fixture-path.txt")));
            int exit = 1;
            app.DispatcherUnhandledException += delegate(object sender, System.Windows.Threading.DispatcherUnhandledExceptionEventArgs e) { Console.Error.WriteLine(e.Exception); e.Handled = true; app.Shutdown(1); };
            window.Loaded += async delegate {
                try {
                    var history = (DataGrid)((FrameworkElement)window.Content).FindName("History");
                    var files = (ListBox)((FrameworkElement)window.Content).FindName("Files");
                    var diff = (DataGrid)((FrameworkElement)window.Content).FindName("Diff");
                    await Wait(() => diff.Items.Count > 0);
                    Console.WriteLine("PASS UI: commits={0}, files={1}, diffRows={2}", history.Items.Count, files.Items.Count, diff.Items.Count);
                    var search = (TextBox)((FrameworkElement)window.Content).FindName("Search");
                    search.Text = "no matching commits here";
                    await Task.Delay(100);
                    if (history.Items.Count != 0 || files.Items.Count != 0 || diff.Items.Count != 0) throw new Exception("Stale selection after search");
                    search.Text = "";
                    var tree = (TreeView)((FrameworkElement)window.Content).FindName("Branches");
                    ((TreeViewItem)((TreeViewItem)tree.Items[1]).Items[0]).IsSelected = true;
                    await Wait(() => history.Items.Count == 2 && diff.Items.Count > 0);
                    Console.WriteLine("PASS UI: search and branch filtering");
                    ((TreeViewItem)tree.Items[0]).IsSelected = true;
                    await Wait(() => history.Items.Count == 6 && diff.Items.Count > 0);
                    history.SelectedIndex = 2;
                    await Wait(() => files.Items.Count == 1 && ((FileChange)files.Items[0]).Path == "中文 file.txt" && diff.Items.Count > 0);
                    Console.WriteLine("PASS UI: selecting merge loads first-parent diff");
                    window.UpdateLayout();
                    var bitmap = new RenderTargetBitmap((int)window.ActualWidth, (int)window.ActualHeight, 96, 96, PixelFormats.Pbgra32);
                    bitmap.Render(window);
                    var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
                    using (var stream = File.Create(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "preview.png"))) encoder.Save(stream);
                    exit = 0;
                } catch (Exception ex) { Console.Error.WriteLine(ex); }
                finally { app.Shutdown(exit); }
            };
            app.Run(window);
            return exit;
        }
        static async Task Wait(Func<bool> predicate)
        {
            for (int i = 0; i < 80; i++) { if (predicate()) return; await Task.Delay(100); }
            throw new Exception("UI query timed out");
        }
    }
}

