using System;
using System.Collections.Generic;
using System.Linq;

namespace Alhena
{
    public sealed class GraphEdge
    {
        public int From, To, Color;
        public bool StartsAtNode, EndsAtNode;
    }
    public sealed class GraphRow
    {
        public int Lane, Color, Width;
        public List<GraphEdge> Edges = new List<GraphEdge>();
    }
    public static class GraphLayout
    {
        public static void Assign(List<Commit> commits)
        {
            var lanes = new List<string>(); var colors = new List<int>(); int nextColor = 0;
            foreach (var commit in commits) {
                int lane = lanes.IndexOf(commit.Hash);
                bool incoming = lane >= 0;
                if (!incoming) { lane = lanes.Count; lanes.Add(commit.Hash); colors.Add(nextColor++); }
                var before = lanes.ToArray(); var beforeColors = colors.ToArray();
                var row = new GraphRow { Lane = lane, Color = colors[lane] };
                lanes.RemoveAt(lane); colors.RemoveAt(lane);
                for (int p = 0; p < commit.Parents.Length; p++) {
                    string parent = commit.Parents[p];
                    if (!lanes.Contains(parent)) {
                        int slot = p == 0 ? Math.Min(lane, lanes.Count) : lanes.Count;
                        lanes.Insert(slot, parent); colors.Insert(slot, p == 0 ? row.Color : nextColor++);
                    }
                }
                for (int i = 0; i < before.Length; i++) {
                    if (i == lane) {
                        if (incoming) row.Edges.Add(new GraphEdge { From = i, To = lane, Color = row.Color, EndsAtNode = true });
                    } else row.Edges.Add(new GraphEdge { From = i, To = lanes.IndexOf(before[i]), Color = beforeColors[i] });
                }
                foreach (string parent in commit.Parents) {
                    int target = lanes.IndexOf(parent);
                    row.Edges.Add(new GraphEdge { From = lane, To = target, Color = colors[target], StartsAtNode = true });
                }
                row.Width = Math.Max(before.Length, lanes.Count);
                commit.Graph = row;
            }
        }
    }
}
