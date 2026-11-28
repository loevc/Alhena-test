using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace Alhena
{
    public static class Tests
    {
        static int checks;
        static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); checks++; }
        static Commit C(string hash, params string[] parents) { return new Commit { Hash = hash, Parents = parents }; }
        public static int Main()
        {
            string root = Path.Combine(Path.GetTempPath(), "alhena-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try { Run(root).GetAwaiter().GetResult(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "fixture-path.txt"), root); Console.WriteLine("PASS: " + checks + " checks; fixture: " + root); return 0; }
            catch (Exception ex) { Console.Error.WriteLine(ex); Console.Error.WriteLine("Fixture: " + root); return 1; }
        }
        static async Task CommitFile(Git git, string message)
        {
            await git.Run("add", "--all");
            await git.Run("-c", "user.name=Alhena Test", "-c", "user.email=test@example.invalid", "commit", "-m", message);
        }
        static async Task Run(string root)
        {
            var git = new Git(root);
            await git.Run("init", "-b", "main");
            Assert((await git.Log(null, 300)).Count == 0, "unborn repository");
            string original = "中文 file.txt", renamed = "renamed 中文.txt";
            File.WriteAllText(Path.Combine(root, original), "first\nsecond\n");
            await CommitFile(git, "初始提交");
            var initial = (await git.Log(null, 300)).Single();
            Assert(initial.Subject == "初始提交" && initial.Parents.Length == 0, "UTF-8 root log");
            Assert((await git.Files(initial)).Single().Path == original, "root file path");
            Assert((await git.Patch(initial, (await git.Files(initial)).Single())).Contains("+first"), "root patch");
            await git.Run("symbolic-ref", "HEAD", "refs/heads/unborn");
            Assert((await git.Log(null, 300)).Count == 1, "unborn HEAD with other refs");
            await git.Run("symbolic-ref", "HEAD", "refs/heads/main");
            await git.Run("checkout", "-b", "feature");
            File.AppendAllText(Path.Combine(root, original), "feature\n");
            await CommitFile(git, "feature subject");
            await git.Run("checkout", "main");
            File.WriteAllText(Path.Combine(root, "main.txt"), "main\n");
            await CommitFile(git, "main subject");
            await git.Run("-c", "user.name=Alhena Test", "-c", "user.email=test@example.invalid", "merge", "--no-ff", "feature", "-m", "merge feature");
            var log = await git.Log(null, 300);
            Assert(log.Count == 4 && log[0].Parents.Length == 2, "merge graph / NUL framing");
            Assert((await git.Files(log[0])).Single().Path == original, "merge first-parent changes");
            Assert(log.All(c => c.Graph.Edges.All(e => e.From >= 0 && e.To >= 0)), "graph lane targets exist");
            foreach (var commit in log) foreach (var parent in commit.Parents) Assert(log.FindIndex(c => c.Hash == parent) > log.IndexOf(commit), "topological ordering");
            Assert((await git.Log("refs/heads/feature", 300)).Count == 2, "branch filter");
            Assert((await git.Log(null, 2)).Count == 2, "bounded loading");
            await git.Run("mv", "--", original, renamed);
            await CommitFile(git, "rename");
            var rename = (await git.Log(null, 300))[0];
            var change = (await git.Files(rename)).Single();
            Assert(change.OldPath == original && change.Path == renamed && change.Status.StartsWith("R"), "NUL rename paths");
            Assert((await git.Patch(rename, change)).Contains("rename from"), "rename patch");
            await git.Run("checkout", "--detach");
            File.WriteAllText(Path.Combine(root, "-leading [literal].txt"), "literal\n");
            await CommitFile(git, "detached head");
            var detached = (await git.Log(null, 300))[0];
            Assert(detached.Subject == "detached head", "include detached HEAD");
            Assert((await git.Patch(detached, (await git.Files(detached)).Single())).Contains("+literal"), "literal pathspec");
            Assert((await git.Branches()).Count == 2, "branch parsing");
            var diamond = new List<Commit> { C("merge", "left", "right"), C("left", "base"), C("right", "base"), C("base") };
            GraphLayout.Assign(diamond);
            Assert(diamond[0].Graph.Edges.Count == 2 && diamond[0].Graph.Width == 2, "merge forks two lanes");
            Assert(diamond[3].Graph.Width == 1 && diamond[3].Graph.Lane == 0, "converged lane is reclaimed");
            var octopus = new List<Commit> { C("m", "a", "b", "c"), C("c", "z"), C("b", "z"), C("a", "z"), C("z") };
            GraphLayout.Assign(octopus);
            Assert(octopus[0].Graph.Edges.Count == 3 && octopus.Last().Graph.Width == 1, "octopus converges");
            bool failed = false;
            try { await git.Run("rev-parse", "--verify", "does-not-exist"); } catch (InvalidOperationException) { failed = true; }
            Assert(failed, "Git errors are propagated");
        }
    }
}
