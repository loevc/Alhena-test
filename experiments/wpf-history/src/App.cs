using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using System.Threading.Tasks;

namespace Alhena
{
    public sealed class GraphCell : FrameworkElement
    {
        static readonly Brush[] Palette = { Brushes.MediumPurple, Brushes.CornflowerBlue, Brushes.MediumSeaGreen, Brushes.SandyBrown, Brushes.HotPink, Brushes.Turquoise };
        public GraphCell() { DataContextChanged += delegate { InvalidateVisual(); }; }
        protected override void OnRender(DrawingContext dc)
        {
            var commit = DataContext as Commit;
            if (commit == null || commit.Graph == null) return;
            var row = commit.Graph; double mid = ActualHeight / 2;
            foreach (var edge in row.Edges) {
                double x1 = 15 + edge.From * 18, x2 = 15 + edge.To * 18;
                double y1 = edge.StartsAtNode ? mid : 0, y2 = edge.EndsAtNode ? mid : ActualHeight;
                var geometry = new StreamGeometry();
                using (var c = geometry.Open()) {
                    c.BeginFigure(new Point(x1, y1), false, false);
                    c.BezierTo(new Point(x1, (y1+y2)/2), new Point(x2, (y1+y2)/2), new Point(x2,y2), true, false);
                }
                dc.DrawGeometry(null, new Pen(Palette[edge.Color % Palette.Length], 1.6), geometry);
            }
            dc.DrawEllipse(Palette[row.Color % Palette.Length], new Pen(new SolidColorBrush(Color.FromRgb(30,31,34)), 2), new Point(15 + row.Lane * 18, mid), 4.5, 4.5);
        }
    }
    public sealed class DiffRow
    {
        public string OldNumber { get; set; }
        public string NewNumber { get; set; }
        public string OldText { get; set; }
        public string NewText { get; set; }
        public Brush OldBackground { get; set; }
        public Brush NewBackground { get; set; }
    }
    public sealed class MainWindow : Window
    {
        const string Layout = @"
<Grid xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml'>
 <Grid.Resources>
  <SolidColorBrush x:Key='Panel' Color='#25262B'/>
  <Style TargetType='Button'><Setter Property='Background' Value='#363942'/><Setter Property='Foreground' Value='#F0F1F4'/><Setter Property='BorderBrush' Value='#494D59'/><Setter Property='Padding' Value='14,6'/><Setter Property='Margin' Value='0,0,8,0'/><Setter Property='Template'><Setter.Value><ControlTemplate TargetType='Button'><Border x:Name='Frame' Background='{TemplateBinding Background}' BorderBrush='{TemplateBinding BorderBrush}' BorderThickness='1' CornerRadius='3' Padding='{TemplateBinding Padding}'><ContentPresenter HorizontalAlignment='Center' VerticalAlignment='Center'/></Border><ControlTemplate.Triggers><Trigger Property='IsMouseOver' Value='True'><Setter TargetName='Frame' Property='Background' Value='#4B4263'/></Trigger><Trigger Property='IsEnabled' Value='False'><Setter Property='Opacity' Value='0.45'/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter></Style>
  <Style TargetType='TextBox'><Setter Property='Background' Value='#1E1F22'/><Setter Property='Foreground' Value='#DFE1E5'/><Setter Property='BorderBrush' Value='#454852'/><Setter Property='Padding' Value='8,5'/><Setter Property='CaretBrush' Value='White'/></Style>
  <Style TargetType='TreeView'><Setter Property='Background' Value='{StaticResource Panel}'/><Setter Property='Foreground' Value='#DFE1E5'/><Setter Property='BorderThickness' Value='0'/><Setter Property='Padding' Value='10'/></Style>
  <Style TargetType='TreeViewItem'><Setter Property='Foreground' Value='#DFE1E5'/><Setter Property='Padding' Value='2,5'/></Style>
  <Style TargetType='DataGrid'><Setter Property='Background' Value='#1E1F22'/><Setter Property='Foreground' Value='#DFE1E5'/><Setter Property='BorderThickness' Value='0'/><Setter Property='RowBackground' Value='#1E1F22'/><Setter Property='AlternatingRowBackground' Value='#212226'/><Setter Property='GridLinesVisibility' Value='None'/><Setter Property='HeadersVisibility' Value='Column'/><Setter Property='AutoGenerateColumns' Value='False'/><Setter Property='IsReadOnly' Value='True'/><Setter Property='CanUserAddRows' Value='False'/><Setter Property='CanUserDeleteRows' Value='False'/><Setter Property='CanUserSortColumns' Value='False'/><Setter Property='CanUserReorderColumns' Value='False'/><Setter Property='SelectionMode' Value='Single'/><Setter Property='SelectionUnit' Value='FullRow'/><Setter Property='EnableRowVirtualization' Value='True'/><Setter Property='RowHeight' Value='30'/></Style>
  <Style TargetType='DataGridColumnHeader'><Setter Property='Background' Value='#2B2D33'/><Setter Property='Foreground' Value='#A9ADBA'/><Setter Property='Padding' Value='8'/><Setter Property='BorderThickness' Value='0,0,0,1'/><Setter Property='BorderBrush' Value='#393B40'/></Style>
  <Style TargetType='DataGridCell'><Setter Property='BorderThickness' Value='0'/><Setter Property='Padding' Value='0'/><Style.Triggers><Trigger Property='IsSelected' Value='True'><Setter Property='Background' Value='#314365'/><Setter Property='Foreground' Value='White'/></Trigger></Style.Triggers></Style>
  <Style TargetType='GridSplitter'><Setter Property='Background' Value='#383A42'/></Style>
 </Grid.Resources>
 <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='*'/><RowDefinition Height='Auto'/></Grid.RowDefinitions>
 <Border Background='#2B2D33' Padding='16,12'><DockPanel>
  <StackPanel DockPanel.Dock='Left' Orientation='Horizontal'><TextBlock Text='ALHENA' FontWeight='Bold' FontSize='18' Foreground='#B7A0F8' Margin='0,0,24,0' VerticalAlignment='Center'/><Button x:Name='Open' Content='打开仓库…'/><Button x:Name='Refresh' Content='刷新  F5'/></StackPanel>
  <TextBox x:Name='RepoPath' ToolTip='输入仓库目录并按 Enter' VerticalContentAlignment='Center'/>
 </DockPanel></Border>
 <Grid Grid.Row='1'>
  <Grid.ColumnDefinitions><ColumnDefinition Width='215' MinWidth='150'/><ColumnDefinition Width='5'/><ColumnDefinition Width='*' MinWidth='500'/></Grid.ColumnDefinitions>
  <DockPanel Background='{StaticResource Panel}'><TextBlock DockPanel.Dock='Top' Text='仓库 / 分支' Foreground='#A9ADBA' Margin='16,14,0,4'/><TreeView x:Name='Branches'/></DockPanel>
  <GridSplitter Grid.Column='1' HorizontalAlignment='Stretch'/>
  <Grid Grid.Column='2'>
   <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='3*' MinHeight='120'/><RowDefinition Height='5'/><RowDefinition Height='2*' MinHeight='180'/></Grid.RowDefinitions>
   <DockPanel Background='#25262B' LastChildFill='True' Margin='0'>
    <TextBlock DockPanel.Dock='Left' Text='历史记录' VerticalAlignment='Center' Margin='12,0,0,0' Foreground='#A9ADBA'/>
    <Button x:Name='More' DockPanel.Dock='Right' Content='加载更多' Margin='8,8,12,8'/><TextBox x:Name='Search' ToolTip='搜索已加载提交的标题、作者、哈希和引用' Margin='12,8,0,8' Width='340' HorizontalAlignment='Left'/>
   </DockPanel>
   <DataGrid x:Name='History' Grid.Row='1'/>
   <GridSplitter Grid.Row='2' HorizontalAlignment='Stretch'/>
   <Grid Grid.Row='3'>
    <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='*'/></Grid.RowDefinitions>
    <Border Background='#2B2D33' Padding='12,8'><TextBlock x:Name='Details' Text='选择提交以查看详情' TextTrimming='CharacterEllipsis' ToolTip='{Binding Text, RelativeSource={RelativeSource Self}}'/></Border>
    <Grid Grid.Row='1'>
     <Grid.ColumnDefinitions><ColumnDefinition Width='260' MinWidth='120'/><ColumnDefinition Width='5'/><ColumnDefinition Width='*'/></Grid.ColumnDefinitions>
     <DockPanel Background='#25262B'><TextBlock DockPanel.Dock='Top' Text='变更文件（合并提交对比第一父提交）' Foreground='#A9ADBA' FontSize='11' Margin='10,10,0,8'/><ListBox x:Name='Files' Background='#25262B' Foreground='#DFE1E5' BorderThickness='0' ScrollViewer.HorizontalScrollBarVisibility='Auto'/></DockPanel>
     <GridSplitter Grid.Column='1' HorizontalAlignment='Stretch'/><DataGrid x:Name='Diff' Grid.Column='2' RowHeight='22' FontFamily='Consolas' FontSize='12' SelectionMode='Extended'/>
    </Grid>
   </Grid>
  </Grid>
 </Grid>
 <Border Grid.Row='2' Background='#2B2D33' Padding='14,7'><TextBlock x:Name='Status' Foreground='#A9ADBA' Text='打开一个本地 Git 仓库开始浏览 · 当前版本只读取仓库'/></Border>
</Grid>";
        Grid content;
        DataGrid history, diff;
        TreeView branches;
        ListBox files;
        TextBox repoPath, search;
        TextBlock status, details;
        Button more;
        Git git;
        List<Commit> commits = new List<Commit>();
        string reference;
        int limit = 300, loadVersion, fileVersion, diffVersion;
        bool rebuilding;

        T Find<T>(string name) where T : class { return content.FindName(name) as T; }
        public MainWindow(string initial)
        {
            Title = "Alhena · Git"; Width = 1440; Height = 900; MinWidth = 1000; MinHeight = 640;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            Background = new SolidColorBrush(Color.FromRgb(30,31,34)); Foreground = Brushes.Gainsboro;
            FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI"); FontSize = 12;
            content = (Grid)XamlReader.Parse(Layout); Content = content;
            history = Find<DataGrid>("History"); diff = Find<DataGrid>("Diff"); branches = Find<TreeView>("Branches");
            files = Find<ListBox>("Files"); repoPath = Find<TextBox>("RepoPath"); search = Find<TextBox>("Search");
            status = Find<TextBlock>("Status"); details = Find<TextBlock>("Details"); more = Find<Button>("More");
            var factory = new FrameworkElementFactory(typeof(GraphCell));
            history.Columns.Add(new DataGridTemplateColumn { Header = "提交图", Width = 110, CellTemplate = new DataTemplate { VisualTree = factory } });
            AddColumn(history, "提交信息", "Subject", new DataGridLength(1, DataGridLengthUnitType.Star), null);
            AddColumn(history, "引用", "Refs", 200, null); AddColumn(history, "作者", "Author", 120, null);
            AddColumn(history, "哈希", "ShortHash", 85, null); AddColumn(history, "时间", "Date", 145, null);
            AddColumn(diff, "行", "OldNumber", 48, "OldBackground"); AddColumn(diff, "之前", "OldText", new DataGridLength(1, DataGridLengthUnitType.Star), "OldBackground");
            AddColumn(diff, "行", "NewNumber", 48, "NewBackground"); AddColumn(diff, "之后", "NewText", new DataGridLength(1, DataGridLengthUnitType.Star), "NewBackground");
            Find<Button>("Open").Click += async delegate {
                using (var dialog = new System.Windows.Forms.FolderBrowserDialog { Description = "选择本地 Git 仓库" }) {
                    if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK) await Open(dialog.SelectedPath);
                }
            };
            Find<Button>("Refresh").Click += async delegate { await Reload(true); };
            more.Click += async delegate { limit += 300; await Reload(false); };
            repoPath.KeyDown += async delegate(object sender, KeyEventArgs e) { if (e.Key == Key.Enter) await Open(repoPath.Text); };
            PreviewKeyDown += async delegate(object sender, KeyEventArgs e) { if (e.Key == Key.F5) { e.Handled = true; await Reload(true); } };
            search.TextChanged += delegate { Filter(); };
            branches.SelectedItemChanged += async delegate {
                if (rebuilding) return;
                var item = branches.SelectedItem as TreeViewItem;
                if (item == null || !(item.Tag is Branch)) return;
                reference = ((Branch)item.Tag).Ref; limit = 300; await Reload(false);
            };
            history.SelectionChanged += async delegate { await SelectCommit(); };
            files.SelectionChanged += async delegate { await SelectFile(); };
            Loaded += async delegate { if (!String.IsNullOrWhiteSpace(initial)) await Open(initial); };
        }
        static void AddColumn(DataGrid grid, string title, string property, DataGridLength width, string background)
        {
            var style = new Style(typeof(TextBlock));
            style.Setters.Add(new Setter(TextBlock.PaddingProperty, new Thickness(8, 3, 8, 0)));
            style.Setters.Add(new Setter(TextBlock.TextTrimmingProperty, TextTrimming.CharacterEllipsis));
            style.Setters.Add(new Setter(TextBlock.ToolTipProperty, new Binding(property)));
            if (background != null) style.Setters.Add(new Setter(TextBlock.BackgroundProperty, new Binding(background)));
            grid.Columns.Add(new DataGridTextColumn { Header = title, Binding = new Binding(property), Width = width, ElementStyle = style });
        }
        void Error(Exception ex) { status.Text = "查询失败：" + ex.Message; status.ToolTip = ex.ToString(); }
        async Task Open(string path)
        {
            int version = ++loadVersion;
            status.Text = "正在打开仓库…";
            try {
                var candidate = new Git(System.IO.Path.GetFullPath(path.Trim()));
                string root = (await candidate.Run("rev-parse", "--show-toplevel")).TrimEnd('\r','\n');
                if (version != loadVersion) return;
                git = new Git(root); reference = null; limit = 300; repoPath.Text = root;
                Title = System.IO.Path.GetFileName(root) + " — Alhena · Git";
                await Reload(true);
            } catch (Exception ex) { if (version == loadVersion) Error(ex); }
        }
        async Task Reload(bool refreshBranches)
        {
            if (git == null) return;
            int version = ++loadVersion; var source = git; string selectedRef = reference;
            ++fileVersion; ++diffVersion; files.ItemsSource = null; diff.ItemsSource = null;
            details.Text = "选择提交以查看详情"; status.Text = "正在读取提交关系…"; more.IsEnabled = false;
            try {
                var logTask = source.Log(selectedRef, limit);
                var branchTask = refreshBranches ? source.Branches() : Task.FromResult<List<Branch>>(null);
                await Task.WhenAll(logTask, branchTask);
                if (version != loadVersion) return;
                commits = logTask.Result;
                if (refreshBranches) {
                    rebuilding = true; branches.Items.Clear();
                    var all = new TreeViewItem { Header = "所有分支", Tag = new Branch(), IsSelected = selectedRef == null }; branches.Items.Add(all);
                    foreach (bool remote in new[] { false, true }) {
                        var group = new TreeViewItem { Header = remote ? "远程分支" : "本地分支", IsExpanded = true };
                        foreach (var branch in branchTask.Result.Where(b => b.Remote == remote)) group.Items.Add(new TreeViewItem { Header = branch.Label, Tag = branch, IsSelected = branch.Ref == selectedRef });
                        branches.Items.Add(group);
                    }
                    rebuilding = false;
                }
                history.Columns[0].Width = Math.Max(85, commits.Select(c => c.Graph.Width * 18 + 30).DefaultIfEmpty(85).Max());
                Filter();
                if (history.Items.Count > 0) history.SelectedIndex = 0;
                more.IsEnabled = commits.Count >= limit;
            } catch (Exception ex) { if (version == loadVersion) Error(ex); }
        }
        void Filter()
        {
            string query = search.Text.Trim();
            history.ItemsSource = commits.Where(c => query.Length == 0 || new[] { c.Subject, c.Author, c.Hash, c.Refs }.Any(s => s.IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0)).ToList();
            status.Text = commits.Count == 0 ? "仓库尚无提交" : String.Format("{0} 条已加载 · {1} 条匹配 · {2} · 搜索范围为已加载记录", commits.Count, history.Items.Count, reference ?? "所有分支");
        }
        async Task SelectCommit()
        {
            int version = ++fileVersion; ++diffVersion;
            files.ItemsSource = null; diff.ItemsSource = null;
            var commit = history.SelectedItem as Commit; var source = git;
            if (commit == null || source == null) { details.Text = "选择提交以查看详情"; return; }
            details.Text = commit.ShortHash + "  ·  " + commit.Author + "  ·  " + commit.Date + "  ·  " + commit.Subject;
            try {
                var changes = await source.Files(commit);
                if (version != fileVersion) return;
                files.ItemsSource = changes;
                if (changes.Count > 0) files.SelectedIndex = 0;
            } catch (Exception ex) { if (version == fileVersion) Error(ex); }
        }
        async Task SelectFile()
        {
            int version = ++diffVersion; diff.ItemsSource = null;
            var commit = history.SelectedItem as Commit; var file = files.SelectedItem as FileChange; var source = git;
            if (commit == null || file == null || source == null) return;
            try {
                string patch = await source.Patch(commit, file);
                if (version != diffVersion) return;
                diff.ItemsSource = ParsePatch(patch);
            } catch (Exception ex) { if (version == diffVersion) Error(ex); }
        }
        static List<DiffRow> ParsePatch(string patch)
        {
            var rows = new List<DiffRow>(); var removed = new List<string>(); var added = new List<string>();
            Brush red = new SolidColorBrush(Color.FromRgb(74,43,48)), green = new SolidColorBrush(Color.FromRgb(35,65,49));
            int oldLine = 0, newLine = 0; bool inHunk = false;
            Action flush = delegate {
                for (int i = 0; i < Math.Max(removed.Count, added.Count); i++) rows.Add(new DiffRow {
                    OldNumber = i < removed.Count ? (oldLine++).ToString() : "", NewNumber = i < added.Count ? (newLine++).ToString() : "",
                    OldText = i < removed.Count ? removed[i] : "", NewText = i < added.Count ? added[i] : "",
                    OldBackground = i < removed.Count ? red : Brushes.Transparent, NewBackground = i < added.Count ? green : Brushes.Transparent });
                removed.Clear(); added.Clear();
            };
            foreach (string raw in patch.Split('\n')) {
                string line = raw.TrimEnd('\r');
                if (line.StartsWith("@@ ", StringComparison.Ordinal)) {
                    flush(); var parts = line.Split(' ');
                    oldLine = Int32.Parse(parts[1].Substring(1).Split(',')[0]); newLine = Int32.Parse(parts[2].Substring(1).Split(',')[0]); inHunk = true;
                    rows.Add(new DiffRow { OldText = line, NewText = line });
                } else if (inHunk && line.StartsWith("-", StringComparison.Ordinal)) removed.Add(line.Substring(1));
                else if (inHunk && line.StartsWith("+", StringComparison.Ordinal)) added.Add(line.Substring(1));
                else {
                    flush();
                    if (inHunk && line.StartsWith(" ", StringComparison.Ordinal)) rows.Add(new DiffRow { OldNumber = (oldLine++).ToString(), NewNumber = (newLine++).ToString(), OldText = line.Substring(1), NewText = line.Substring(1) });
                    else if (line.Length > 0) rows.Add(new DiffRow { OldText = line, NewText = line });
                }
                if (rows.Count > 20000) { rows.Add(new DiffRow { OldText = "差异较大，预览仅显示前 20000 行", NewText = "差异较大，预览仅显示前 20000 行" }); break; }
            }
            flush();
            if (rows.Count == 0) rows.Add(new DiffRow { OldText = "无文本差异（可能仅文件名或权限变化）" });
            return rows;
        }
    }
    public static class App
    {
        [STAThread]
        public static void Main(string[] args)
        {
            var app = new Application();
            app.DispatcherUnhandledException += delegate(object sender, System.Windows.Threading.DispatcherUnhandledExceptionEventArgs e) {
                MessageBox.Show(e.Exception.Message, "Alhena", MessageBoxButton.OK, MessageBoxImage.Error); e.Handled = true;
            };
            app.Run(new MainWindow(args.Length > 0 ? args[0] : null));
        }
    }
}
