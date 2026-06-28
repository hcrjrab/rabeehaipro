"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api, type TaskSummary } from "@/lib/api-client";
import { ListTodo, Play, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";

const statusIcons: Record<string, React.ReactNode> = {
  pending: <Clock className="h-4 w-4 text-muted-foreground" />,
  planning: <Loader2 className="h-4 w-4 text-blue-400" />,
  running: <Loader2 className="h-4 w-4 animate-spin text-blue-400" />,
  completed: <CheckCircle2 className="h-4 w-4 text-emerald-400" />,
  failed: <XCircle className="h-4 w-4 text-destructive" />,
  cancelled: <XCircle className="h-4 w-4 text-muted-foreground" />,
};

const statusVariants: Record<string, "default" | "secondary" | "success" | "destructive" | "warning" | "outline"> = {
  pending: "secondary",
  planning: "warning",
  running: "warning",
  completed: "success",
  failed: "destructive",
  cancelled: "outline",
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState(false);

  const load = () => {
    setLoading(true);
    api.tasks.list().then(setTasks).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const runTask = async () => {
    if (!goal.trim()) return;
    setRunning(true);
    try {
      await api.tasks.run(goal);
      setGoal("");
      load();
    } catch {} finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ListTodo className="h-5 w-5 text-primary" />
        <h1 className="text-xl font-bold tracking-tight">Tasks</h1>
      </div>

      <Card>
        <CardHeader><CardTitle>New Task</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            placeholder="Describe the task you want the AI to execute..."
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            rows={3}
          />
          <Button onClick={runTask} disabled={running || !goal.trim()}>
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Execute Task
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Task History</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
            </div>
          ) : tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tasks yet.</p>
          ) : (
            <ScrollArea className="max-h-96">
              <div className="space-y-3">
                {tasks.map((task) => (
                  <div key={task.id} className="rounded-lg border p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{task.goal}</span>
                      <Badge variant={statusVariants[task.status] ?? "outline"}>
                        <span className="mr-1">{statusIcons[task.status]}</span>
                        {task.status}
                      </Badge>
                    </div>
                    <div className="mt-1 flex gap-2 text-xs text-muted-foreground">
                      <span>{new Date(task.created_at).toLocaleString()}</span>
                      {task.plan && <span>{task.plan.steps.length} steps</span>}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
