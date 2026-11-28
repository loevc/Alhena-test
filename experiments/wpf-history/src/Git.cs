using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Alhena
{
    public sealed class Commit
    {
        public string Hash { get; set; }
        public string[] Parents { get; set; }
        public string Author { get; set; }
        public string Date { get; set; }
        public string Refs { get; set; }
        public string Subject { get; set; }
        public string ShortHash { get { return Hash.Substring(0, 8); } }
        public GraphRow Graph { get; set; }
    }
    public sealed class FileChange
    {
        public string Status { get; set; }
        public string Path { get; set; }
        public string OldPath { get; set; }
        public override string ToString() { return Status + "   " + (OldPath == null ? Path : OldPath + " → " + Path); }
    }
    public sealed class Branch
    {
        public string Ref { get; set; }
        public string Label { get; set; }
        public bool Remote { get; set; }
        public override string ToString() { return Label; }
    }
    public sealed class Git
    {
        public string Root { get; private set; }
        public Git(string root) { Root = root; }

        // Windows CommandLineToArgvW quoting; no shell and no interpolation into a script.
        public static string Quote(string value)
        {
            var result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in value) {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') result.Append('\\', slashes * 2 + 1);
                else result.Append('\\', slashes);
                result.Append(c); slashes = 0;
            }
            return result.Append('\\', slashes * 2).Append('"').ToString();
        }

        public Task<string> Run(params string[] args)
        {
            return Task.Run(async delegate {
                var info = new ProcessStartInfo("git", "--no-pager --literal-pathspecs -c color.ui=false -c core.quotepath=false " + String.Join(" ", args.Select(Quote))) {
                    WorkingDirectory = Root, UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
                };
                info.EnvironmentVariables["GIT_TERMINAL_PROMPT"] = "0";
                info.EnvironmentVariables["GIT_OPTIONAL_LOCKS"] = "0";
                using (var process = Process.Start(info)) {
                    var stdout = process.StandardOutput.ReadToEndAsync();
                    var stderr = process.StandardError.ReadToEndAsync();
                    if (!process.WaitForExit(30000)) { process.Kill(); throw new TimeoutException("Git 查询超过 30 秒，请缩小查询范围。"); }
                    var result = await stdout.ConfigureAwait(false);
                    var error = await stderr.ConfigureAwait(false);
                    if (process.ExitCode != 0) throw new InvalidOperationException(error.Trim());
                    return result;
                }
            });
        }
        public async Task<List<Branch>> Branches()
        {
            string output = await Run("for-each-ref", "--format=%(refname)%00%(HEAD)%00%(refname:short)", "refs/heads", "refs/remotes");
            return output.Split(new[] {'\n'}, StringSplitOptions.RemoveEmptyEntries).Select(line => {
                string[] f = line.TrimEnd('\r').Split('\0');
                return new Branch { Ref = f[0], Label = (f[1] == "*" ? "● " : "") + f[2], Remote = f[0].StartsWith("refs/remotes/", StringComparison.Ordinal) };
            }).ToList();
        }
        public async Task<List<Commit>> Log(string reference, int limit)
        {
            // An unborn repository has no refs; a detached HEAD can still have commits.
            string refs = await Run("for-each-ref", "--format=%(objectname)");
            bool hasHead = true;
            try { await Run("rev-parse", "--verify", "HEAD"); }
            catch (InvalidOperationException) { hasHead = false; }
            if (String.IsNullOrWhiteSpace(refs) && !hasHead) return new List<Commit>();
            var args = new List<string> { "log", "--topo-order", "-z", "--format=%H%x00%P%x00%an%x00%aI%x00%D%x00%s", "-n", limit.ToString(CultureInfo.InvariantCulture) };
            if (reference == null) { args.Add("--all"); if (hasHead) args.Add("HEAD"); }
            else args.Add(reference);
            args.Add("--");
            string output = await Run(args.ToArray());
            var fields = output.Split('\0');
            var commits = new List<Commit>();
            for (int i = 0; i + 5 < fields.Length; i += 6) {
                DateTimeOffset date;
                commits.Add(new Commit { Hash = fields[i], Parents = fields[i+1].Split(new[] {' '}, StringSplitOptions.RemoveEmptyEntries), Author = fields[i+2],
                    Date = DateTimeOffset.TryParse(fields[i+3], out date) ? date.LocalDateTime.ToString("yyyy-MM-dd HH:mm") : fields[i+3], Refs = fields[i+4], Subject = fields[i+5] });
            }
            GraphLayout.Assign(commits);
            return commits;
        }
        public async Task<List<FileChange>> Files(Commit commit)
        {
            string output = commit.Parents.Length == 0
                ? await Run("diff-tree", "--root", "--no-commit-id", "-r", "--name-status", "-z", "-M", commit.Hash, "--")
                : await Run("diff", "--name-status", "-z", "-M", commit.Parents[0], commit.Hash, "--");
            var f = output.Split('\0'); var files = new List<FileChange>();
            for (int i = 0; i + 1 < f.Length && f[i].Length > 0; ) {
                string status = f[i++]; string path = f[i++]; string old = null;
                if (status[0] == 'R' || status[0] == 'C') { old = path; path = f[i++]; }
                files.Add(new FileChange { Status = status, Path = path, OldPath = old });
            }
            return files;
        }
        public Task<string> Patch(Commit commit, FileChange file)
        {
            var args = commit.Parents.Length == 0
                ? new List<string> { "show", "--format=", "--root", "--no-ext-diff", "--no-textconv", "--no-color", "--unified=4", "-M", commit.Hash }
                : new List<string> { "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--unified=4", "-M", commit.Parents[0], commit.Hash };
            args.Add("--"); if (file.OldPath != null) args.Add(file.OldPath); args.Add(file.Path);
            return Run(args.ToArray());
        }
    }
}
